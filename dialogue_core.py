"""対話エンジンのコアロジック。

イベントジェネレータパターンで、CLIとUIから共通利用される。
yield する各イベントはdict形式で、'type'フィールドで種別を識別。

イベント種別:
- {"type": "topic", "text": str}                 : お題
- {"type": "turn", "round": int, "persona": "A"|"B",
   "name": str, "emoji": str, "text": str}       : 発言
- {"type": "facilitator", "round": int, "text": str}: 介入
- {"type": "thinking", "role": str, "emoji": str,
   "message": str, "for_event": str}             : 「考え中」表示（次の発言で置換）
- {"type": "retry", "role": str, "wait_sec": float,
   "attempt": int}                               : レート制限自動リトライ
- {"type": "agreement", "round": int}            : 合意成立
- {"type": "end", "reason": str, "round": int}   : 上限到達など
- {"type": "summary", "text": str}               : 結論・アドバイス（Markdown）
- {"type": "error", "text": str}                 : エラー
"""
from __future__ import annotations

import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import types

from personas import THINKING_PHRASES, PERSONA_QUIRKS


# キャラ発言前のローディング表示用フレーズ（ランダム選択）
THINKING_MESSAGES = [
    "考え中...",
    "脳みそフル回転中...",
    "うーん...",
    "ちょっと待って...",
    "アイデア練り中...",
    "言葉を選んでます...",
    "思案中...",
    "頭の中で議論中...",
    "深く考察中...",
    "ひらめき待ち...",
    "ロジック組み立て中...",
    "ベストな返答を模索中...",
    "ニューロン総動員中...",
    "返答を吟味中...",
]

FACILITATOR_THINKING_MESSAGES = [
    "論点を整理中...",
    "議論を俯瞰中...",
    "次のステップを検討中...",
    "アジェンダ調整中...",
]

SUMMARIZER_THINKING_MESSAGES = [
    "結論をまとめ中...",
    "要点を整理中...",
    "ブリーフィングを作成中...",
    "アクションを抽出中...",
]


def _pick_thinking(persona: dict | None = None) -> str:
    """ローディング文言を抽選。persona が渡された場合はキャラ固有プールから優先。

    キャラ固有プール（personas.THINKING_PHRASES）が空ならば、汎用プールにフォールバック。
    """
    if persona is not None:
        key = persona.get("key", "")
        pool = THINKING_PHRASES.get(key) or []
        if pool:
            return random.choice(pool)
    return random.choice(THINKING_MESSAGES)


def _pick_facilitator_thinking() -> str:
    return random.choice(FACILITATOR_THINKING_MESSAGES)


def _pick_summarizer_thinking() -> str:
    return random.choice(SUMMARIZER_THINKING_MESSAGES)

T = TypeVar("T")
MAX_RETRY_WAIT_SEC = 60.0  # 1回の待機の上限
MAX_RETRY_ATTEMPTS = 3  # 上限を超えたらエラーをそのまま返す


def _is_rate_limit_error(error_msg: str) -> bool:
    return "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg


def _is_unavailable_error(error_msg: str) -> bool:
    """503 UNAVAILABLE（モデル混雑など、サーバ側の一時的不調）。"""
    return "UNAVAILABLE" in error_msg or "503" in error_msg


def _is_transient_error(error_msg: str) -> bool:
    """リトライで自動回復が期待できる過渡的なエラー全般。"""
    return _is_rate_limit_error(error_msg) or _is_unavailable_error(error_msg)


def _parse_retry_delay(error_msg: str) -> float:
    """エラーメッセージから推奨待機秒数を推定。

    - 429 系: サーバが retryDelay を返す。なければ 30 秒。
    - 503 系: retryDelay は通常無いので、短めの 4 秒で素早く再試行。
    """
    # "Please retry in 20.007059734s." 形式
    m = re.search(r"retry in ([\d.]+)s", error_msg)
    if m:
        return float(m.group(1))
    # "'retryDelay': '20s'" 形式
    m = re.search(r"'retryDelay':\s*'(\d+)s'", error_msg)
    if m:
        return float(m.group(1))
    if _is_unavailable_error(error_msg):
        return 4.0
    return 30.0


