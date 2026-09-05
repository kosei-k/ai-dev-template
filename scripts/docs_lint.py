#!/usr/bin/env python3
"""ドキュメントの機械検査。「機械検査できる規約はチェックリストではなくlintに落とす」の実体。

どのプロジェクトでも通用する検査だけをここに持つ。プロジェクト固有の検査
(設定ファイルのスキーマ検証など)は `[checks] extra` で指定したスクリプトに委ねる。

検査する内容:
  1. 聖域設定(.claude/project.toml の [[sanctuary.rule]])のパスが実在するか
     — ガードが空振りしているのを黙って許さない
  2. 受け入れケース台帳と tests/ の双方向突合
     (Statusは区別しない。台帳に載っているIDは常にテストと対応している前提)
  3. 連番規約(NN_slug.md、2桁ゼロ埋め)のディレクトリ検査
  4. ドキュメント内リンク(相対パス)の参照切れ
  5. [checks] extra があればそれを実行し、終了コードを引き継ぐ

設定は .claude/project.toml から読む。設定が無い項目の検査はスキップする
(ただし 1 は例外で、[[sanctuary.rule]] があるのにパスが壊れていたら必ず落とす)。

終了コード: 0=問題なし、1=問題あり(CIを落とす)。
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

CONFIG_PATH = Path(".claude/project.toml")
AC_ID_PATTERN = re.compile(r"\b([A-Z]+)-AC-(\d{3})\b")
NUMBERED_FILENAME = re.compile(r"^(\d{2})_[a-z0-9_]+\.md$")
MD_LINK = re.compile(
    r"`(\.{0,2}/?[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*\.md)`|\[[^\]]*\]\(([^)]+\.md)\)"
)


def load_config(base: Path) -> dict:
    config = base / CONFIG_PATH
    if not config.exists():
        return {}
    with config.open("rb") as f:
        return tomllib.load(f)


# ----------------------------------------------------------------------
# 1. 聖域設定の実在確認
# ----------------------------------------------------------------------


def check_sanctuary(base: Path, cfg: dict) -> list[str]:
    rules = cfg.get("sanctuary", {}).get("rule", [])
    errors = []
    for rule in rules:
        path = rule.get("path")
        if not path:
            errors.append("[[sanctuary.rule]] に path がない")
        elif not (base / path).exists():
            errors.append(
                f"聖域に指定された {path} が実在しない。ガードが空振りしている"
                "(.claude/project.toml を直すこと)"
            )
    return errors


# ----------------------------------------------------------------------
# 2. 受け入れケース台帳 <-> tests/ の双方向突合
# ----------------------------------------------------------------------


def _extract_ids(text: str) -> set[str]:
    return {f"{m.group(1)}-AC-{m.group(2)}" for m in AC_ID_PATTERN.finditer(text)}


def check_acceptance(base: Path, cfg: dict) -> list[str]:
    acceptance = cfg.get("acceptance", {})
    ledger_rel = acceptance.get("ledger")
    tests_rel = acceptance.get("tests_dir")
    if not ledger_rel or not tests_rel:
        return []

    ledger = base / ledger_rel
    tests_dir = base / tests_rel
    if not ledger.exists():
        return [f"受け入れケース台帳 {ledger_rel} が無い"]

    ledger_ids = _extract_ids(ledger.read_text(encoding="utf-8"))

    if not tests_dir.exists():
        # 立ち上げ直後は実装もテストも無い。台帳が空ならこの検査は対象外。
        # 台帳にIDがあるのにテストが無いのは、対応が取れていない状態なので落とす。
        if not ledger_ids:
            return []
        return [
            f"台帳に {len(ledger_ids)}件のIDがあるが、テストディレクトリ {tests_rel} が無い"
        ]
    patterns = acceptance.get("test_globs", ["*.py"])
    test_ids: set[str] = set()
    for pattern in patterns:
        for path in tests_dir.rglob(pattern):
            test_ids |= _extract_ids(path.read_text(encoding="utf-8"))

    errors = []
    for aid in sorted(ledger_ids - test_ids):
        errors.append(f"受け入れケース {aid} が台帳にあるが {tests_rel} のどこにも出現しない")
    for aid in sorted(test_ids - ledger_ids):
        errors.append(f"受け入れケース {aid} がテストに出現するが台帳に載っていない")
    return errors


# ----------------------------------------------------------------------
# 3. 連番規約
# ----------------------------------------------------------------------


def check_numbering(base: Path, cfg: dict) -> list[str]:
    errors: list[str] = []
    for rel in cfg.get("numbering", {}).get("dirs", []):
        directory = base / rel
        if not directory.exists():
            continue
        numbers: list[int] = []
        for path in sorted(directory.glob("*.md")):
            m = NUMBERED_FILENAME.match(path.name)
            if not m:
                errors.append(f"{rel}: {path.name} が命名規約(NN_slug.md, 2桁ゼロ埋め)に違反")
                continue
            numbers.append(int(m.group(1)))
        if len(numbers) != len(set(numbers)):
            errors.append(f"{rel}: 連番の重複がある {sorted(numbers)}")
    return errors


# ----------------------------------------------------------------------
# 4. ドキュメント内リンクの参照切れ
# ----------------------------------------------------------------------


def _candidates(base: Path, root: Path, referencing: Path, ref: str) -> list[Path]:
    if ref.startswith("./") or ref.startswith("../"):
        return [(referencing.parent / ref).resolve()]
    if (base / ref).exists():
        return [(base / ref).resolve()]
    return [(referencing.parent / ref).resolve(), (root / ref).resolve()]


def check_doc_links(base: Path, cfg: dict) -> list[str]:
    rel = cfg.get("docs", {}).get("link_check_dir")
    if not rel:
        return []
    root = base / rel
    if not root.exists():
        return []

    errors = []
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for m in MD_LINK.finditer(text):
            ref = m.group(1) or m.group(2)
            if ref.startswith("http") or "<" in ref or ref.startswith("NN_"):
                continue  # プレースホルダー例は対象外
            if not any(c.exists() for c in _candidates(base, root, path, ref)):
                errors.append(f"{path.relative_to(base)}: 参照切れ {ref}")
    return errors


# ----------------------------------------------------------------------
# 5. プロジェクト固有の検査(拡張点)
# ----------------------------------------------------------------------


def run_extra_check(base: Path, cfg: dict) -> int:
    script = cfg.get("checks", {}).get("extra")
    if not script:
        return 0
    path = base / script
    if not path.exists():
        print(f"docs_lint: [checks] extra が指す {script} が無い", file=sys.stderr)
        return 1
    print(f"docs_lint: プロジェクト固有の検査を実行: {script}")
    return subprocess.run([sys.executable, str(path)], cwd=base).returncode


# ----------------------------------------------------------------------


def main() -> int:
    base = Path.cwd()
    cfg = load_config(base)
    if not cfg:
        print(
            f"docs_lint: {CONFIG_PATH} が無い。ai-dev-template の SETUP.md を参照",
            file=sys.stderr,
        )
        return 1

    errors = (
        check_sanctuary(base, cfg)
        + check_acceptance(base, cfg)
        + check_numbering(base, cfg)
        + check_doc_links(base, cfg)
    )

    if errors:
        print(f"docs_lint: {len(errors)}件の問題:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    code = run_extra_check(base, cfg)
    if code == 0:
        print("docs_lint: 問題なし")
    return code


if __name__ == "__main__":
    sys.exit(main())
