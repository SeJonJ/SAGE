#!/usr/bin/env bash
# SAGE generated-artifact write guard — canonical algorithm
# spec: docs/sage_harness/hooks/generated-artifact-write-guard.md
#
# 목적: 생성 산출물(.claude/.codex 의 agents/hooks/skills) 직접수정을 block 하고 spec 으로 redirect.
#       산출물 직접수정을 막아야 "항상 spec 을 고친다"가 권고가 아닌 강제가 된다 (설계 §5.6).
#
# 입력 우선순위:
#   1) --path <p>            (테스트/직접호출)
#   2) $SAGE_GUARD_PATH       (테스트/직접호출)
#   3) stdin JSON tool_input.file_path  (런타임 PreToolUse 어댑터)
#
# 종료코드: 0 = 통과, 2 = block (stderr 메시지가 모델에 전달됨)
set -euo pipefail

extract_path_from_stdin() {
  # Claude PreToolUse JSON 예: { "tool_input": { "file_path": "..." } }
  # python3 -c 로 파싱(heredoc-as-program 을 쓰면 sys.stdin 이 JSON 이 아니라 프로그램이 됨).
  # 프로그램은 -c 인자로 주고 stdin 은 JSON 으로 유지. 실패 시 빈 문자열(=통과).
  python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = (d.get("tool_input") or {}) if isinstance(d, dict) else {}
print(ti.get("file_path") or ti.get("path") or "")
' 2>/dev/null || true
}

TARGET=""
if [[ "${1:-}" == "--path" ]]; then
  TARGET="${2:-}"
elif [[ -n "${SAGE_GUARD_PATH:-}" ]]; then
  TARGET="$SAGE_GUARD_PATH"
elif [[ ! -t 0 ]]; then
  TARGET="$(extract_path_from_stdin)"
fi

# 경로 없음 → 가드 대상 아님
[[ -z "$TARGET" ]] && exit 0

norm="${TARGET#./}"

# 명시 허용(소스 경로) — sage_harness 는 절대 block 하지 않는다 (방어적 우선판정)
case "$norm" in
  *docs/sage_harness/*|*scripts/sage_harness/*) exit 0 ;;
esac

# 가드 대상: .claude/.codex 의 agents/hooks/skills 산출물
is_guarded() {
  case "$1" in
    *.claude/agents/*|*.claude/hooks/*|*.claude/skills/*) return 0 ;;
    *.codex/agents/*|*.codex/hooks/*|*.codex/skills/*)    return 0 ;;
  esac
  return 1
}

if is_guarded "$norm"; then
  cat >&2 <<EOF
⛔ SAGE write guard: '$TARGET' 는 생성 산출물입니다. 직접수정 금지.
→ docs/sage_harness/<kind>s/<id>.md (spec) 을 고치고 'sage generate' 를 쓰세요.
→ 이미 수정한 diff 라면 'sage absorb --kind <k> --id <id> --from-blocked-diff' 로 spec patch 로 변환하세요.
(sage generate CLI 는 편집도구를 안 거치므로 이 가드에 걸리지 않습니다.)
EOF
  exit 2
fi

exit 0
