# 7차 전 개발 — 배치2: cross-model 결정론 invocation

상태: 2-1(rename) 완료·커밋(8beb744). 2-2~2-5 구현 중.
정본 범위: vault `TECH - SAGE 7차 전 개발 범위 (피드백 통합)`.

## 핵심 결정 (피드백 1 확정)
gstack `/codex` 스킬 의존을 폐기하고 **SAGE 자체 결정론 invocation**으로 cross-model 리뷰 수행.
gstack wrapper 기법(`-s read-only`·`< /dev/null`·timeout·`--json` 최종 agent_message 파싱)만 차용.

## 2-2 `sage review` (same-runtime)
- 역할: cross_model=false 경로. host AI 자신이 clean-context 리뷰. **peer 호출 없음.**
- 결정론 부분: `review-loop open --reviewer-requested same_runtime` → (host AI가 FIND/REFUTE/…)
  → `review-loop close --reviewer-actual same_runtime`. reviewer 일치 → degraded=false.
- sage-team 스킬과 균일 인터페이스를 위해 thin orchestration 명령으로 둔다.

## 2-3 `sage cross-check` (cross-model) — 엔진(핵심)
- 역할: cross_model=true 경로. 반대 런타임을 **직접 호출**해 독립 리뷰 획득.
- 흐름:
  1. `reviewer_resolution` 로 peer 결정 + 가용성 판정(아래 2-3a).
  2. peer 도달 가능 → review packet(변경 diff + 05 맥락) 작성 →
     - claude-host: `codex exec --json -s read-only -c model_reasoning_effort=high "<packet>" < /dev/null` (timeout 래핑)
     - codex-host: `claude -p --output-format json "<packet>"` (timeout 래핑)
     → 최종 agent_message 파싱 → 05 문서/리뷰결과에 반영 → `reviewer_actual=cross_model`.
  3. peer 미도달 → same-runtime 폴백 → `reviewer_actual=same_runtime` → 배치3 degraded=true 로 표면화.
- 침묵 폴백 금지: 폴백 시 stderr 경고 + reviewer_actual 기록(배치3 게이트가 degraded BLOCK/WARN).

## 2-3a `reviewer_resolution` 재작성 (gstack→peer-CLI 직접 탐지)
현재(doctor.py): claude-host=gstack 필요, codex-host=invocation 문자열 필요.
변경:
- caps = {codex: which("codex"), claude: which("claude")} (peer CLI 직접 탐지 — 1-a gstack 오탐 버그 근원 제거).
- cross off → same_runtime (불변).
- claude-host + cross + codex 가용 → opposite_runtime(codex), `codex exec`.
- claude-host + cross + codex 불가 → same_runtime 폴백(degraded, codex_cli_unavailable).
- codex-host + cross + claude 가용 → opposite_runtime(claude), `claude -p`.
- codex-host + cross + claude 불가 → same_runtime 폴백(degraded, claude_cli_unavailable).
- gstack 필드는 legacy notice 로만(하위호환 — requires:[gstack] 경고 후 무시).
- 영향: test_reviewer_resolution.py(7) 재작성, doctor.py gstack which 제거, profile 템플릿 cross_model 섹션 갱신.

## 2-5 진단 정정
"codex CLI는 interactive 전용" 거짓 문구를 스킬/문서에서 제거(`codex exec` 실재). sage-review/cross-check 스킬 본문 + cross_model invocation 주석.

## 2-4 라우팅 (sage-team 스킬)
Phase 05 에서 profile.options.cross_model → true면 `sage cross-check`, false면 `sage review`.
(스킬 3분할은 배치1이지만 이 라우팅 결선은 배치2 마무리에 포함.)

## codex 리뷰: 상 tier 4~5회, 매 라운드 논리검증 후 수용/비수용.
## 검증: reviewer_resolution 단위 재작성 + cross-check 단위(폴백/도달/파싱 모킹) + 회귀 + validate.
