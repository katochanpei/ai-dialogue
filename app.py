"""Streamlit UI: Gemini同士の自律対話を観戦するブラウザ画面。

Run:
    streamlit run app.py
"""
from __future__ import annotations

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
            "ADMIN_PASSWORD",
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


# === Sidebar styling: 幅を広げ、フォントを小さく ===
st.markdown(
    """
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
    /* ネオングリーンの「ランダム議論」ボタン（サイドバー内のsecondaryボタン全般を対象） */
    section[data-testid="stSidebar"] button[kind="secondary"] {
        background: linear-gradient(135deg, #39ff14, #00e676) !important;
        color: #000 !important;
        border: 2px solid #00c853 !important;
        font-weight: 700 !important;
        box-shadow: 0 0 10px rgba(57, 255, 20, 0.6) !important;
        transition: all 0.2s ease !important;
    }
    section[data-testid="stSidebar"] button[kind="secondary"]:hover {
        background: linear-gradient(135deg, #00e676, #39ff14) !important;
        box-shadow: 0 0 16px rgba(57, 255, 20, 0.9) !important;
        transform: translateY(-1px) !important;
    }
</style>
""",
    unsafe_allow_html=True,
)


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
- 全員合計で**1日1000リクエスト**が上限（Gemini 2.5 Flash-Lite）
- 1議論あたり 10〜20リクエスト消費
- 上限を超えるとその日は使用できません（翌朝復活）

### 🧰 中身の技術
- モデル: **Gemini 2.5 Flash-Lite**
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
    """パスワード認証。APP_PASSWORD 未設定なら認証スキップ（ローカル開発時）。

    ADMIN_PASSWORD を入れると管理者モード（過去ログ閲覧可）になる。
    UI上は通常と同じパスワード入力欄。
    """
    expected = os.environ.get("APP_PASSWORD", "")
    admin_pw = os.environ.get("ADMIN_PASSWORD", "")
    if not expected:
        return True
    if st.session_state.get("authenticated"):
        return True

    st.title("🎙 AI議論")
    st.caption("社内向け Gemini × Gemini 議論ツール")
    pw = st.text_input("パスワード", type="password", key="_pw_input")
    if st.button("ログイン", type="primary"):
        if admin_pw and pw == admin_pw:
            st.session_state.authenticated = True
            st.session_state.is_admin = True
            st.rerun()
        elif pw == expected:
            st.session_state.authenticated = True
            st.session_state.is_admin = False
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


def _init_state() -> None:
    defaults = {
        "running": False,
        "is_admin": False,
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
        topic = st.text_area(
            "お題",
            value=DEFAULT_TOPIC,
            label_visibility="collapsed",
            height=110,
            key="topic_input",
        )

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

        is_admin = st.session_state.get("is_admin", False)
        show_past_logs = is_admin or not _is_multi_user_mode()

        if show_past_logs:
            st.markdown("---")
            if is_admin and _is_multi_user_mode():
                st.caption("🕵️ 管理者モード（全員のログを閲覧可）")
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
    st.markdown(
        """
左のサイドバーでお題とキャラA/Bを選んで、**▶️ 議論スタート** を押してください。

- Gemini同士が自律的に議論して、合意するまで進む
- 3往復ごとにファシリテーターが論点を整理
- ターミナルではなく、ここで観戦できる
- 終了後はログが `logs/` に保存される
        """
    )

    cols = st.columns(3)
    with cols[0]:
        st.metric("キャラ数", f"{len(PERSONAS) - 1} + カスタム")
    with cols[1]:
        st.metric("モデル", "Gemini 2.5 Flash-Lite")
    with cols[2]:
        st.metric("過去ログ", f"{len(_list_past_logs())}件")

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
    st.subheader("お題")
    st.info(cfg["topic"])
    st.subheader(
        f"対決: {cfg['persona_a']['label']}   vs   {cfg['persona_b']['label']}"
    )
    st.caption(
        f"⚙️ 最大 {cfg['max_rounds']} 往復 / "
        f"{cfg['interval']} 往復ごとにファシリテーター介入 / "
        f"発言間 {cfg['delay']} 秒"
    )

    chat_container = st.container()
    status_container = st.container()
    events_log: list[dict] = []

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
            if ev.get("type") in {"agreement", "end", "error", "summary"}:
                _render_event(ev, status_container)
            else:
                _render_event(ev, chat_container)
    finally:
        log_md = build_log_markdown(
            events_log,
            cfg["topic"],
            cfg["persona_a"]["name"],
            cfg["persona_b"]["name"],
        )
        # ログは常にディスクに保存（管理者が後で閲覧できるように）。
        # ただし一般ユーザーUI上は隠れる（MULTI_USER_MODE時）。
        log_path = save_log(
            events_log,
            cfg["topic"],
            cfg["persona_a"]["name"],
            cfg["persona_b"]["name"],
        )
        st.session_state.last_log_path = log_path
        st.session_state.last_log_md = log_md
        st.session_state.last_log_name = log_path.name
        st.session_state.running = False

    st.markdown("---")
    st.subheader("📥 議論ログのダウンロード")
    st.download_button(
        "議論ログをダウンロード",
        data=log_md.encode("utf-8"),
        file_name=log_path.name,
        mime="text/markdown",
        type="primary",
    )
    st.caption(
        "議論内容は他のユーザーから閲覧できません。"
        "必要であれば、いま このタイミングでダウンロードしてください。"
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
