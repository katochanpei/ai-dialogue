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
from personas import CUSTOM_KEY, DEFAULT_A_KEY, DEFAULT_B_KEY, PERSONAS, RANDOM_KEY  # noqa: E402


st.set_page_config(page_title="AI議論", page_icon="🎙", layout="wide")


def _generate_aurora_palette() -> dict[str, str]:
    """パステル系オーロラ4色パレットを生成（明るく華やか）。

    色相環からおおむね 90 度ずつ離れた 4 色をランダムに選ぶ。
    彩度はやや控えめ、明度はかなり高めで「パステル × 明るい」配色。
    """
    hue_start = random.randint(0, 360)
    palette: dict[str, str] = {}
    for i in range(4):
        hue = (hue_start + i * 90 + random.randint(-15, 15)) % 360
        sat = random.randint(65, 85)
        light = random.randint(76, 88)
        alpha = round(random.uniform(0.92, 1.0), 2)
        palette[f"C{i + 1}"] = f"hsla({hue},{sat}%,{light}%,{alpha})"
    return palette


# セッション中は色を固定。新しいセッションで色変わる。
if "aurora_palette" not in st.session_state:
    st.session_state["aurora_palette"] = _generate_aurora_palette()
_AURORA = st.session_state["aurora_palette"]


# === Main UI styling: Figma準拠の派手アーケード調 ===
_SIDEBAR_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&display=swap" rel="stylesheet">
<style>
    /* サイドバー非表示 + メインを左右真ん中に */
    section[data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    [data-testid="stMain"] {
        margin-left: 0 !important;
        width: 100% !important;
        align-items: center !important;
    }
    [data-testid="stAppViewContainer"] > section {
        margin-left: 0 !important;
    }

    /* メイン中央寄せ：タイトルは広く、フォームは狭く */
    [data-testid="stMainBlockContainer"],
    .main .block-container {
        max-width: 820px !important;
        padding-top: 3rem !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }

    /* お題テキストエリアは少し内側に絞ってタイトルより狭く見せる */
    div[data-testid="stTextArea"] {
        max-width: 660px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    [data-testid="stTextArea"] textarea {
        font-size: 1.05rem !important;
        line-height: 1.55 !important;
        min-height: 160px !important;
    }
    .stApp textarea::placeholder,
    div[data-testid="stTextArea"] textarea::placeholder {
        color: rgba(255, 255, 255, 0.30) !important;
        opacity: 1 !important;
        -webkit-text-fill-color: rgba(255, 255, 255, 0.30) !important;
    }

    /* セレクトボックスのラベル：控えめに */
    div[data-testid="stSelectbox"] label,
    div[data-testid="stSelectbox"] label p {
        font-size: 11px !important;
        color: rgba(255, 255, 255, 0.5) !important;
        font-weight: 500 !important;
    }

    /* === ボタン共通：ピル型、常識的なサイズの普通フォント === */
    div[data-testid="stButton"] button {
        border-radius: 999px !important;
        padding: 10px 20px !important;
        font-family: 'Inter', 'Helvetica Neue', sans-serif !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        letter-spacing: 0 !important;
        white-space: nowrap !important;
        line-height: 1.4 !important;
        min-height: auto !important;
        justify-content: center !important;
        text-align: center !important;
    }
    div[data-testid="stButton"] button p {
        font-family: 'Inter', 'Helvetica Neue', sans-serif !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
        text-align: center !important;
    }

    /* プライマリボタン（議論スタート）：オーロラ */
    @keyframes auroraDrift {
        0%   { background-position:   0%   0%; }
        25%  { background-position: 100%   0%; }
        50%  { background-position: 100% 100%; }
        75%  { background-position:   0% 100%; }
        100% { background-position:   0%   0%; }
    }
    @keyframes auroraGlow {
        0%, 100% {
            box-shadow:
                0 0 14px rgba(255, 255, 255, 0.22),
                inset 0 0 14px rgba(255, 255, 255, 0.08);
        }
        50% {
            box-shadow:
                0 0 30px rgba(255, 255, 255, 0.45),
                inset 0 0 22px rgba(255, 255, 255, 0.18);
        }
    }
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #f8f5ff !important;
        background-image:
            radial-gradient(at 20% 20%, __AURORA_C1__ 0%, transparent 55%),
            radial-gradient(at 80% 25%, __AURORA_C2__ 0%, transparent 55%),
            radial-gradient(at 75% 80%, __AURORA_C3__ 0%, transparent 55%),
            radial-gradient(at 25% 80%, __AURORA_C4__ 0%, transparent 55%) !important;
        background-size: 200% 200% !important;
        animation:
            auroraDrift 6s ease-in-out infinite,
            auroraGlow 2.7s ease-in-out infinite !important;
        color: #000000 !important;
        border: 2px solid rgba(255, 255, 255, 0.6) !important;
        transition: transform 0.2s ease !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        animation:
            auroraDrift 3s ease-in-out infinite,
            auroraGlow 1.3s ease-in-out infinite !important;
        transform: translateY(-1px) scale(1.02) !important;
    }

    /* 戻るアクション（底部）：薄い枠付き控えめボタン
       body 先頭付け＋[kind="secondary"] 末尾付けで特異性を上げ、
       オーロラの kind="secondary" スタイルに勝つように */
    body [data-testid="element-container"]:has(.back-action-wrap)
        + [data-testid="element-container"] button[kind="secondary"] {
        background: transparent !important;
        background-image: none !important;
        background-color: transparent !important;
        animation: none !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        color: rgba(255, 255, 255, 0.7) !important;
        padding: 10px 20px !important;
        min-height: auto !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        box-shadow: none !important;
        border-radius: 8px !important;
        letter-spacing: 0 !important;
        text-shadow: none !important;
    }
    body [data-testid="element-container"]:has(.back-action-wrap)
        + [data-testid="element-container"] button[kind="secondary"] p {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        color: rgba(255, 255, 255, 0.7) !important;
    }
    body [data-testid="element-container"]:has(.back-action-wrap)
        + [data-testid="element-container"] button[kind="secondary"]:hover {
        background: rgba(255, 255, 255, 0.06) !important;
        background-image: none !important;
        border-color: rgba(255, 255, 255, 0.4) !important;
        animation: none !important;
        transform: none !important;
    }

    /* トップ左の戻るリンク：純粋な <a> タグ。button 要素ではないので
       Streamlit のボタンスタイルと一切競合しない */
    a.back-top-link {
        color: rgba(255, 255, 255, 0.5) !important;
        font-size: 16px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 400 !important;
        text-decoration: none !important;
        display: inline-block;
        padding: 4px 8px;
    }
    a.back-top-link:hover {
        color: rgba(255, 255, 255, 0.85) !important;
        text-decoration: none !important;
    }

    /* === セカンダリボタン（ランダム議論）：単色インディゴ、アニメ無し === */
    div[data-testid="stButton"] button[kind="secondary"] {
        background: #6366f1 !important;
        background-image: none !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: none !important;
        animation: none !important;
        transition: background-color 0.15s ease, transform 0.15s ease !important;
    }
    div[data-testid="stButton"] button[kind="secondary"] p {
        color: #ffffff !important;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        background: #7c7af2 !important;
        background-image: none !important;
        transform: translateY(-1px) scale(1.02) !important;
    }

    /* === エクスパンダー：薄い枠線つき、角丸 === */
    [data-testid="stExpander"] {
        border: 1px solid rgba(255, 255, 255, 0.10) !important;
        border-radius: 8px !important;
        background: transparent !important;
        overflow: hidden !important;
    }
    [data-testid="stExpander"] details {
        border: none !important;
        background: transparent !important;
    }
    [data-testid="stExpander"] details > summary {
        padding: 10px 16px !important;
        font-size: 13px !important;
        border: none !important;
    }
    [data-testid="stExpander"] details > summary p {
        font-size: 13px !important;
    }

    /* ボタン間スペーサ（PC基準値、スマホで縮める） */
    .btn-gap { height: 12px; }

    /* ランダムボタン直前のマーカー（::before で🎲を出す目印） */
    .random-btn-wrap { display: none; }

    /* ランダムボタンの先頭に🎲を文字より大きく表示（PC / スマホ共通） */
    body [data-testid="element-container"]:has(.random-btn-wrap)
        + [data-testid="element-container"] button[kind="secondary"]::before {
        content: "🎲";
        font-size: 1.45em;
        line-height: 1;
        margin-right: 10px;
        vertical-align: -2px;
        display: inline-block;
    }

    /* スマホ：VSの上下を更に詰める／ボタンを高め・幅80%・隙間半減 */
    @media (max-width: 768px) {
        /* スマホ時のみボタンラッパーを flex 中央寄せ（PCでは use_container_width が効くので触らない） */
        div[data-testid="stButton"] {
            display: flex !important;
            justify-content: center !important;
        }
        .ai-giron-vs {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            margin: 0 !important;
            font-size: 18px !important;
            line-height: 1 !important;
        }
        /* VS を含む列ブロックの上下余白を圧縮 */
        div[data-testid="stColumn"]:has(.ai-giron-vs) {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            margin-top: -10px !important;
            margin-bottom: -10px !important;
        }
        /* スタート／ランダムボタン：高さ 1.5倍、幅 80%、中央寄せ */
        div[data-testid="stButton"] button[kind="primary"],
        div[data-testid="stButton"] button[kind="secondary"] {
            padding-top: 18px !important;
            padding-bottom: 18px !important;
            width: 80% !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        /* 戻る系（back-action-wrap 直後）の secondary は対象外に戻す */
        body [data-testid="element-container"]:has(.back-action-wrap)
            + [data-testid="element-container"] button[kind="secondary"] {
            padding-top: 10px !important;
            padding-bottom: 10px !important;
            width: auto !important;
        }
        /* ボタン間スペーサを半減 */
        .btn-gap { height: 6px !important; }
    }

    .ai-giron-title-main {
        font-family: 'Dela Gothic One', sans-serif !important;
        font-size: 38px !important;
        color: white !important;
        text-align: center;
        margin: 14px auto 4px auto !important;
        line-height: 1.1;
        white-space: nowrap !important;
        width: fit-content !important;
        display: block !important;
    }
    .ai-giron-title-login {
        font-family: 'Dela Gothic One', sans-serif !important;
        font-size: 76px !important;
        color: white !important;
        text-align: center;
        margin: 18px 0 0px 0 !important;
        line-height: 1.1;
        white-space: nowrap !important;
    }
    .ai-giron-vs {
        font-family: 'Dela Gothic One', sans-serif !important;
        font-size: 24px;
        color: white;
        text-align: center;
        padding-top: 28px;
    }
</style>
"""
_aurora_css = _SIDEBAR_CSS
for _k, _v in _AURORA.items():
    _aurora_css = _aurora_css.replace(f"__AURORA_{_k}__", _v)
st.markdown(_aurora_css, unsafe_allow_html=True)


HELP_MARKDOWN = """
<div style="font-size: 0.86rem; color: rgba(255,255,255,0.65); line-height: 1.7;">

**🎯 何ができるか**

お題を与えると、2人のAIキャラが自律的に議論して合意に至ります。3往復ごとにファシリテーターAIが論点を整理し、議論終了後は要約と次のアクションを提案します。

**⚙️ 動作の仕組み**

ブラウザ → Streamlit Cloud → Google Gemini API、という流れで動作します。
キャラA（提案役）／キャラB（反論役）／ファシリテーター／要約役 の4人のGeminiが連携。
同じGeminiでも違う性格設定（システムプロンプト）を与えると、別人格として振る舞います。

**⚠️ データ送信に関する注意**

お題・キャラ設定・議論の内容はすべて Google のサーバに送信され、保存される可能性があります。
無料プラン使用時、Google がモデル改善に使用する場合があります。

入力しないでください:
- 社外秘・社内秘情報
- 個人情報・顧客データ
- 未公開の経営情報、契約情報
- パスワード・APIキー等

ブレストや雑談、公開情報ベースのお題でのみご利用ください。

**📊 仕様・制限**

- モデル: Gemini 3.1 Flash-Lite
- 利用可能キャラ: 12 + カスタム
- 1日上限: 数百〜千リクエスト程度（全員合計、無料枠）
- 1議論あたり: 10〜20リクエスト消費
- 上限を超えるとその日は使用できません（翌朝復活）
- UI: Streamlit / ホスティング: Streamlit Community Cloud
- ソース: <a href="https://github.com/katochanpei/ai-dialogue" style="color: rgba(255,255,255,0.8);">github.com/katochanpei/ai-dialogue</a>

</div>
"""


def _render_help_panel(expanded: bool = False) -> None:
    """仕組みの解説パネル。注意点・仕様も含む。"""
    with st.expander("ℹ️ このツールについて（仕組み・注意点・仕様）", expanded=expanded):
        st.markdown(HELP_MARKDOWN, unsafe_allow_html=True)


def _check_password() -> bool:
    """パスワード認証。APP_PASSWORD 未設定なら認証スキップ（ローカル開発時）。"""
    expected = os.environ.get("APP_PASSWORD", "")
    if not expected:
        return True
    if st.session_state.get("authenticated"):
        return True

    # ログイン画面ではサイドバーを非表示にしてスッキリ
    st.markdown(
        """
<style>
    section[data-testid="stSidebar"] { display: none !important; }

/* メインを縦横ど真ん中に */
[data-testid="stMain"] {
    min-height: 100vh !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
}

[data-testid="stMainBlockContainer"],
.main .block-container {
    max-width: 420px !important;
    padding-top: 1rem !important;
    padding-bottom: 1rem !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # 中央のカード型ログインフォーム
    st.markdown(
        """
<div style="display: flex; flex-direction: column; align-items: center; gap: 8px; padding-top: 8px;">
  <!-- 1行目: 🗣️ 🗣️ -->
  <div style="display: flex; gap: clamp(8px, 3vw, 24px); align-items: center;">
    <span style="font-size: clamp(64px, 18vw, 128px); line-height: 0.75;">🗣️</span>
    <span style="display: inline-block; transform: scaleX(-1);
                 font-size: clamp(64px, 18vw, 128px); line-height: 0.75;">🗣️</span>
  </div>
  <!-- 2行目: AI議論! -->
  <div class="ai-giron-title-login">AI議論!</div>
  <!-- サブタイトル -->
  <p style="color: rgba(255,255,255,0.55); font-size: 0.88rem; margin: 10px 0 80px 0; text-align: center;">
    Gemini × Gemini 議論ツール
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.form("login_form", clear_on_submit=False, border=False):
        pw = st.text_input(
            "パスワード",
            type="password",
            placeholder="パスワードを入力",
            label_visibility="collapsed",
            key="_pw_input",
        )
        submitted = st.form_submit_button(
            "ログイン",
            type="primary",
            use_container_width=True,
        )
        if submitted:
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
        "議論する人格を選択",
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

    return PERSONAS[selected_key]


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


def _main_form() -> dict:
    """中央寄せの ChatGPT 風メインフォーム。お題が主役。"""
    # === セクション1: タイトル + サブタイトル ===
    st.markdown(
        """
<div style="display: flex; flex-direction: column; align-items: center;
            gap: 8px; padding-top: 24px; margin-bottom: 18px;">
  <!-- 1行目: 🗣️ 🗣️←反転 -->
  <div style="display: flex; gap: clamp(8px, 3vw, 24px); align-items: center;">
    <span style="font-size: clamp(48px, 12vw, 72px); line-height: 0.75;">🗣️</span>
    <span style="display: inline-block; transform: scaleX(-1);
                 font-size: clamp(48px, 12vw, 72px); line-height: 0.75;">🗣️</span>
  </div>
  <!-- 2行目: AI議論! -->
  <div class="ai-giron-title-main">AI議論!</div>
  <!-- サブタイトル -->
  <p style="color: rgba(255,255,255,0.55); font-size: 0.82rem; margin: 6px 0 0 0; text-align: center;">
    Gemini × Gemini 議論ツール
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    # === セクション間スペース（タイトル → フォーム） ===
    st.markdown('<div style="height: 16px;"></div>', unsafe_allow_html=True)

    # === セクション2: 入力フォーム本体 ===
    # お題テキストエリア（プレースホルダで入力を促す）
    topic_input = st.text_area(
        "お題",
        value="",
        placeholder="Gemini × Gemini に議論してもらいたいお題を入力してください…（空のまま開始するとサンプルお題で議論します）",
        height=160,
        key="topic_input",
        label_visibility="collapsed",
        help="空のまま「議論スタート！」を押すと、サンプルお題で開始します。",
    )
    topic = topic_input.strip() or DEFAULT_TOPIC

    # ─── お題 → キャラ間の余白 ───
    st.markdown('<div style="height: 0px;"></div>', unsafe_allow_html=True)

    # キャラA / VS / キャラB
    col_a, col_vs, col_b = st.columns([298, 80, 298])
    with col_a:
        persona_a = _persona_selector("A", DEFAULT_A_KEY)
    with col_vs:
        st.markdown('<div class="ai-giron-vs">VS</div>', unsafe_allow_html=True)
    with col_b:
        persona_b = _persona_selector("B", DEFAULT_B_KEY)

    # ─── キャラ → ボタン間の余白 ───
    st.markdown('<div style="height: 36px;"></div>', unsafe_allow_html=True)

        # ボタン群（縦並び・中央寄せ）
    _, btn_center, _ = st.columns([1, 4, 1])
    with btn_center:
        start = st.button(
            "議論スタート！",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.running,
        )
        st.markdown('<div class="btn-gap"></div>', unsafe_allow_html=True)
        st.markdown('<div class="random-btn-wrap"></div>', unsafe_allow_html=True)
        random_start = st.button(
            "ランダム議論！",
            type="secondary",
            use_container_width=True,
            disabled=st.session_state.running,
            help="お題・キャラ・パラメータを全てランダムに決めて議論を開始します",
        )

    # === セクション間スペース（フォーム → 折りたたみ） ===
    st.markdown('<div style="height: 64px;"></div>', unsafe_allow_html=True)

    # === セクション3: 折りたたみ要素（詳細パラメータ／ヘルプ） ===
    st.markdown(
        """
<style>
  [data-testid="stExpander"] { margin-bottom: 0px !important; }
</style>
""",
        unsafe_allow_html=True,
    )
    with st.expander("⚙️ 詳細パラメータ", expanded=False):
        max_rounds = st.slider("最大往復", 1, 30, 20)
        interval = st.slider("ファシリテーター介入間隔", 1, 10, 3)
        delay = st.slider("発言間スリープ (秒)", 0.0, 5.0, 2.0, 0.5)

    if not _is_multi_user_mode():
        with st.expander("📜 過去ログ", expanded=False):
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


def _randomize_cfg(cfg: dict) -> dict:
    """お題・キャラ・パラメータを全てランダムに上書きする。"""
    keys_pool = [k for k in PERSONAS.keys() if k not in (CUSTOM_KEY, RANDOM_KEY)]
    a_key, b_key = random.sample(keys_pool, 2)
    return {
        **cfg,
        "topic": random.choice(RANDOM_TOPICS),
        "persona_a": PERSONAS[a_key],
        "persona_b": PERSONAS[b_key],
        "max_rounds": random.randint(5, 10),
        "interval": random.randint(2, 4),
        "delay": round(random.uniform(1.0, 2.5), 1),
    }


def _resolve_random_personas(cfg: dict) -> dict:
    """persona_a / persona_b の key が "random" のとき、実ペルソナへ解決する。

    両方ランダムなら 2 つ異なるキャラ、片方のみなら相手と被らないキャラを抽選する。
    """
    keys_pool = [k for k in PERSONAS.keys() if k not in (CUSTOM_KEY, RANDOM_KEY)]
    a_is_random = cfg["persona_a"].get("key") == RANDOM_KEY
    b_is_random = cfg["persona_b"].get("key") == RANDOM_KEY
    if not a_is_random and not b_is_random:
        return cfg
    new_cfg = dict(cfg)
    if a_is_random and b_is_random:
        a_key, b_key = random.sample(keys_pool, 2)
        new_cfg["persona_a"] = PERSONAS[a_key]
        new_cfg["persona_b"] = PERSONAS[b_key]
    elif a_is_random:
        used = cfg["persona_b"].get("key")
        choices = [k for k in keys_pool if k != used] or keys_pool
        new_cfg["persona_a"] = PERSONAS[random.choice(choices)]
    else:
        used = cfg["persona_a"].get("key")
        choices = [k for k in keys_pool if k != used] or keys_pool
        new_cfg["persona_b"] = PERSONAS[random.choice(choices)]
    return new_cfg


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


def _reset_dialogue_state() -> None:
    """議論完了後の状態をクリアしてフォームに戻すための初期化。"""
    for key in ("last_log_md", "last_log_name", "last_log_path"):
        if key in st.session_state:
            st.session_state[key] = None


def main() -> None:
    if not _check_password():
        return
    _init_state()

    # クエリパラメータ経由の「やっぱり戻る」リンク検出
    if "back" in st.query_params:
        _reset_dialogue_state()
        st.query_params.clear()
        st.rerun()

    if st.session_state.viewing_log:
        _render_past_log(st.session_state.viewing_log)
        return

    # フォームを差し替え可能なスロットに入れる
    form_slot = st.empty()
    with form_slot.container():
        cfg = _main_form()

    if cfg["start"] or cfg["random_start"]:
        # フォームを消して画面を議論専用に切り替える
        form_slot.empty()

        # 左上の戻るリンク（純粋な <a> タグ、button要素ではない）
        st.markdown(
            '<a href="?back=1" class="back-top-link">← やっぱり戻る</a>',
            unsafe_allow_html=True,
        )

        if cfg["random_start"]:
            cfg = _randomize_cfg(cfg)
            st.info("🎲 ランダムモード: お題・キャラ・パラメータを抽選しました。")

        cfg = _resolve_random_personas(cfg)

        with st.spinner("Gemini API の利用可否を確認しています..."):
            ok, message, code = check_api_availability()
        if not ok:
            st.error("❌ Gemini API が現在利用できません。議論を開始できません。")
            st.markdown(f"**理由:**\n\n{message}")
            with st.expander("エラーコード（詳細）"):
                st.code(code)
            return

        _run_dialogue(cfg)

        # 議論完了後：底部に控えめな戻るリンク
        st.markdown('<div style="height: 32px;"></div>', unsafe_allow_html=True)
        st.markdown('<div class="back-action-wrap"></div>', unsafe_allow_html=True)
        if st.button("← 新しい議論を始める", key="back_to_form_btn"):
            _reset_dialogue_state()
            st.rerun()


if __name__ == "__main__":
    main()
