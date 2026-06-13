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

# stdin 케이스 검증 (런타임 어댑터 모사) — Claude file_path / Codex apply_patch / 정상
check_stdin() {
  local json="$1" expected="$2" desc="$3" e=0
  echo "$json" | bash "$GUARD" >/dev/null 2>&1 || e=$?
  if [[ "$e" == "$expected" ]]; then pass=$((pass+1)); else fail=$((fail+1)); printf '  ✗ [stdin:%s] exit=%s expected=%s\n' "$desc" "$e" "$expected"; fi
}
check_stdin '{"tool_input":{"file_path":".claude/agents/z.md"}}' 2 "claude file_path guarded"
# audit 1회차 P0: Codex apply_patch 본문 다중 target 우회 차단
check_stdin '{"tool_name":"apply_patch","tool_input":{"command":"*** Add File: .codex/hooks/foo.sh\n+x\n"}}' 2 "codex apply_patch guarded"
check_stdin '{"tool_name":"apply_patch","tool_input":{"command":"*** Update File: .codex/agents/bar.md\n+y\n"}}' 2 "codex apply_patch agent guarded"
check_stdin '{"tool_name":"apply_patch","tool_input":{"command":"*** Add File: src/main/java/Foo.java\n+z\n"}}' 0 "codex apply_patch 일반소스 통과"
check_stdin '{"tool_name":"apply_patch","tool_input":{"command":"*** Add File: docs/sage_harness/hooks/x.md\n+z\n"}}' 0 "codex apply_patch spec 통과"

echo "----"
echo "PASS=$pass FAIL=$fail"
[[ "$fail" == "0" ]] || exit 1
