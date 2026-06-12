---
id: generated-artifact-write-guard
kind: hook
---
## intent
생성 산출물(.claude/.codex 의 agents/hooks/skills) 직접수정을 결정론적으로 block 하고
spec(docs/sage_harness)으로 redirect 한다. SSOT 모델의 잠금장치 — 없으면 "항상 spec을 고친다"가
권고에 그치고 AI가 개발 중 산출물을 곁다리로 고쳐 조용한 drift가 생긴다 (설계 §5.6).

## runtime_bindings
- claude: { event: PreToolUse, matcher: "Write|Edit|MultiEdit" }
- codex:  { event: PreToolUse, matcher: "apply_patch" }
- on_fail: block            # adapter가 exit 2(stderr) / JSON 으로 매핑

## canonical
scripts/sage_harness/hooks/generated-artifact-write-guard.sh
- 입력: --path | $SAGE_GUARD_PATH | stdin JSON(tool_input.file_path)
- 핵심 알고리즘 = "경로가 생성 산출물인가" 분류 (런타임별 입력 추출은 얇은 어댑터)

## enforcement
- block(exit 2): 경로가 `*.claude/{agents,hooks,skills}/*` 또는 `*.codex/{agents,hooks,skills}/*`
- pass(exit 0): 그 외 전부. 특히 `docs/sage_harness/**`·`scripts/sage_harness/**`(소스)는 우선 허용
- 경로 없음/파싱 실패 → pass (가드 대상 아님, 조용한 오작동 방지)
- 예외 처리 불필요: `sage generate` CLI 는 편집도구(Write/Edit/apply_patch)를 거치지 않으므로
  애초에 이 PreToolUse 가드에 걸리지 않는다 (설계 §5.6 G3)

## scope 메모 (v1)
- 가드 범위 = agents/hooks/skills 디렉토리 (설계 §5.6 다이어그램 명시 범위)
- settings.json / hooks.json(등록 산출물) 가드는 부트스트랩 중 직접편집 필요성 때문에 v1 보류 — 후속 결정

## tests
scripts/sage_harness/hooks/tests/ (cases.tsv: path → expected exit)

## mode (forward-compat)
- v1 SAGE-mode = block (spec-SSOT 존재 전제)
- ChatForYou 등 spec 미존재 환경에 선적용 시 = warn-mode 미러 drift 탐지로 degrade (profile `guard.mode`)
