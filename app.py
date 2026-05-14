"""Streamlit UI: Gemini同士の自律対話を観戦するブラウザ画面。

Run:
    streamlit run app.py
"""
from __future__ import annotations

import html
import os
import random
from pathlib import Path

import streamlit as st


RANDOM_TOPICS = [
    "来年バズりそうな新サービスを1つ考えて、両者で具体案として合意してください。",
    "リモートワークと出社、これからの最適なバランスは何か。",
    "AIに任せていい仕事と、人間がやり続けるべき仕事の境界線は。",
    "副業で月10万円稼ぐ最も現実的な方法は。",
    "中小企業の採用力を3倍にするための1つの施策を決めてください。",
    "10年後も生き残る職業を3つに絞ってください。",
    "Z世代が本当に求めている福利厚生は何か、1つに絞って提案してください。",
    "通勤時間をビジネスチャンスに変える新サービスを1つ考えてください。",
    "ペット業界で今後伸びるサービスを1つ提案してください。",
    "シニア向けに本当に売れる新商品とは何かを決めてください。",
    "コンビニで売れる新カテゴリの商品を1つ提案してください。",
    "外食産業の人手不足を解決する画期的なアイデアを1つ決めてください。",
    "オンライン会議をもっと楽しくする工夫を1つ提案してください。",
    "若手社員のモチベーションを上げる最強の仕掛けを1つ決めてください。",
    "電気代を半分にする新しい家電のアイデアを1つ考えてください。",
    "もしオフィスを廃止するなら、代わりに何を作るべきか。",
    "30秒で人を笑わせる動画コンテンツの企画を1つ。",
    "新しい朝活ビジネスのアイデアを1つ提案してください。",
    "サブスクリプションが向くサービスと向かないサービスの境界線は。",
    "地方都市の人口減少を逆手に取った新ビジネスを1つ。",
]


def _bootstrap_secrets() -> None:
    """Streamlit Cloud の secrets を環境変数にコピー（dialogue_core から見えるように）。"""
    try:
        for key in (
            "GEMINI_API_KEY",
            "APP_PASSWORD",
            "MULTI_USER_MODE",
        ):
            if key in st.secrets and not os.environ.get(key):
                os.environ[key] = str(st.secrets[key])
    except Exception:
        pass  # secrets.toml が無い（ローカル .env 運用）でもエラーにしない


_bootstrap_secrets()


def _is_multi_user_mode() -> bool:
    """クラウド共有モード（ログ非保存・履歴非表示）。"""
    return os.environ.get("MULTI_USER_MODE", "").lower() in ("true", "1", "yes")


from dialogue_core import (  # noqa: E402
    DEFAULT_TOPIC,
    build_log_markdown,
    check_api_availability,
    dialogue_events,
    save_log,
)
from personas import CUSTOM_KEY, DEFAULT_A_KEY, DEFAULT_B_KEY, PERSONAS  # noqa: E402


st.set_page_config(page_title="AI議論", page_icon="🎙", layout="wide")


