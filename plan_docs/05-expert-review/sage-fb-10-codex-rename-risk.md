# [Expert Review] SAGE-FB-10 Codex rename 목적지 L3 분류 우회 차단

Cycle-Stem: `sage-fb-10-codex-rename-risk`
Review-Mode: Claude fresh headless (`claude -p --no-session-persistence`, no subagents)
Final Status: APPROVED

## 1. Review Protocol

사용자 요구에 따라 개발 완료 전 Claude 독립 리뷰를 세 번 수행했다. 각 리뷰는 이전 세션을
resume하지 않은 새 headless 프로세스였으며 gstack `/review`를 읽기 전용 plan mode로 실행했다.
세 번째 리뷰가 문서 finding을 남겼으므로 수정 후 네 번째 fresh closure 리뷰를 추가했다.

## 2. Review Rounds

| Round | Verdict | Findings | Triage Result |
|---|---|---|---|
| R1 | CHANGES_REQUIRED | P1 2, P2 2 | 전부 수용: Move-after-hunk backfill, equal-rank provenance, dead branch, test matrix |
| R2 | CHANGES_REQUIRED | P2 4 | 3건 수용; L0/L3 overlap은 독립 FB-07로 defer하고 acceptance 경계 명시 |
| R3 | CHANGES_REQUIRED | P1 1, P2 4 | 전부 수용: acceptance heading/status/evidence/boundary 및 dead conditional 수정 |
| Closure | CLEAN | P0 0, P1 0 | R3 수정과 실제 acceptance parser, gate probes 재검증 |

## 3. Accepted Findings and Rework

1. Move marker가 hunk 뒤에 올 때 destination content가 비는 문제를 source content backfill로 수정했다.
2. same-rank L3 changes가 filename/content provenance를 서로 가리던 문제를 ordered union으로 수정했다.
3. operator `file_short`와 `reason`은 같은 change를 가리키도록 aggregate trigger와 분리했다.
4. filename-L3인 동일 change도 content-L3 provenance를 보존한다.
5. extraction/classification 테스트를 실제 `decide()` hard BLOCK까지 확장했다.
6. Phase 01/04 acceptance 문서를 엔진 parser가 읽는 canonical heading/status로 수정했다.

## 4. Deferred Finding

destination 자체가 L0 pass glob과 L3 filename glob을 동시에 만족할 때 L0-first가 우선하는 동작은
재현됐지만 FB-10이 도입한 결함이 아니며, 요구사항 정본의 SAGE-FB-07이 위험도 예외 계약을 별도로
소유한다. 이번 사이클은 해당 경계를 00/01/02/04에 명시하고 위험 precedence를 변경하지 않았다.

## 5. Verification

- Relevant suites: `151 passed, 24 subtests passed`.
- `test_hook_runtime.py`: `65 passed`.
- Actual acceptance parser: six required IDs and six evidence rows, no missing/unrecognized/unresolved rows after closure.
- `git diff --check`: pass.
- Claude closure probes: real fixture rename hard BLOCK, change-order permutations, marker injection all safe.
- Full hook suite에서 관측된 6 failures는 missing optional environment/package와 기존 profile/golden staleness이며
  변경 모듈 참조가 없어 본 diff 회귀로 분류하지 않았다.

## 6. Final Decision

APPROVED. SAGE-FB-10의 rename destination 누락, same-rank security provenance 손실, 실제 gate hard-block
검증 공백이 닫혔다. FB-07 경계 외 필수 acceptance는 모두 PASS다.