def _safe_call_with_retry(
    fn: Callable[[], T],
    *,
    on_retry: Callable[[float, int], None] | None = None,
) -> T:
    """関数呼び出しを 429 / 503 自動リトライ付きで実行する。

    最大 MAX_RETRY_ATTEMPTS 回まで再試行。リトライ時は on_retry コールバックで通知。
    リトライ上限を超えたら最後の例外をそのまま re-raise。
    """
    for attempt in range(MAX_RETRY_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if _is_transient_error(msg) and attempt < MAX_RETRY_ATTEMPTS:
                base = _parse_retry_delay(msg)
                # 503 はサーバが retryDelay を返さないので、指数バックオフで広げる
                if _is_unavailable_error(msg):
                    base = base * (2 ** attempt)
                delay = min(max(base, 1.0), MAX_RETRY_WAIT_SEC)
                if on_retry:
                    on_retry(delay, attempt + 1)
                time.sleep(delay)
                continue
            raise


load_dotenv(Path(__file__).resolve().parent / ".env")
MODEL = "gemini-3.1-flash-lite"


def _get_api_key() -> str | None:
    """APIキーを取得（環境変数を実行時に読む）。

    Streamlit Cloud では app.py が st.secrets から os.environ にコピーする。
    ローカルでは .env から自動ロード済み。
    """
    return os.getenv("GEMINI_API_KEY")


# 後方互換のため定数も提供（インポート時点の値）
API_KEY = _get_api_key()

DEFAULT_TOPIC = (
    "2027年にバズりそうな新サービスを1つ考えて、"
    "両者で具体的なサービス内容（誰向け・何ができる・収益モデル）を合意してください。"
)

MIN_ROUNDS_BEFORE_JUDGE = 3


# 各キャラのシステムプロンプト末尾に共通付与される指示。
# キャラ設定より「全体トーン」を優先させる。"会話" ではなく "雑談" を作るための核心。
VARIATION_HINT = """

【全体トーン（最重要・キャラ設定より優先）】
- これは堅い議論ではなく **AI同士のカジュアルな雑談**。「結論を出す」より「思ったことを言う」場。
- 1ターンは **最大2文・60字目安**。説明を足さない。長くなるくらいなら短くしてでも言わない選択を取る。
- 「ですます」より自然な話し言葉。「〜やん」「〜じゃね？」「〜だよね」「〜思う」「〜くない？」を混ぜる。
- **賢くまとめようとしない**。論点整理・前置き・要約・改善提案・「両者の意見を統合すると…」は禁止。
- **雑な一言・合いの手・反応** を遠慮なく入れる。例：
  「アリじゃね？」「てか普通に読みたいわ」「えー、ホントに？」「いやそれだけ？」
  「あー、わかる」「マジか」「いや知らんけど」「ちょっと違うやろ」「うわ気になる」
  「それは草」「うっわ重い」「で？」「いやそれはそう」
- **たまに話を逸らす** のもOK。興味が別方向に飛ぶ、関係ない角度から茶々を入れる、それで十分会話になる。
- **皮肉・適当さ・ノリ・軽いボケ** は歓迎。お互い少しバカにし合うくらいの距離感がちょうどいい。
- キャラの役割（営業／悪役／子供／ツッコミ等）になりきり過ぎず、**空気として参加する**。

【絶対やらないこと】
- 「総括すると」「ここまでの議論を整理すると」「両者を踏まえて」みたいな進行役モード
- 「〜という観点では」「〜の側面で」「〜という前提で」みたいな論文調
- 一発言で結論を出す・締めにいく動き

【表現のバリエーション】
- 同じ口癖・同じ書き出しを連発しない。直前の自分の発言と被らせない。
- キャラ設定のサンプルフレーズは「方向性の例」。そのまま使い続けず、同じ意図を毎回違う言葉で。
- テンプレ感を出さない。人間っぽい揺らぎ・間・余白を持って話す。
"""


def _build_system_prompt(persona: dict) -> str:
    """ペルソナの基本プロンプトに共通トーン指示 + キャラ別口癖サンプルを付与して返す。"""
    quirks = PERSONA_QUIRKS.get(persona.get("key", ""), "")
    quirks_block = (
        f"\n\n【口癖サンプル（あくまで方向性。毎ターン同じ語を連発しない）】\n{quirks}"
        if quirks
        else ""
    )
    return f"{persona['system']}\n{VARIATION_HINT}{quirks_block}"


# === ボケ強制モード ===
# N% の確率で次の発言時に「ボケて」とシステム側から指示を差し込み、ノリと崩しを足す。
BOKE_PROB = 0.18
BOKE_MODES = [
    "今回だけ：話を完全に別の方向に逸らして、お題から逃げて1〜2文で軽く返して。",
    "今回だけ：皮肉と短いツッコミだけで1〜2文返して。",
    "今回だけ：全然関係ない興味（食べ物・天気・別キャラの見た目とか）に飛んで1〜2文返して。",
    "今回だけ：ノリで適当に同意して、すぐ別の話題を振って1〜2文返して。",
    "今回だけ：相手の発言にわざと噛み合わない返しを1〜2文してみて。",
    "今回だけ：キャラを少し崩して、軽くボケるか茶化して1〜2文返して。",
]


def _maybe_inject_boke(message: str) -> str:
    """確率で「今回だけボケて」の特別指示をメッセージ末尾に差し込む。"""
    if random.random() < BOKE_PROB:
        boke = random.choice(BOKE_MODES)
        return f"{message}\n\n【今回だけ特別指示】{boke}"
    return message


def check_api_availability() -> tuple[bool, str, str]:
    """議論開始前に API が利用可能かを最小リクエストでチェックする。

    Returns:
        (ok, message, code)
        code: "ok" | "no_key" | "rate_limit_day" | "rate_limit_minute" |
              "free_tier_zero" | "auth_error" | "model_not_found" | "unknown"
    """
    api_key = _get_api_key()
    if not api_key:
        return (
            False,
            "GEMINI_API_KEY が設定されていません。.env または Streamlit Cloud の Secrets を確認してください。",
            "no_key",
        )
    try:
        client = genai.Client(api_key=api_key)
        _safe_call_with_retry(
            lambda: client.models.generate_content(
                model=MODEL,
                contents="ping",
                config=types.GenerateContentConfig(max_output_tokens=1),
            )
        )
        return True, "API利用可能", "ok"
    except Exception as e:
        msg = str(e)
        if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
            if "limit: 0" in msg:
                return (
                    False,
                    f"モデル『{MODEL}』が無料枠の対象から外されました（limit: 0）。\n"
                    f"対応: `dialogue_core.py` の MODEL 定数を別モデル"
                    f"（例: gemini-2.5-flash, gemini-2.5-flash-lite）に変更してください。",
                    "free_tier_zero",
                )
            if "PerDay" in msg:
                return (
                    False,
                    f"モデル『{MODEL}』の1日あたりリクエスト上限に達しました（無料枠）。\n"
                    "対応: 翌日まで待つか、別のAPIキーやモデルに切り替えてください。",
                    "rate_limit_day",
                )
            return (
                False,
                "短時間に多くのリクエストが行われたため、レート制限がかかりました（無料枠の毎分上限）。\n"
                "対応: 1〜2分待ってから再試行してください。",
                "rate_limit_minute",
            )
        if "PERMISSION" in msg or "401" in msg or "API key not valid" in msg.lower():
            return (
                False,
                "APIキーが無効または権限がありません。\n"
                "対応: Google AI Studio でキーを再生成し、.env または Secrets に設定してください。",
                "auth_error",
            )
        if "not found" in msg.lower() or "404" in msg:
            return (
                False,
                f"モデル『{MODEL}』が見つかりません。\n対応: MODEL 定数のスペルを確認してください。",
                "model_not_found",
            )
        return False, f"APIエラー:\n{msg[:500]}", "unknown"


def _call_judge(client: genai.Client, last_a: str, last_b: str) -> bool:
    prompt = f"""2人の雑談の最新2発言を読み、**2人が同じ方向に乗ってる**かを判定してください。
形式的な「合意」ではなく、カジュアルに同じ案／同じ気分に寄ってる状態を見ます。

【発言A】
{last_a}

【発言B】
{last_b}

【YES と判定する条件】
- 両者が同じ方向・同じ案に乗っている
- 片方の提案や感想に、もう片方が肯定的に乗っている（例：「アリ」「いいやん」「それで」「うん」「マジそれ」「確定」「決まり」「やろう」「これでいこ」「賛成」「そうそう」「同じこと思った」など、雑談トーンの肯定でも可）
- 反対・引っかかり・新しい疑問が残っていない

【NO と判定する条件】
- どちらかが「でも」「いや」「ちょっと」「うーん」「微妙」「ちゃう」と引っかかっている
- 話題が別方向に逸れて、同じ案について揃っていない
- 新しい問いを投げかけている／話を広げている最中
- まだお互いに違う案を出し合っている

雑談なので「誰向け・何ができる」みたいな完璧な具体性は要求しない。**2人がノってるか**が判定基準。
YES または NO のみで答えてください。"""
    try:
        resp = _safe_call_with_retry(
            lambda: client.models.generate_content(model=MODEL, contents=prompt)
        )
        return (resp.text or "").strip().upper().startswith("YES")
    except Exception:
        return False


def _call_facilitator(client: genai.Client, transcript: list[str]) -> str:
    history = "\n".join(transcript[-8:])
    prompt = f"""あなたは2人の雑談を見守る空気役です。たまに軽く話題を振るだけ。

【対話ログ】
{history}

【出力ルール】
- 「ここまでの論点を整理すると」みたいな進行役の口調は禁止
- 「で、〜はどう？」「ちなみに〜って実際どう思う？」みたいな軽い投げ込みを1〜2文
- 60字以内、雑談トーン、整理・要約・まとめは絶対しない"""
    try:
        resp = _safe_call_with_retry(
            lambda: client.models.generate_content(model=MODEL, contents=prompt)
        )
        return (resp.text or "").strip()
    except Exception as e:
        return f"（介入失敗: {e}）"


def _call_summarizer(
    client: genai.Client,
    topic: str,
    transcript: list[str],
    agreed: bool,
) -> str:
    """議論を要約し、依頼者向けの実用ブリーフィングを生成する。"""
    history = "\n".join(transcript)
    state = "両者が合意した" if agreed else "合意に至らなかった（上限到達）"
    prompt = f"""あなたは議論の要約役 兼 アドバイザーです。
以下の議論を読んで、依頼者向けの実用ブリーフィングを作成してください。

【お題】
{topic}

【状態】
{state}

【議論の全文】
{history}

【出力ルール】
- 下記のMarkdown構造のみで出力（見出し・絵文字はそのまま）
- 「結論」は2〜3行で具体的に（誰向け・何ができる・どう価値）
- 「キーポイント」は3〜4つ、各1行
- 「次にやること」は具体アクションを1〜2つ
- 「さらに考えるべきこと」は深掘り問いを1〜2つ
- 「注意点・盲点」は1〜2行（なければ「特になし」）
- 全体400〜550字。冗長な前置きや言い換えは省き、要点だけ

## 🎯 結論
（合意/到達点を2〜3行で具体的に。合意せずなら有力候補と未決事項を1〜2行）

## 🔑 キーポイント
- （重要論点1）
- （重要論点2）
- （重要論点3）

## 🚀 次にやること
1. （最優先の具体アクション）
2. （次のアクション、必要なら）

## 🤔 さらに考えるべきこと
- （深掘り問い）

## ⚠️ 注意点・盲点
（議論で軽視された懸念や見落としポイント。なければ「特になし」）
"""
    try:
        resp = _safe_call_with_retry(
            lambda: client.models.generate_content(model=MODEL, contents=prompt)
        )
        return (resp.text or "").strip()
    except Exception as e:
        return f"（要約失敗: {e}）"


def _send_with_retry_events(chat, message: str) -> Iterator[tuple[str, object]]:
    """`chat.send_message` を 429 / 503 自動リトライ付きで実行するジェネレータ。

    yields:
        ("retry", {"wait_sec": float, "attempt": int}) - リトライ前
        ("result", str)                                 - 成功時のテキスト
        ("error", Exception)                            - 最終失敗時
    """
    for attempt in range(MAX_RETRY_ATTEMPTS + 1):
        try:
            resp = chat.send_message(message)
            yield ("result", (resp.text or "").strip())
            return
        except Exception as e:
            msg = str(e)
            if _is_transient_error(msg) and attempt < MAX_RETRY_ATTEMPTS:
                base = _parse_retry_delay(msg)
                if _is_unavailable_error(msg):
                    base = base * (2 ** attempt)
                delay = min(max(base, 1.0), MAX_RETRY_WAIT_SEC)
                yield ("retry", {"wait_sec": delay, "attempt": attempt + 1})
                time.sleep(delay)
                continue
            yield ("error", e)
            return


def dialogue_events(
    topic: str,
    persona_a: dict,
    persona_b: dict,
    max_rounds: int = 20,
    intervention_interval: int = 3,
    delay_sec: float = 2.0,
) -> Iterator[dict]:
    """対話イベントを順次yield するジェネレータ。"""
    api_key = _get_api_key()
    if not api_key:
        yield {"type": "error", "text": "GEMINI_API_KEY が設定されていません（.env または Streamlit secrets）"}
        return

    try:
        client = genai.Client(api_key=api_key)
        chat_a = client.chats.create(
            model=MODEL,
            config=types.GenerateContentConfig(
                system_instruction=_build_system_prompt(persona_a)
            ),
        )
        chat_b = client.chats.create(
            model=MODEL,
            config=types.GenerateContentConfig(
                system_instruction=_build_system_prompt(persona_b)
            ),
        )
    except Exception as e:
        yield {"type": "error", "text": f"クライアント初期化失敗: {e}"}
        return

    yield {"type": "topic", "text": topic}

    next_input = (
        f"お題は「{topic}」です。"
        "あなたから雑談を始めてください。最初の一言だけ、2文以内・60字目安で軽く投げて。"
    )
    last_a = ""
    last_b = ""
    transcript: list[str] = []

    for round_num in range(1, max_rounds + 1):
        # --- A の発言（リトライ対応 + 「考え中」表示） ---
        yield {
            "type": "thinking",
            "role": persona_a["name"],
            "emoji": persona_a["emoji"],
            "message": _pick_thinking(persona_a),
            "for_event": "turn_a",
        }
        last_a = None
        for item_type, payload in _send_with_retry_events(chat_a, _maybe_inject_boke(next_input)):
            if item_type == "retry":
                yield {
                    "type": "retry",
                    "role": persona_a["name"],
                    "wait_sec": payload["wait_sec"],
                    "attempt": payload["attempt"],
                }
            elif item_type == "result":
                last_a = payload
            elif item_type == "error":
                yield {"type": "error", "text": f"{persona_a['name']}: {payload}"}
                return
        if last_a is None:
            return
        yield {
            "type": "turn",
            "round": round_num,
            "persona": "A",
            "name": persona_a["name"],
            "emoji": persona_a["emoji"],
            "text": last_a,
        }
        transcript.append(f"{persona_a['name']}: {last_a}")
        time.sleep(delay_sec)

        # --- B の発言（リトライ対応 + 「考え中」表示） ---
        yield {
            "type": "thinking",
            "role": persona_b["name"],
            "emoji": persona_b["emoji"],
            "message": _pick_thinking(persona_b),
            "for_event": "turn_b",
        }
        last_b = None
        for item_type, payload in _send_with_retry_events(chat_b, _maybe_inject_boke(last_a)):
            if item_type == "retry":
                yield {
                    "type": "retry",
                    "role": persona_b["name"],
                    "wait_sec": payload["wait_sec"],
                    "attempt": payload["attempt"],
                }
            elif item_type == "result":
                last_b = payload
            elif item_type == "error":
                yield {"type": "error", "text": f"{persona_b['name']}: {payload}"}
                return
        if last_b is None:
            return
        yield {
            "type": "turn",
            "round": round_num,
            "persona": "B",
            "name": persona_b["name"],
            "emoji": persona_b["emoji"],
            "text": last_b,
        }
        transcript.append(f"{persona_b['name']}: {last_b}")
        time.sleep(delay_sec)

        if round_num >= MIN_ROUNDS_BEFORE_JUDGE and _call_judge(client, last_a, last_b):
            yield {"type": "agreement", "round": round_num}
            yield {
                "type": "thinking",
                "role": "要約役",
                "emoji": "📋",
                "message": _pick_summarizer_thinking(),
                "for_event": "summary",
            }
            summary = _call_summarizer(client, topic, transcript, agreed=True)
            yield {"type": "summary", "text": summary, "topic": topic}
            return

        if round_num % intervention_interval == 0 and round_num < max_rounds:
            yield {
                "type": "thinking",
                "role": "ファシリテーター",
                "emoji": "🎤",
                "message": _pick_facilitator_thinking(),
                "for_event": "facilitator",
            }
            fac = _call_facilitator(client, transcript)
            yield {"type": "facilitator", "round": round_num, "text": fac}
            next_input = f"{last_b}\n\n（ファシリテーターより: {fac}）"
        else:
            next_input = last_b

    yield {"type": "end", "reason": "max_rounds", "round": max_rounds}
    yield {
        "type": "thinking",
        "role": "要約役",
        "emoji": "📋",
        "message": _pick_summarizer_thinking(),
        "for_event": "summary",
    }
    summary = _call_summarizer(client, topic, transcript, agreed=False)
    yield {"type": "summary", "text": summary, "topic": topic}


def build_log_markdown(
    events_log: list[dict],
    topic: str,
    persona_a_name: str,
    persona_b_name: str,
) -> str:
    """イベントログを Markdown 文字列として組み立てる（ディスク書き出しなし）。"""
    lines = [
        "# AI対話ログ",
        "",
        f"- 日時: {datetime.now().isoformat(timespec='seconds')}",
        f"- モデル: {MODEL}",
        f"- キャラA: {persona_a_name}",
        f"- キャラB: {persona_b_name}",
        f"- お題: {topic}",
        "",
        "---",
        "",
        "## お題",
        "",
        topic,
        "",
    ]

    for ev in events_log:
        t = ev.get("type")
        if t == "turn":
            lines.append(f"## ターン{ev['round']} - {ev['emoji']} {ev['name']}")
            lines.append("")
            lines.append(ev["text"])
            lines.append("")
        elif t == "facilitator":
            lines.append(f"## 🎤 ファシリテーター介入（{ev['round']}往復経過）")
            lines.append("")
            lines.append(ev["text"])
            lines.append("")
        elif t == "agreement":
            lines.append(f"## ✅ 合意成立（{ev['round']}往復）")
            lines.append("")
        elif t == "end":
            lines.append(f"## ⏱ 最大往復数 {ev['round']} に到達して終了")
            lines.append("")
        elif t == "summary":
            lines.append("---")
            lines.append("")
            lines.append("# 📋 結論ブリーフィング")
            lines.append("")
            if ev.get("topic"):
                lines.append(f"**📋 お題:** {ev['topic']}")
                lines.append("")
            lines.append(ev["text"])
            lines.append("")
        elif t == "retry":
            lines.append(
                f"> ⏳ レート制限により {ev.get('wait_sec', 0):.0f} 秒待機・自動リトライ"
                f"（{ev.get('role', '')}）"
            )
            lines.append("")
        elif t == "error":
            lines.append("## ❌ エラー")
            lines.append("")
            lines.append(ev["text"])
            lines.append("")

    return "\n".join(lines)


def save_log(
    events_log: list[dict],
    topic: str,
    persona_a_name: str,
    persona_b_name: str,
) -> Path:
    """イベントログを Markdown ファイルとしてディスクに保存。"""
    content = build_log_markdown(events_log, topic, persona_a_name, persona_b_name)
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_path = log_dir / f"{timestamp}_dialogue.md"
    log_path.write_text(content, encoding="utf-8")
    return log_path
