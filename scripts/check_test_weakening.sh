#!/usr/bin/env bash
# テスト弱体化の機械検知。「AIを止める境界(テストを緩めて通さない)」の実体化。
#
# 使い方: check_test_weakening.sh <base_ref> <head_ref> <light|strict> [tests_glob] [impl_glob]
#   tests_glob: 既定 'tests/*.py'
#   impl_glob : 既定 'src/*'（実装側の削除と対応しているかの判定に使う）
#
# 検出:
#   1. 受け入れケースID付きテストの削除          -> BLOCK (light/strict とも)
#   2. skip/xfail マーカーの追加                  -> BLOCK (light/strict とも)
#   3. 実装削除を伴わないテスト関数の削除          -> ESCALATE (strict のみ)
#   4. assert の純減                              -> ESCALATE (strict のみ)
#
# 終了コード: 0=問題なし 1=BLOCK(CI失敗) 2=ESCALATE(needs-human)
set -euo pipefail

BASE_REF="${1:?base ref required}"
HEAD_REF="${2:?head ref required}"
MODE="${3:-light}"
TESTS_GLOB="${4:-tests/*.py}"
IMPL_GLOB="${5:-src/*}"

if [[ "$MODE" != "light" && "$MODE" != "strict" ]]; then
  echo "MODE must be 'light' or 'strict', got: $MODE" >&2
  exit 1
fi

DIFF_RANGE="${BASE_REF}...${HEAD_REF}"
TEST_DIFF="$(git diff "$DIFF_RANGE" -- "$TESTS_GLOB" || true)"

if [[ -z "$TEST_DIFF" ]]; then
  echo "check_test_weakening: $TESTS_GLOB に変更なし。問題なし"
  exit 0
fi

BLOCK_REASONS=()
ESCALATE_REASONS=()

# --- 1. 受け入れケースID付きテストの削除 ---------------------------------
DELETED_IDS="$(echo "$TEST_DIFF" | grep -E '^-[^-]' | grep -oE '[A-Z]+-AC-[0-9]{3}' | sort -u || true)"
ADDED_IDS="$(echo "$TEST_DIFF" | grep -E '^\+[^+]' | grep -oE '[A-Z]+-AC-[0-9]{3}' | sort -u || true)"
ORPHANED_IDS="$(comm -23 <(echo "$DELETED_IDS") <(echo "$ADDED_IDS") 2>/dev/null | grep -v '^$' || true)"

if [[ -n "$ORPHANED_IDS" ]]; then
  BLOCK_REASONS+=("受け入れケースID付きテストが削除された(台帳側の更新漏れの疑い): $(echo "$ORPHANED_IDS" | tr '\n' ' ')")
fi

# --- 2. skip/xfail マーカーの追加 ----------------------------------------
SKIP_ADDED="$(echo "$TEST_DIFF" | grep -E '^\+' | grep -E '@pytest\.mark\.(skip|xfail)|pytest\.skip\(|\.skip\(|xfail\(' || true)"
if [[ -n "$SKIP_ADDED" ]]; then
  BLOCK_REASONS+=("skip/xfail マーカーが追加された:
$SKIP_ADDED")
fi

if [[ "$MODE" == "strict" ]]; then
  # --- 3. 実装削除を伴わないテスト関数の削除 -----------------------------
  DELETED_TEST_FUNCS="$(echo "$TEST_DIFF" | grep -cE '^-\s*def test_' || true)"
  IMPL_DIFF="$(git diff "$DIFF_RANGE" -- "$IMPL_GLOB" || true)"
  IMPL_DELETIONS="$(echo "$IMPL_DIFF" | grep -cE '^-[^-]' || true)"

  if [[ "$DELETED_TEST_FUNCS" -gt 0 && "$IMPL_DELETIONS" -eq 0 ]]; then
    ESCALATE_REASONS+=("テスト関数が${DELETED_TEST_FUNCS}件削除されたが $IMPL_GLOB に対応する削除が無い(正当なリファクタか要確認)")
  fi

  # --- 4. assert の純減 ---------------------------------------------------
  ASSERT_REMOVED="$(echo "$TEST_DIFF" | grep -cE '^-[^-].*assert ' || true)"
  ASSERT_ADDED="$(echo "$TEST_DIFF" | grep -cE '^\+[^+].*assert ' || true)"
  if [[ "$ASSERT_REMOVED" -gt "$ASSERT_ADDED" ]]; then
    ESCALATE_REASONS+=("assert が純減している(削除${ASSERT_REMOVED}件 > 追加${ASSERT_ADDED}件)。検証強度の低下の疑い")
  fi
fi

if [[ ${#BLOCK_REASONS[@]} -gt 0 ]]; then
  echo "check_test_weakening: BLOCK"
  printf '  - %s\n' "${BLOCK_REASONS[@]}"
  exit 1
fi

if [[ ${#ESCALATE_REASONS[@]} -gt 0 ]]; then
  echo "check_test_weakening: ESCALATE"
  printf '  - %s\n' "${ESCALATE_REASONS[@]}"
  exit 2
fi

echo "check_test_weakening: 問題なし ($MODE)"
exit 0
