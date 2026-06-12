---
id: ""            # 예: pre-phase4-checklist-gate
kind: hook
---
## intent
이 hook이 무엇을 결정론적으로 차단/검사하는지 한 문장.

## runtime_bindings
- claude: { event: PreToolUse, matcher: "Write|Edit|MultiEdit" }
- codex:  { event: PreToolUse, matcher: "apply_patch" }
- on_fail: block            # block | warn | context — adapter가 exit code/JSON/stderr로 매핑

## canonical
scripts/sage_harness/hooks/<id>.sh   # 실제 알고리즘 (양 런타임 공유 정본)

## enforcement
- 차단 조건과 통과 조건을 명시 (enforcement는 hook 전용)

## tests
.{claude,codex}/hooks/tests/   # 런타임별 입력 fixture 회귀
