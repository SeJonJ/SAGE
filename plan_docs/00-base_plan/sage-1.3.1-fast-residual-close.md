# [Fast 기본 계획] Fast Cycle 잔여 승인 close 거부 수정 (#18)

Cycle-Stem: `sage-1.3.1-fast-residual-close`
Cycle-Mode: FAST
Document-Language: ko
Risk Level: L3
Fast-Review-Level: L3
Fast-Minimum-Rounds: 1
Fast-Lens-Count: 4
Fast-Lenses: correctness, security, data_integrity, concurrency
Fast-Reason: 두 이슈(#18·#19) 모두 긴급하고 크리티컬해 빠른 반영이 필요하지만, 수정 범위가 좁고 단순해 Fast 사이클로 진행
Fast-Audit-Run: pending
Status: COMPLETED — 05 codex cross-review APPROVED, 06 작성(2026-10-12). 커밋은 사용자 결정
Done-Criteria-Revision: 1

## Phase 00 — 기본 계획

### 배경

- 이슈: https://github.com/SeJonJ/SAGE/issues/18
- 판정·범위 정본: 위키 「SAGE - 1.3.0 버그 대응 (26.10.12)」
- 엔진 저장소에는 SAGE 를 설치하지 않는다. 이 사이클은 Fast 문서 절차를 손으로 따르고, 감사 run 은 열지 않는다(`Fast-Audit-Run: pending` 유지). 05 리뷰는 codex cross-review 로 한다.
- #19 와 같은 1.3.1 패치로 배포한다. #19 는 이 사이클이 끝난 뒤 별도 사이클로 시작한다.

### 문제

Fast 합본 00(`Cycle-Mode: FAST`)으로 진행하는 사이클에서 `converge_on: blocking` run 이 비차단 지적만 남기고 수렴하면 `next` 는 `STOP CONVERGED_RESIDUAL` 을 권하지만 `close` 가 `Phase 01 exact cycle selection failed` 로 거부한다. `review_loop._acceptance_blockers()` 가 01·04 를 실제 파일 glob 으로만 찾고 합본을 펼치지 않기 때문이다. 같은 함수를 쓰는 `USER_AUTHORIZED_EARLY` 조기 완료도 Fast 에서 같은 이유로 막힌다(0.9.90 부터). acceptance 정책이 꺼진 프로젝트에서는 재현되지 않는다.

관련 결함: Fast 에 묶인 run 의 `round` 가 렌즈 영수증 없이 기록되고 run 이 승인으로 닫힌 뒤에야 `sage fast-cycle review` 가 거부한다. 닫힌 run 은 되돌릴 수 없어 리뷰를 처음부터 다시 해야 한다.

### 범위

- 포함: 합본 펼치기 공용 함수, `review_loop` acceptance 검사의 Fast 처리, Fast run `round` 의 렌즈 영수증 검사, 회귀 시험, `sage-review` 사이클 상한 안내 보강.
- 제외: `next` 의 close 사전 검사(순수 함수 `loop_verdict` 에 문서 읽기가 섞임), acceptance 판정 규칙 자체, 06 게이트 판정 변경.

### Done Criteria
- [x] Fast 합본 + `blocking` + 비차단 잔여 run 이 `close --reason CONVERGED_RESIDUAL` 로 승인 닫힌다
- [x] Fast 합본의 acceptance 미해결(FAIL·NOT TESTED)은 잔여 승인·조기 완료에서 그 사유로 거부된다
- [x] 합본 파싱 오류는 「문서 없음」이 아니라 파싱 문제로 보고된다
- [x] 06 게이트(`hook_runtime`)와 CI 권위 판정(`ci_authority`)의 기존 동작이 바뀌지 않는다
- [x] Fast 에 묶인 run 의 `round` 는 렌즈 영수증이 없거나 다르면 기록되지 않고, 일반 run 은 기존과 같다
- [x] 관련 회귀 스위트가 통과한다
- [x] codex cross-review 가 APPROVED 다

### Document Mapping (Checklist)
- [x] Phase 00 context complete
- [x] Phase 01 requirements and acceptance matrix embedded
- [x] Phase 02 design and failure handling embedded
- [x] Phase 03 ownership, implementation checklist, and verification plan ready

## Phase 01 — 요구사항

### Acceptance Matrix

| ID | User Requirement | Required Evidence | Owner | Required? |
|---|---|---|---|---|
| A1 | Fast 합본 + `blocking` + P3 잔여 1건 run 의 `CONVERGED_RESIDUAL` close 가 성공하고 `REDUCED_BY_POLICY` 로 기록된다 | 회귀 시험 | dev | yes |
| A2 | Fast 합본 Phase 04 의 필수 acceptance 가 FAIL·NOT TESTED 면 잔여 승인 close 가 `unresolved acceptance` 로 거부된다 | 회귀 시험 | dev | yes |
| A3 | Fast 합본 run 의 `USER_AUTHORIZED_EARLY` 가 「문서 없음」 없이 acceptance 검사까지 도달한다 | 회귀 시험 | dev | yes |
| A4 | 같은 stem 에 실제 01 파일과 합본이 함께 있으면 모호성으로 거부된다 | 회귀 시험 | dev | yes |
| A5 | 이 run stem 의 합본이 파싱 오류면 그 오류가 거부 사유로 보이고, 다른 stem 의 깨진 합본은 이 run 을 막지 않는다 | 회귀 시험 | dev | yes |
| A6 | 실제 01~04 파일을 쓰는 표준·FAST-CONVERTED run 의 판정이 바뀌지 않는다 | 기존 시험 통과 + 회귀 시험 | dev | yes |
| A7 | `hook_runtime`·`ci_authority` 가 공용 함수를 쓰면서 기존 동작(오류 삼킴 / 오류 반환, 문서 키)이 그대로다 | 기존 시험 통과 + 공용 함수 단위 시험 | dev | yes |
| A8 | Fast 에 묶인 run 의 `round` 는 `--lens-receipts` 누락·불일치 시 거부되고 일반 run 은 기존처럼 받아들여진다 | 회귀 시험 | dev | yes |
| A9 | `sage-review` 사이클 상한 절에 run 상한에 닿은 run 을 닫고 새 run 에서 이어 가는 순서가 있다 | 문서 diff | dev | yes |

## Phase 02 — 설계

### 공용 함수

`scripts/sage_harness/hooks/fast_cycle_contract.py`(정본, `sage/fast_cycle_contract.py` 가 다시 내보냄)에 추가한다.

```
virtual_phase_docs(phase00_docs, *, stem=None) -> (dict[phase, list[doc]], list[str])
```

- `Cycle-Mode: FAST` 인 00 문서만 대상. `stem` 을 주면 메타데이터 `Cycle-Stem` 이 그 값인 문서만 본다.
- 파싱 문제가 있는 합본은 펼치지 않고 문제를 issues 로 돌려준다(현재 `ci_authority` 와 같은 순서: Cycle-Mode 확인 → 문제 보고).
- 가상 문서 키는 지금과 같게 `path`·`content`·`virtual_fast`, 원본에 `recent` 가 있으면 그것만 옮긴다. 원본 dict 의 다른 키는 옮기지 않는다(`ci_authority` 요청 문서의 키가 가상 문서로 새어 나가지 않게).
- content 머리(`Cycle-Stem`·`Risk Level`)는 현재 두 구현과 바이트 단위로 같게 유지한다.

### 호출부

- `hook_runtime`: 공용 함수를 부르고 issues 는 지금처럼 버린다(게이트 core 가 파서·감사 실패를 따로 받는다). 예외도 지금처럼 삼킨다.
- `ci_authority._expand_fast_phase_docs`: 공용 함수 결과를 그대로 쓰고 issues 앞에 `Fast composite: ` 를 붙인다. 파서 예외 처리 문구는 유지한다.
- `review_loop._acceptance_blockers`: 01·04 후보 = `_phase_docs(phase)` + 이 run stem 의 가상 문서. 이 stem 합본의 파싱 문제가 있으면 `Fast composite Phase 00 unreadable: <문제>` 로 거부한다. `_phase_docs` 자체는 바꾸지 않는다(표준 Done Criteria 재실행 검사도 쓰므로).

### 렌즈 영수증

`round` 에서 `_fast_run_id()` 로 묶인 Fast run 이 확인되면, 그 run 의 `lenses` 와 `--lens-receipts` 가 같지 않을 때(누락 포함) 기록을 거부한다. 비교 규칙은 `fast_cycle.py` 묶기 검사(`record.get("lens_receipts") != expected_lenses`)와 같게 한다. Fast run 을 특정할 수 없으면(미사용·후보 둘 이상·감사 읽기 실패) 지금처럼 받아들이고 묶기 시점 검사에 맡긴다.

### 실패 처리

- 공용 함수 내부 예외: `review_loop` 에서는 `acceptance check failed: <예외>` 로 거부(판정 불가 = 통과 아님).
- 합본이 없거나 Fast 가 아닌 stem: 가상 문서 0개 → 기존 동작 그대로.

## Phase 03 — 구현

- [x] File ownership assigned before source edits
- [x] Acceptance IDs mapped to implementation tasks
- [x] Verification command plan recorded

### 소유 파일 (단독 작업)

- `scripts/sage_harness/hooks/fast_cycle_contract.py`
- `scripts/sage_harness/hooks/runtime/hook_runtime.py`
- `sage/ci_authority.py`
- `sage/commands/review_loop.py`
- `scripts/sage_harness/hooks/tests/test_review_blocking_convergence.py`, `test_fast_cycle.py`(필요 시)
- `templates/core/framework/.claude/skills/sage-review/SKILL.md`, `templates/core/skills/sage-review.md`
- `docs/sage_harness/.manifest.json` (hook 런타임 해시 재생성 시)

### 작업 ↔ acceptance

| 작업 | Acceptance |
|---|---|
| 공용 함수 + 단위 시험 | A5, A7 |
| `hook_runtime`·`ci_authority` 전환 | A7 |
| `_acceptance_blockers` Fast 처리 | A1, A2, A3, A4, A5, A6 |
| `round` 렌즈 영수증 검사 | A8 |
| `sage-review` 문서 보강 | A9 |

### 검증 명령

- 관련 시험: `python -m unittest scripts/sage_harness/hooks/tests/test_review_blocking_convergence.py scripts/sage_harness/hooks/tests/test_fast_cycle.py scripts/sage_harness/hooks/tests/test_ci_authority.py scripts/sage_harness/hooks/tests/test_hook_runtime.py`(파일 경로 실행이 안 되면 모듈 경로로)
- 전체 스위트는 로컬 한 버전 1회: `bash scripts/sage_harness/hooks/tests/run-all.sh`
- `python -m sage validate --check --schema`
- 파이썬 버전 매트릭스·플랫폼 스모크는 CI 에 맡긴다.

## Phase 04 — 분석

Status: COMPLETE — 구현·로컬 검증 완료, 05 APPROVED

### Acceptance Evidence

| ID | Status | Evidence |
|---|---|---|
| A1 | PASS | `TestFastCompositeAcceptance.test_the_residual_approval_reads_the_composite` — close 성공, `review_assurance=REDUCED_BY_POLICY`, `mode=FAST` |
| A2 | PASS | `test_unresolved_composite_acceptance_blocks_the_residual_approval` — FAIL·NOT TESTED 모두 `unresolved acceptance` 거부, close 기록 0 |
| A3 | PASS | `test_the_early_close_reaches_the_composite_acceptance` — `exact cycle selection failed` 없이 acceptance 사유로 거부 |
| A4 | PASS | `test_a_real_phase01_file_beside_the_composite_is_ambiguous` — `ambiguous phase documents` 거부 |
| A5 | PASS | `test_a_broken_composite_of_this_cycle_is_reported_as_such`·`test_a_broken_composite_of_another_cycle_does_not_block`·`TestVirtualPhaseDocs` |
| A6 | PASS | 기존 `TestResidualEligibility`(실제 01·04 파일) 통과, `test_fast_convert` 통과 |
| A7 | PASS | `test_hook_runtime`·`test_ci_authority` 변경 없이 통과, `TestVirtualPhaseDocs` 로 키·머리·필터 확인 |
| A8 | PASS | `test_a_fast_round_without_the_lens_receipts_is_refused`(누락·부분·순서 다름) · `test_a_standard_round_without_lens_receipts_is_unchanged` |
| A9 | PASS | `sage-review` SKILL 「Cycle cap」 절·spec procedure 문구 추가 |

### 검증 결과

- 새 시험 10건 통과. 소스 수정만 되돌리면 같은 시험 11건(subTest 포함)이 실패해 원래 증상을 재현한다(A8 일반 run 시험만 양쪽 통과 — 의도).
- 관련 묶음 통과: `test_review_blocking_convergence`·`test_fast_cycle`·`test_fast_convert`·`test_ci_authority`·`test_hook_runtime`·`test_loop_audit`·`test_review_loop_cli`.
- `python -m sage validate --check --schema`: WARN(exit 0) — overlay 안내만, main 과 같다. `hook_runtime_hash.shared` 재계산.
- 전체 스위트(`run-all.sh`, 로컬 Python 3 한 버전): 3,824건 실패 0, `ALL HOOK TESTS PASS`. 파이썬 버전 매트릭스·플랫폼 스모크는 CI 에 맡긴다.

### 설계와 달라진 점

- `_acceptance_blockers` 의 문서 읽기(00·01·04)를 한 try 로 묶고, 어떤 예외든 `acceptance check failed` 로 거부한다. 이전에는 01·04 읽기의 `ValueError`(glob 설정·경로 탈출)가 close 를 traceback 으로 죽였다 — 변경 전 결함이지만 같은 자리라 함께 닫았다. 판정 불가는 통과가 아니다는 방향은 같다.
- 공용 함수로 합치며 생긴 차이 두 가지(05 1차 P3 로 확인, 허용):
  - 원본 문서에 `recent` 키가 있으면 가상 문서가 그것을 옮긴다. `hook_runtime` 문서는 항상 `recent` 를 가져 이전과 같고, `ci_authority` 요청 문서에는 이 키를 만드는 생산자가 없다.
  - 펼치는 도중 예외가 나면 이전에는 앞서 펼친 문서가 남았고, 지금은 하나도 남지 않는다. `ci_authority` 는 두 경우 모두 parser failure 로 차단하고, `hook_runtime` 은 게이트 core 가 파서·감사 실패를 따로 받으므로 판정 결과는 같다.
  - 호출부 계약은 `TestVirtualPhaseDocs.test_the_ci_authority_caller_keeps_its_contract` 로 고정했다.
- 렌즈 영수증 거부 문구에 「`sage fast-cycle review` 는 run 이 닫힌 뒤 거부한다」는 이유를 넣었다.

### 판정 요청 (05 에)

- `hook_runtime`·`ci_authority` 동작 불변 판단이 맞는가(가상 문서 키·순서, 예외 시 부분 펼침이 사라진 점).
- Fast run 을 특정하지 못하면 영수증 검사를 건너뛰는 것이 허용 가능한가.
