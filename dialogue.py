"""CLI: Gemini同士の自律対話システム。

Usage:
    python dialogue.py                                          # 対話入力 or デフォルト
    python dialogue.py "リモートワーク是非"                       # お題指定
    python dialogue.py "お題" --persona-a engineer --persona-b child
    python dialogue.py --list-personas                          # キャラ一覧表示
"""
from __future__ import annotations

import argparse
import sys

from dialogue_core import DEFAULT_TOPIC, dialogue_events, save_log
from personas import DEFAULT_A_KEY, DEFAULT_B_KEY, PERSONAS


def _print_event(ev: dict) -> None:
    t = ev.get("type")
    if t == "topic":
        print(f"\n=== お題 ===\n{ev['text']}\n")
    elif t == "turn":
        print(f"\n## ターン{ev['round']} - {ev['emoji']} {ev['name']}\n")
        print(ev["text"])
    elif t == "facilitator":
        print(f"\n## 🎤 ファシリテーター介入（{ev['round']}往復経過）\n")
        print(ev["text"])
    elif t == "agreement":
        print(f"\n## ✅ 合意成立（{ev['round']}往復）\n")
    elif t == "end":
        print(f"\n## ⏱ 最大往復数 {ev['round']} に到達して終了\n")
    elif t == "summary":
        print("\n" + "=" * 60)
        print("📋 結論ブリーフィング")
        print("=" * 60 + "\n")
        print(ev["text"])
        print()
    elif t == "error":
        print(f"\n❌ {ev['text']}", file=sys.stderr)


def _list_personas() -> None:
    print("利用可能なキャラ:")
    for key, p in PERSONAS.items():
        print(f"  {key:12s} {p['label']}")


def _resolve_topic(args) -> str:
    if args.topic:
        return " ".join(args.topic)
    if not args.no_prompt and sys.stdin.isatty():
        try:
            entered = input("お題を入力（Enterでデフォルト）:\n> ").strip()
        except EOFError:
            entered = ""
        return entered or DEFAULT_TOPIC
    return DEFAULT_TOPIC


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gemini同士で勝手に議論させるAI対話システム",
    )
    parser.add_argument("topic", nargs="*", help="議論のお題")
    parser.add_argument(
        "--persona-a",
        default=DEFAULT_A_KEY,
        choices=list(PERSONAS.keys()),
        help=f"キャラA（既定: {DEFAULT_A_KEY}）",
    )
    parser.add_argument(
        "--persona-b",
        default=DEFAULT_B_KEY,
        choices=list(PERSONAS.keys()),
        help=f"キャラB（既定: {DEFAULT_B_KEY}）",
    )
    parser.add_argument("--rounds", type=int, default=20, help="最大往復数")
    parser.add_argument("--interval", type=int, default=3, help="ファシリテーター介入間隔")
    parser.add_argument("--delay", type=float, default=2.0, help="発言間スリープ秒数")
    parser.add_argument("--no-prompt", action="store_true", help="お題対話入力を抑止")
    parser.add_argument("--list-personas", action="store_true", help="キャラ一覧を表示して終了")
    args = parser.parse_args()

    if args.list_personas:
        _list_personas()
        return 0

    topic = _resolve_topic(args)
    persona_a = PERSONAS[args.persona_a]
    persona_b = PERSONAS[args.persona_b]

    events_log: list[dict] = []
    for ev in dialogue_events(
        topic,
        persona_a,
        persona_b,
        max_rounds=args.rounds,
        intervention_interval=args.interval,
        delay_sec=args.delay,
    ):
        events_log.append(ev)
        _print_event(ev)

    log_path = save_log(events_log, topic, persona_a["name"], persona_b["name"])
    print(f"\n📝 ログ保存: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
