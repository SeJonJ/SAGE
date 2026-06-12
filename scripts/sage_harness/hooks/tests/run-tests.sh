#!/usr/bin/env bash
# SAGE hook 회귀 테스트 러너.
# cases.tsv 의 각 행(path<TAB>expected_exit<TAB>desc)을 hook 에 --path 로 먹여 종료코드 검증.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_DIR="$(dirname "$HERE")"
GUARD="$HOOK_DIR/generated-artifact-write-guard.sh"
CASES="$HERE/cases.tsv"

pass=0; fail=0

run_case() {
  local path="$1" expected="$2" desc="$3"
  local actual=0
  bash "$GUARD" --path "$path" >/dev/null 2>&1 || actual=$?
  if [[ "$actual" == "$expected" ]]; then
    pass=$((pass+1))
  else
    fail=$((fail+1))
    printf '  ✗ [%s] exit=%s expected=%s :: %s\n' "$path" "$actual" "$expected" "$desc"
  fi
}

echo "== generated-artifact-write-guard 회귀 테스트 =="
while IFS=$'\t' read -r path expected desc; do
  [[ -z "$path" || "$path" == \#* ]] && continue
  run_case "$path" "$expected" "$desc"
done < "$CASES"

# stdin JSON 추출 경로도 1건 검증 (런타임 어댑터 모사)
stdin_exit=0
echo '{"tool_input":{"file_path":".claude/agents/z.md"}}' | bash "$GUARD" >/dev/null 2>&1 || stdin_exit=$?
if [[ "$stdin_exit" == "2" ]]; then pass=$((pass+1)); else fail=$((fail+1)); echo "  ✗ [stdin JSON] exit=$stdin_exit expected=2"; fi

echo "----"
echo "PASS=$pass FAIL=$fail"
[[ "$fail" == "0" ]] || exit 1
