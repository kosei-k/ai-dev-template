#!/usr/bin/env python3
"""PreToolUse(Edit|Write|MultiEdit) フック。「AIを止める境界」をローカルでも効かせる。

`.claude/project.toml` の `[[sanctuary.rule]]` に挙がったパスへの編集を検出したら
permissionDecision: "ask" を返し、理由を添えて人間に確認させる。
CI側の聖域(fixer)と同じ基準を、ローカルの手作業にも適用する。

拒否(deny)ではなく確認(ask)にしているのは、人間が意図して変更するケース
(その値を変更するPR作業そのもの)を塞がないため。機械的にブロックすべきものは
テスト弱体化検知の役目。

設定の書き方(.claude/project.toml):

    [[sanctuary.rule]]
    path = "config/config.toml"          # 末尾一致で判定する
    match = "\\b(limit|threshold)\\s*="  # 任意。この正規表現に当たる編集だけ止める
    reason = "この値は判断そのもの。根拠がADR・PRに書かれているか確認すること"

    [[sanctuary.rule]]
    path = "src/rules.py"
    symbols = ["def evaluate(", "def overall("]   # 任意。この文字列を含む編集だけ止める
    reason = "判定の心臓部。意味を変える変更は先にPlan PRを通すこと"

`match` も `symbols` も無い場合、そのファイルへの編集はすべて確認対象になる。
Write(全文置換)は常に確認対象。

**設定が壊れている場合は黙って素通りさせない。** `.claude/project.toml` が読めない、
`path` が実在しない、といった場合は ask を返して人間に知らせる(ガードが空振りして
いることに気づけないのが最悪のため)。
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path

CONFIG_PATH = Path(".claude/project.toml")


def _text_from_input(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Write":
        return tool_input.get("content", "")
    if tool_name == "Edit":
        return f"{tool_input.get('old_string', '')}\n{tool_input.get('new_string', '')}"
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        return "\n".join(f"{e.get('old_string', '')}\n{e.get('new_string', '')}" for e in edits)
    return ""


def load_rules(base: Path) -> tuple[list[dict], str | None]:
    """(ルール, 設定の不備) を返す。不備があれば理由の文字列が入る。"""
    config = base / CONFIG_PATH
    if not config.exists():
        return [], (
            f"{CONFIG_PATH} が無いため聖域ガードが機能していません。"
            "ai-dev-template の SETUP.md に従って作成してください。"
        )
    try:
        with config.open("rb") as f:
            cfg = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        return [], f"{CONFIG_PATH} を読めません({e})。聖域ガードが機能していません。"

    rules = cfg.get("sanctuary", {}).get("rule", [])
    if not rules:
        return [], None  # 聖域を定義しない選択は許容する(明示的に空)

    missing = [r.get("path", "?") for r in rules if not (base / r.get("path", "")).exists()]
    if missing:
        return rules, (
            f"{CONFIG_PATH} の聖域パスが実在しません: {', '.join(missing)}。"
            "ガードが空振りしています。設定を直してください。"
        )
    return rules, None


def decide(tool_name: str, tool_input: dict, rules: list[dict]) -> tuple[str, str] | None:
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return None
    text = _text_from_input(tool_name, tool_input)

    for rule in rules:
        path = rule.get("path", "")
        if not path or not file_path.endswith(path):
            continue

        # Write は全文置換なので常に確認する
        hit = tool_name == "Write"
        if not hit and (pattern := rule.get("match")):
            hit = bool(re.search(pattern, text))
        if not hit and (symbols := rule.get("symbols")):
            hit = any(s in text for s in symbols)
        if not hit and not rule.get("match") and not rule.get("symbols"):
            hit = True  # 条件指定が無ければファイル単位で確認

        if hit:
            reason = rule.get("reason") or f"{path} は聖域として設定されています。"
            return ("ask", reason)

    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return 0

    base = Path(payload.get("cwd") or os.getcwd())
    rules, defect = load_rules(base)

    if defect:
        _emit("ask", f"⚠ 聖域ガードの設定に問題があります。{defect}")
        return 0

    result = decide(tool_name, tool_input, rules)
    if result is None:
        return 0
    _emit(*result)
    return 0


def _emit(decision: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


if __name__ == "__main__":
    sys.exit(main())