def _generate_prism_colors() -> str:
    """ランダムなプリズム色グラデーション文字列を生成。

    色相環を7等分し、開始位置と各色の彩度・明度をランダム化することで
    毎セッション異なる「美しい」虹色を作る。最後に最初の色を繰り返して
    アニメーションがループしても自然に繋がるようにする。
    """
    hue_start = random.randint(0, 360)
    n = 7
    parts = []
    for i in range(n):
        hue = (hue_start + i * (360 // n)) % 360
        sat = random.randint(82, 95)
        light = random.randint(58, 68)
        parts.append(f"hsl({hue},{sat}%,{light}%)")
    return ", ".join(parts + [parts[0]])


# セッション中は色を固定（ボタンが安定して見える）。新しいセッションで色変わる。
if "prism_colors" not in st.session_state:
    st.session_state["prism_colors"] = _generate_prism_colors()
_PRISM = st.session_state["prism_colors"]


# === Sidebar styling: 幅を広げ、フォントを小さく ===
_SIDEBAR_CSS = """
<style>
    section[data-testid="stSidebar"] {
        min-width: 340px !important;
        width: 340px !important;
    }
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    section[data-testid="stSidebar"] .stSelectbox div[role="combobox"] {
        font-size: 0.82rem !important;
        line-height: 1.35 !important;
    }
    section[data-testid="stSidebar"] h1 { font-size: 1.25rem !important; }
    section[data-testid="stSidebar"] h2 { font-size: 1.0rem !important; }
    section[data-testid="stSidebar"] h3 { font-size: 0.9rem !important; }
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        font-size: 0.72rem !important;
    }
    /* お題入力のプレースホルダを薄め＆黒寄りグレーに */
    section[data-testid="stSidebar"] textarea::placeholder,
    section[data-testid="stSidebar"] textarea::-webkit-input-placeholder,
    section[data-testid="stSidebar"] textarea::-moz-placeholder {
        color: rgba(255, 255, 255, 0.22) !important;
        opacity: 1 !important;
    }
    /* 「ランダム議論」ボタン：プリズム色のうねうねアニメーション（派手版） */
    @keyframes prismFlow {
        0%   { background-position:   0%   0%; }
        25%  { background-position: 100%   0%; }
        50%  { background-position: 100% 100%; }
        75%  { background-position:   0% 100%; }
        100% { background-position:   0%   0%; }
    }
    @keyframes prismBreathe {
        0%, 100% {
            box-shadow:
                0 0 14px rgba(255, 255, 255, 0.22),
                inset 0 0 14px rgba(255, 255, 255, 0.10);
            filter: brightness(1.00) saturate(1.00);
        }
        50% {
            box-shadow:
                0 0 38px rgba(255, 255, 255, 0.55),
                inset 0 0 30px rgba(255, 255, 255, 0.22);
            filter: brightness(1.12) saturate(1.20);
        }
    }
    @keyframes prismHueShift {
        0%, 100% { filter: hue-rotate(0deg); }
        50%      { filter: hue-rotate(25deg); }
    }
    section[data-testid="stSidebar"] button[kind="secondary"] {
        background: linear-gradient(135deg, __PRISM_COLORS__) !important;
        background-size: 600% 600% !important;
        animation:
            prismFlow 4.5s linear infinite,
            prismBreathe 2.4s ease-in-out infinite,
            prismHueShift 8s ease-in-out infinite !important;
        color: #fff !important;
        border: 1px solid rgba(255, 255, 255, 0.40) !important;
        font-weight: 700 !important;
        text-shadow: 0 1px 4px rgba(0, 0, 0, 0.50) !important;
        transition: transform 0.2s ease !important;
    }
    section[data-testid="stSidebar"] button[kind="secondary"]:hover {
        animation:
            prismFlow 2s linear infinite,
            prismBreathe 1.2s ease-in-out infinite,
            prismHueShift 4s ease-in-out infinite !important;
        transform: translateY(-1px) scale(1.02) !important;
    }
</style>
"""
st.markdown(_SIDEBAR_CSS.replace("__PRISM_COLORS__", _PRISM), unsafe_allow_html=True)


def _render_warning_banner() -> None:
    """常時表示の注意書き（小さめ）。"""
    st.caption(
        "⚠️ お題・会話内容は Google の Gemini API に送信されます。"
        "**社内秘・個人情報・顧客データは入力しないでください。**"
    )


HELP_MARKDOWN = """
### 🤔 何ができるか
- お題を与えると、**2人のAIキャラが議論して合意**に至る
- 3往復ごとに**ファシリテーターAI**が論点を整理して介入
- 終わったら**要約と次のアクション**を提案してくれる

### ⚙️ どうやって動いているか（噛み砕いて）

```
あなたのブラウザ ─► Streamlit Cloud ─► Google Gemini API
                                            │
                                            ▼
                                    4人のGeminiが連携
                                    ├ キャラA（提案役）
                                    ├ キャラB（反論役）
                                    ├ ファシリテーター
                                    └ 要約役（結論まとめ）
```

1. **Gemini = Googleが作った大規模言語モデル**（ChatGPTのGoogle版にあたるもの）
2. **API経由で呼び出す**: 毎回ネット越しに Google のサーバに「これを考えて」と投げる
3. **役割演技**: 同じGeminiでも違う性格設定（システムプロンプトと呼ぶ）を与えると、別人格として振る舞う
4. **会話の流れ**: あなたのお題 → キャラA発言 → キャラB発言 → 判定AIが合意チェック → 合意なら要約、まだなら次のラウンドへ

### 📤 何が送信されるか
- ✅ お題、キャラ設定、議論の内容すべて
- ⚠️ これらは**Googleのサーバに保存される可能性があります**
- ⚠️ 無料プラン使用時、Googleが**モデル改善に使用する場合があります**

**入力してはいけないもの:**
- ❌ 社外秘・社内秘情報
- ❌ 個人情報・顧客データ
- ❌ 未公開の経営情報、契約情報
- ❌ パスワード・APIキー等

→ ブレストや雑談、公開情報ベースのお題でのみご利用ください。

### 💰 コストと制限
- **完全無料**（Geminiの無料枠を使用）
- 全員合計で**1日数百〜千リクエスト程度**が上限（Gemini 3.1 Flash-Lite 無料枠、Googleの設定次第）
- 1議論あたり 10〜20リクエスト消費
- 上限を超えるとその日は使用できません（翌朝復活）

### 🧰 中身の技術
- モデル: **Gemini 3.1 Flash-Lite**
- UI: **Streamlit**
- 言語: Python
- ホスティング: Streamlit Community Cloud
- ソース: [github.com/katochanpei/ai-dialogue](https://github.com/katochanpei/ai-dialogue)
"""


def _render_help_panel(expanded: bool = False) -> None:
    """仕組みの解説パネル。"""
    with st.expander("❓ このツールの仕組み・注意点を読む", expanded=expanded):
        st.markdown(HELP_MARKDOWN)


def _check_password() -> bool:
    """パスワード認証。APP_PASSWORD 未設定なら認証スキップ（ローカル開発時）。"""
    expected = os.environ.get("APP_PASSWORD", "")
    if not expected:
        return True
    if st.session_state.get("authenticated"):
        return True

    st.title("🎙 AI議論")
    st.caption("社内向け Gemini × Gemini 議論ツール")
    pw = st.text_input("パスワード", type="password", key="_pw_input")
    if st.button("ログイン", type="primary"):
        if pw == expected:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


def _init_state() -> None:
    defaults = {
        "running": False,
        "last_log_path": None,
        "last_log_md": None,
        "last_log_name": None,
        "viewing_log": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _persona_selector(side: str, default_key: str) -> dict:
    keys = list(PERSONAS.keys())
    idx = keys.index(default_key) if default_key in keys else 0
    selected_key = st.selectbox(
        f"キャラ{side}",
        keys,
        index=idx,
        format_func=lambda k: PERSONAS[k]["label"],
        key=f"persona_{side}_select",
    )

    if selected_key == CUSTOM_KEY:
        name = st.text_input("名前", value="カスタム", key=f"persona_{side}_custom_name")
        emoji = st.text_input("絵文字", value="✏️", key=f"persona_{side}_custom_emoji")
        system = st.text_area(
            "プロンプト",
            value="あなたは独自に設定されたキャラクターです。\n【性格】\n【口調】\n【話し方ルール】\n- 一度の発言は200字以内\n- 合意したら明確に同意を表明",
            height=160,
            key=f"persona_{side}_custom_system",
        )
        return {
            "key": "custom",
            "name": name or "カスタム",
            "emoji": emoji or "✏️",
            "label": f"{emoji or '✏️'} {name or 'カスタム'}",
            "system": system,
        }

    p = PERSONAS[selected_key]
    with st.expander(f"プレビュー: {p['label']}", expanded=False):
        st.markdown(f"```\n{p['system']}\n```")
    return p


def _render_event(ev: dict, container) -> None:
    t = ev.get("type")
    if t == "turn":
        role = "user" if ev["persona"] == "A" else "assistant"
        with container.chat_message(role, avatar=ev["emoji"]):
            st.caption(f"ターン{ev['round']} ・ {ev['name']}")
            st.write(ev["text"])
    elif t == "facilitator":
        with container.chat_message("ai", avatar="🎤"):
            st.caption(f"ファシリテーター介入（{ev['round']}往復経過）")
            st.info(ev["text"])
    elif t == "retry":
        wait_sec = ev.get("wait_sec", 0)
        attempt = ev.get("attempt", 1)
        role = ev.get("role", "")
        container.warning(
            f"⏳ APIレート制限を検出（{role}）。"
            f"{wait_sec:.0f} 秒待機してから自動リトライします（{attempt}回目）..."
        )
    elif t == "agreement":
        container.success(f"✅ 合意成立！（{ev['round']}往復）")
    elif t == "end":
        container.warning(f"⏱ 最大往復数 {ev['round']} に到達。合意せず終了。")
    elif t == "summary":
        with container.container():
            st.markdown("---")
            st.markdown("# 📋 結論ブリーフィング")
            st.caption("議論の要約と、あなたの次のアクション")
            with st.container(border=True):
                if ev.get("topic"):
                    st.markdown(
                        f"""
<div style="
    background: linear-gradient(135deg,
        rgba(59, 130, 246, 0.16) 0%,
        rgba(30, 64, 175, 0.22) 100%);
    padding: 22px 26px;
    border-left: 5px solid #3b82f6;
    border-radius: 10px;
    margin-bottom: 26px;
">
  <div style="font-size: 0.78rem; color: #93c5fd; font-weight: 700;
              letter-spacing: 0.18em; margin-bottom: 10px;
              text-transform: uppercase;">
    📋 お題
  </div>
  <div style="font-size: 1.65rem; font-weight: 700; line-height: 1.55;
              color: #ffffff; letter-spacing: 0.01em;">
    {html.escape(ev["topic"])}
  </div>
</div>
""",
                        unsafe_allow_html=True,
                    )
                st.markdown(ev["text"])
    elif t == "error":
        container.error(f"❌ {ev['text']}")


def _list_past_logs() -> list[Path]:
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    return sorted(log_dir.glob("*_dialogue.md"), reverse=True)


def _sidebar() -> dict:
    with st.sidebar:
        st.title("🎙 AI議論")
        st.caption("Gemini × Gemini 自律対話")

        st.subheader("お題")
        topic_input = st.text_area(
            "お題",
            value="",
            placeholder=DEFAULT_TOPIC,
            label_visibility="collapsed",
            height=110,
            key="topic_input",
            help="空のまま「議論スタート」を押すと、表示中のお題例で開始します",
        )
        # 入力が空ならプレースホルダの内容で議論を開始
        topic = topic_input.strip() or DEFAULT_TOPIC

        st.subheader("キャラ設定")
        persona_a = _persona_selector("A", DEFAULT_A_KEY)
        st.markdown("---")
        persona_b = _persona_selector("B", DEFAULT_B_KEY)

        with st.expander("詳細パラメータ", expanded=False):
            max_rounds = st.slider("最大往復", 1, 30, 20)
            interval = st.slider("介入間隔", 1, 10, 3)
            delay = st.slider("遅延(秒)", 0.0, 5.0, 2.0, 0.5)

        start = st.button(
            "▶️ 議論スタート",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.running,
        )
        random_start = st.button(
            "🎲 ランダム議論！",
            type="secondary",
            use_container_width=True,
            disabled=st.session_state.running,
            help="お題・キャラ・パラメータを全てランダムに決めて議論を開始します",
        )

        if not _is_multi_user_mode():
            st.markdown("---")
            st.subheader("📜 過去ログ")
            log_files = _list_past_logs()
            if log_files:
                log_labels = ["（選択してください）"] + [p.stem for p in log_files]
                picked = st.selectbox(
                    "過去ログ", log_labels, label_visibility="collapsed"
                )
                if picked != "（選択してください）":
                    st.session_state.viewing_log = next(
                        p for p in log_files if p.stem == picked
                    )
                else:
                    st.session_state.viewing_log = None
            else:
                st.caption("まだログがありません")
        st.markdown("---")
        _render_help_panel(expanded=False)

        return {
            "topic": topic,
            "persona_a": persona_a,
            "persona_b": persona_b,
            "max_rounds": max_rounds,
            "interval": interval,
            "delay": delay,
            "start": start,
            "random_start": random_start,
        }


def _render_past_log(log_path: Path) -> None:
    st.subheader(f"📜 {log_path.stem}")
    st.markdown(log_path.read_text(encoding="utf-8"))
    if st.button("← 閉じる"):
        st.session_state.viewing_log = None
        st.rerun()


def _render_intro() -> None:
    st.title("🎙 AI議論")
    st.caption("Gemini同士が自律的に議論して結論を出すツール")

    st.markdown(
        """
<div style="padding: 22px 26px; margin: 18px 0; border-radius: 12px;
            background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
            border-left: 6px solid #2563eb;">
  <div style="font-weight: 700; font-size: 1.05rem; color: #1e3a8a; margin-bottom: 12px;">
    👇 使い方（3ステップ）
  </div>
  <ol style="margin: 0; padding-left: 22px; color: #1e40af; line-height: 1.9;">
    <li>左サイドバーの <strong>「お題」</strong> に話したい議題を入力</li>
    <li>必要であれば <strong>「キャラ A・B」</strong> を選択（デフォルトのままでもOK）</li>
    <li><strong>▶️ 議論スタート</strong> をクリック</li>
  </ol>
  <div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed #93c5fd;
              color: #1e40af; font-size: 0.9rem;">
    🎲 何でも良いから試したい時は、サイドバー下部の <strong>「ランダム議論！」</strong> ボタンが便利です。
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    with cols[0]:
        st.metric("利用可能キャラ", f"{len(PERSONAS) - 1} + カスタム")
    with cols[1]:
        st.metric("使用モデル", "Gemini 3.1 Flash-Lite")

    st.markdown("---")
    _render_help_panel(expanded=False)


def _randomize_cfg(cfg: dict) -> dict:
    """お題・キャラ・パラメータを全てランダムに上書きする。"""
    keys_no_custom = [k for k in PERSONAS.keys() if k != CUSTOM_KEY]
    a_key, b_key = random.sample(keys_no_custom, 2)
    return {
        **cfg,
        "topic": random.choice(RANDOM_TOPICS),
        "persona_a": PERSONAS[a_key],
        "persona_b": PERSONAS[b_key],
        "max_rounds": random.randint(5, 10),
        "interval": random.randint(2, 4),
        "delay": round(random.uniform(1.0, 2.5), 1),
    }


def _run_dialogue(cfg: dict) -> None:
    st.session_state.running = True

    # === お題（最も目立つ大きなパネル） ===
    st.markdown(
        f"""
<div style="
    background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
    padding: 26px 32px;
    border-radius: 14px;
    margin: 14px 0 22px 0;
    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.3);
">
  <div style="color: #bfdbfe; font-size: 0.78rem; font-weight: 700;
              letter-spacing: 0.18em; margin-bottom: 12px; text-transform: uppercase;">
    📋 お 題
  </div>
  <div style="color: #ffffff; font-size: 1.45rem; font-weight: 600;
              line-height: 1.55;">
    {html.escape(cfg["topic"])}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # === 議論ヘッダ（お題より控えめ） ===
    st.subheader(
        f"💬 議論: {cfg['persona_a']['label']}   vs   {cfg['persona_b']['label']}"
    )
    st.caption(
        f"⚙️ 最大 {cfg['max_rounds']} 往復 / "
        f"{cfg['interval']} 往復ごとにファシリテーター介入 / "
        f"発言間 {cfg['delay']} 秒"
    )

    chat_container = st.container()
    status_container = st.container()
    events_log: list[dict] = []
    pending_placeholder = None  # 「考え中」用の差し替えスロット

    def _show_thinking(ev: dict):
        """次の発言が来るまで「考え中...」を表示するプレースホルダを作る。"""
        nonlocal pending_placeholder
        pending_placeholder = chat_container.empty()
        with pending_placeholder.container():
            with st.chat_message("assistant", avatar=ev.get("emoji", "💭")):
                st.caption(f"・ {ev.get('role', '')}")
                st.markdown(f"_{ev.get('message', '考え中...')}_")

    def _swap_into_placeholder(render_fn):
        """thinking placeholder の中身を実際の発言で置き換える。"""
        nonlocal pending_placeholder
        if pending_placeholder is None:
            return False
        with pending_placeholder.container():
            render_fn()
        pending_placeholder = None
        return True

    def _clear_placeholder():
        nonlocal pending_placeholder
        if pending_placeholder is not None:
            pending_placeholder.empty()
            pending_placeholder = None

    try:
        for ev in dialogue_events(
            cfg["topic"],
            cfg["persona_a"],
            cfg["persona_b"],
            max_rounds=cfg["max_rounds"],
            intervention_interval=cfg["interval"],
            delay_sec=cfg["delay"],
        ):
            events_log.append(ev)
            t = ev.get("type")

            if t == "thinking":
                _show_thinking(ev)

            elif t == "turn":
                def _render_turn(_ev=ev):
                    role = "user" if _ev["persona"] == "A" else "assistant"
                    with st.chat_message(role, avatar=_ev["emoji"]):
                        st.caption(f"ターン{_ev['round']} ・ {_ev['name']}")
                        st.write(_ev["text"])
                if not _swap_into_placeholder(_render_turn):
                    _render_event(ev, chat_container)

            elif t == "facilitator":
                def _render_fac(_ev=ev):
                    with st.chat_message("ai", avatar="🎤"):
                        st.caption(f"ファシリテーター介入（{_ev['round']}往復経過）")
                        st.info(_ev["text"])
                if not _swap_into_placeholder(_render_fac):
                    _render_event(ev, chat_container)

            elif t == "summary":
                _clear_placeholder()
                _render_event(ev, status_container)

            elif t in {"agreement", "end", "error"}:
                _clear_placeholder()
                _render_event(ev, status_container)

            elif t == "retry":
                # placeholder はそのまま（待機後に再開）、retry通知だけ表示
                _render_event(ev, status_container)

            else:
                _render_event(ev, chat_container)
    finally:
        from datetime import datetime as _dt
        log_md = build_log_markdown(
            events_log,
            cfg["topic"],
            cfg["persona_a"]["name"],
            cfg["persona_b"]["name"],
        )
        if _is_multi_user_mode():
            # クラウド共有モード: ディスクには保存しない（誰も見られないため無駄）
            timestamp = _dt.now().strftime("%Y-%m-%d_%H%M%S")
            log_filename = f"{timestamp}_dialogue.md"
            st.session_state.last_log_path = None
        else:
            # ローカル: ディスクに保存して履歴に残す
            log_path = save_log(
                events_log,
                cfg["topic"],
                cfg["persona_a"]["name"],
                cfg["persona_b"]["name"],
            )
            log_filename = log_path.name
            st.session_state.last_log_path = log_path
        st.session_state.last_log_md = log_md
        st.session_state.last_log_name = log_filename
        st.session_state.running = False

    st.markdown("---")
    st.subheader("📥 議論ログのダウンロード")
    st.download_button(
        "議論ログをダウンロード",
        data=log_md.encode("utf-8"),
        file_name=log_filename,
        mime="text/markdown",
        type="primary",
    )
    st.caption(
        "💾 議論ログは画面を離れると参照できなくなります。"
        "手元に残したい場合は、上のボタンからダウンロードしてください。"
    )


def main() -> None:
    if not _check_password():
        return
    _init_state()
    cfg = _sidebar()
    _render_warning_banner()

    if st.session_state.viewing_log:
        _render_past_log(st.session_state.viewing_log)
    elif cfg["start"] or cfg["random_start"]:
        if cfg["random_start"]:
            cfg = _randomize_cfg(cfg)
            st.info(
                "🎲 ランダムモード: お題・キャラ・パラメータを抽選しました。"
            )
        with st.spinner("Gemini API の利用可否を確認しています..."):
            ok, message, code = check_api_availability()
        if not ok:
            st.title("🎙 AI議論")
            st.error("❌ Gemini API が現在利用できません。議論を開始できません。")
            st.markdown(f"**理由:**\n\n{message}")
            with st.expander("エラーコード（詳細）"):
                st.code(code)
            return
        _run_dialogue(cfg)
    elif st.session_state.last_log_md:
        st.title("🎙 AI議論")
        st.success(f"前回のログ: {st.session_state.last_log_name}")
        st.download_button(
            "📥 前回のログをダウンロード",
            data=st.session_state.last_log_md.encode("utf-8"),
            file_name=st.session_state.last_log_name,
            mime="text/markdown",
        )
        st.markdown("---")
        st.markdown("左サイドバーで設定を変えて、もう一度議論を開始できる。")
    else:
        _render_intro()


if __name__ == "__main__":
    main()
