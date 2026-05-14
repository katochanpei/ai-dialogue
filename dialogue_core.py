"""対話エンジンのコアロジック。

イベントジェネレータパターンで、CLIとUIから共通利用される。
yield する各イベントはdict形式で、'type'フィールドで種別を識別。

イベント種別:
- {"type": "topic", "text": str}                 : お題
- {"type": "turn", "round": int, "persona": "A"|"B",
   "name": str, "emoji": str, "text": str}       : 発言
- {"type": "facilitator", "round": int, "text": str}: 介入
- {"type": "agreement", "round": int}            : 合意成立
- {"type": "end", "reason": str, "round": int}   : 上限到達など
- {"type": "summary", "text": str}               : 結論・アドバイス（Markdown）
- {"type": "error", "text": str}                 : エラー
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv(Path(__file__).resolve().parent / ".env")
MODEL = "gemini-2.0-flash"


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

MIN_ROUNDS_BEFORE_JUDGE = 2


def _call_judge(client: genai.Client, last_a: str, last_b: str) -> bool:
    prompt = f"""次の2人の最新発言を読み、両者が同じ1つのサービス案で合意したか判定してください。

【発言A】
{last_a}

【発言B】
{last_b}

合意の条件: 同じ案を両者が支持し、明確な同意表現（「これでいこう」「進めましょう」「賛成」など）がある。

YES または NO のみで答えてください。"""
    try:
        resp = client.models.generate_content(model=MODEL, contents=prompt)
        return (resp.text or "").strip().upper().startswith("YES")
    except Exception:
        return False


def _call_facilitator(client: genai.Client, transcript: list[str]) -> str:
    history = "\n".join(transcript[-8:])
    prompt = f"""あなたは議論のファシリテーターです。以下の対話を読んで、簡潔に介入してください。

【対話ログ】
{history}

【出力ルール】
- ここまでの主要論点を1〜2行で要約
- 次に詰めるべきポイントを1つ示す（合意に向けて）
- 全体150字以内、優しい口調で"""
    try:
        resp = client.models.generate_content(model=MODEL, contents=prompt)
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
以下の議論を読んで、依頼者（人間）に向けた実用的なブリーフィングを作成してください。

【お題】
{topic}

【状態】
{state}

【議論の全文】
{history}

【出力ルール】
- 必ず下記のMarkdown構造で出力（見出し・絵文字もそのまま）
- 「結論」は具体的に。「誰向け・何ができる・どう価値を出す」が分かる粒度
- 「やるべきこと」は依頼者が今日・明日に動ける具体アクション
- 全体700〜1000字、読みやすく

## 🎯 結論
（合意/到達した内容を2〜4行で具体的に。合意せずなら有力候補と未決事項を整理）

## 🔑 議論で出たキーポイント
- （重要論点1）
- （重要論点2）
- （重要論点3、必要なら4-5個まで）

## 🚀 あなた（依頼者）が今やるべきこと
1. （最優先の具体アクション）
2. （次のアクション）
3. （その次）

## 🤔 さらに考えるべきこと
- （深掘りすべき問い1）
- （深掘りすべき問い2）

## ⚠️ 注意点・盲点
（議論で軽視された懸念や、依頼者が見落としそうなポイント。なければ「特になし」）
"""
    try:
        resp = client.models.generate_content(model=MODEL, contents=prompt)
        return (resp.text or "").strip()
    except Exception as e:
        return f"（要約失敗: {e}）"


def _send(chat, message: str) -> str:
    resp = chat.send_message(message)
    return (resp.text or "").strip()


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
            config=types.GenerateContentConfig(system_instruction=persona_a["system"]),
        )
        chat_b = client.chats.create(
            model=MODEL,
            config=types.GenerateContentConfig(system_instruction=persona_b["system"]),
        )
    except Exception as e:
        yield {"type": "error", "text": f"クライアント初期化失敗: {e}"}
        return

    yield {"type": "topic", "text": topic}

    next_input = (
        f"お題は「{topic}」です。"
        "あなたから議論を始めてください。最初の提案を200字以内で。"
    )
    last_a = ""
    last_b = ""
    transcript: list[str] = []

    for round_num in range(1, max_rounds + 1):
        try:
            last_a = _send(chat_a, next_input)
        except Exception as e:
            yield {"type": "error", "text": f"{persona_a['name']}: {e}"}
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

        try:
            last_b = _send(chat_b, last_a)
        except Exception as e:
            yield {"type": "error", "text": f"{persona_b['name']}: {e}"}
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
            summary = _call_summarizer(client, topic, transcript, agreed=True)
            yield {"type": "summary", "text": summary}
            return

        if round_num % intervention_interval == 0 and round_num < max_rounds:
            fac = _call_facilitator(client, transcript)
            yield {"type": "facilitator", "round": round_num, "text": fac}
            next_input = f"{last_b}\n\n（ファシリテーターより: {fac}）"
        else:
            next_input = last_b

    yield {"type": "end", "reason": "max_rounds", "round": max_rounds}
    summary = _call_summarizer(client, topic, transcript, agreed=False)
    yield {"type": "summary", "text": summary}


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
            lines.append(ev["text"])
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
