#!/usr/bin/env python3
"""PostToolUse(Edit|Write|MultiEdit) フック。編集したファイルに lint をその場でかける。

手戻りの最小化が目的: lintエラーに気づくのがコミット時・CI時ではなく編集直後になる。
違反があれば systemMessage で Claude に知らせる(ブロックはしない)。

設定の書き方(.claude/project.toml):

    [[lint.rule]]
    ext = ".py"                                  # 対象の拡張子
    command = ["uv", "run", "ruff", "check"]     # 末尾に対象ファイルパスが付く
    fix_hint = "mise run fix"                    # 任意。直し方の案内

    [[lint.rule]]
    ext = ".ts"
    command = ["npx", "eslint"]

設定が無ければ何もしない(このフックは「あると便利」の類であり、
無いことが事故につながらないため、聖域ガードと違って黙って素通りする)。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

CONFIG_PATH = Path(".claude/project.toml")
TIMEOUT_SEC = 20


def load_rules(base: Path) -> list[dict]:
    config = base / CONFIG_PATH
    if not config.exists():
        return []
    try:
        with config.open("rb") as f:
            cfg = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        return []
    return cfg.get("lint", {}).get("rule", [])


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("tool_name", "") not in ("Edit", "Write", "MultiEdit"):
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return 0
    path = Path(file_path)
    if not path.exists():
        return 0

    base = Path(payload.get("cwd") or os.getcwd())
    rule = next(
        (r for r in load_rules(base) if r.get("ext") and file_path.endswith(r["ext"])),
        None,
    )
    if rule is None or not rule.get("command"):
        return 0

    try:
        result = subprocess.run(
            [*rule["command"], str(path)],
            cwd=base,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
    except (OSError, subprocess.SubprocessError):
        return 0  # lintコマンドが無い環境でも編集は止めない

    if result.returncode == 0:
        return 0

    hint = rule.get("fix_hint")
    message = f"lint が {path.name} で違反を検出しました:\n{result.stdout.strip()}"
    if hint:
        message += f"\nコミット前に `{hint}` で直してください。"

    print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
