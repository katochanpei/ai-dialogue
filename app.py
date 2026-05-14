"""Streamlit UI: Gemini同士の自律対話を観戦するブラウザ画面。

Run:
    streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from dialogue_core import DEFAULT_TOPIC, dialogue_events, save_log
from personas import CUSTOM_KEY, DEFAULT_A_KEY, DEFAULT_B_KEY, PERSONAS


st.set_page_config(page_title="AI Dialogue", page_icon="🎙", layout="wide")


def _init_state() -> None:
    defaults = {
        "running": False,
        "last_log_path": None,
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
        name = st.text_input(
            f"キャラ{side} 名前", value="カスタム", key=f"persona_{side}_custom_name"
        )
        emoji = st.text_input(
            f"キャラ{side} 絵文字", value="✏️", key=f"persona_{side}_custom_emoji"
        )
        system = st.text_area(
            f"キャラ{side} システムプロンプト",
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
    elif t == "error":
        container.error(f"❌ {ev['text']}")


def _list_past_logs() -> list[Path]:
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    return sorted(log_dir.glob("*_dialogue.md"), reverse=True)


def _sidebar() -> dict:
    with st.sidebar:
        st.title("🎙 AI Dialogue")
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
            max_rounds = st.slider("最大往復数", 1, 30, 20)
            interval = st.slider("ファシリテーター介入間隔", 1, 10, 3)
            delay = st.slider("発言間スリープ(秒)", 0.0, 5.0, 2.0, 0.5)

        start = st.button(
            "▶️ 議論スタート",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.running,
        )

        st.markdown("---")
        st.subheader("📜 過去ログ")
        log_files = _list_past_logs()
        if log_files:
            log_labels = ["（選択してください）"] + [p.stem for p in log_files]
            picked = st.selectbox("過去ログ", log_labels, label_visibility="collapsed")
            if picked != "（選択してください）":
                st.session_state.viewing_log = next(
                    p for p in log_files if p.stem == picked
                )
            else:
                st.session_state.viewing_log = None
        else:
            st.caption("まだログがありません")

        return {
            "topic": topic,
            "persona_a": persona_a,
            "persona_b": persona_b,
            "max_rounds": max_rounds,
            "interval": interval,
            "delay": delay,
            "start": start,
        }


def _render_past_log(log_path: Path) -> None:
    st.subheader(f"📜 {log_path.stem}")
    st.markdown(log_path.read_text(encoding="utf-8"))
    if st.button("← 閉じる"):
        st.session_state.viewing_log = None
        st.rerun()


def _render_intro() -> None:
    st.title("🎙 AI Dialogue")
    st.markdown(
        """
左のサイドバーでお題とキャラA/Bを選んで、**▶️ 議論スタート** を押してな。

- Gemini同士が自律的に議論して、合意するまで進む
- 3往復ごとにファシリテーターが論点を整理
- 全部ターミナルやなくてここで観戦できる
- 終わったらログが `logs/` に保存される
        """
    )

    cols = st.columns(3)
    with cols[0]:
        st.metric("キャラ数", f"{len(PERSONAS) - 1} + カスタム")
    with cols[1]:
        st.metric("モデル", "Gemini 2.5 Flash")
    with cols[2]:
        st.metric("過去ログ", f"{len(_list_past_logs())}件")


def _run_dialogue(cfg: dict) -> None:
    st.session_state.running = True
    st.subheader("お題")
    st.info(cfg["topic"])
    st.subheader(
        f"対決: {cfg['persona_a']['label']}   vs   {cfg['persona_b']['label']}"
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
            if ev.get("type") in {"agreement", "end", "error"}:
                _render_event(ev, status_container)
            else:
                _render_event(ev, chat_container)
    finally:
        log_path = save_log(
            events_log,
            cfg["topic"],
            cfg["persona_a"]["name"],
            cfg["persona_b"]["name"],
        )
        st.session_state.last_log_path = log_path
        st.session_state.running = False

    with open(log_path, "rb") as f:
        st.download_button(
            "📥 ログをダウンロード",
            data=f,
            file_name=log_path.name,
            mime="text/markdown",
        )


def main() -> None:
    _init_state()
    cfg = _sidebar()

    if st.session_state.viewing_log:
        _render_past_log(st.session_state.viewing_log)
    elif cfg["start"]:
        _run_dialogue(cfg)
    elif st.session_state.last_log_path:
        st.title("🎙 AI Dialogue")
        st.success(f"前回のログ: {st.session_state.last_log_path.name}")
        with open(st.session_state.last_log_path, "rb") as f:
            st.download_button(
                "📥 前回のログをダウンロード",
                data=f,
                file_name=st.session_state.last_log_path.name,
                mime="text/markdown",
            )
        st.markdown("---")
        st.markdown("左サイドバーで設定を変えて、もう一度議論を開始できる。")
    else:
        _render_intro()


if __name__ == "__main__":
    main()
