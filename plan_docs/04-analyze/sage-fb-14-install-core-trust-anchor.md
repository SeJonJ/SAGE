# [Analyze] SAGE-FB-14 최초 install CORE base 신뢰 앵커 검증

Cycle-Stem: `sage-fb-14-install-core-trust-anchor`

## 1. Baseline Reproduction

Current behavior: an existing modified CORE render is skipped by `_write(force=False)`, then
`overlay_materialize.materialize` hashes that file's base and `_manifest` records it as trusted `core_renders`.

Baseline suites before implementation:

- `test_install.py`: exit 0.
- `test_overlay_materialize.py`: 14 tests pass.

## 2. Acceptance Evidence

| Acceptance ID | Status | Evidence |
|---|:---:|---|
| FB14-AC1 | PASS | `test_first_install_unanchored_conflict_is_no_write_and_inventoried`가 rc=1 및 원본 보존을 검증한다. |
| FB14-AC2 | PASS | `test_first_install_allows_unanchored_current_bundle_base`가 동일 base 허용 및 anchor 생성을 검증한다. |
| FB14-AC3 | PASS | modified anchored render 및 forged matching anchor 테스트가 non-force 재축복 차단을 검증한다. |
| FB14-AC4 | PASS | first-install conflict 테스트가 exact key/path/reason/expected/actual SHA 및 `--force` 안내를 검증한다. |
| FB14-AC5 | PASS | blocked 테스트가 profile/guide/manifest 미생성과 기존 manifest byte 보존을 검증한다. |
| FB14-AC6 | PASS | force 테스트가 배포 base 교체, clean anchor 및 symlink 외부 target 보존을 검증한다. |
| FB14-AC7 | PASS | Claude profile render, Claude/Codex 설치 및 materialization 회귀가 동일 target 계약을 검증한다. |
| FB14-AC8 | PASS | 세 distinct fallback headless round와 추가 closure 검토를 완료하고 모든 finding을 선별 처리했다. |

Focused verification after implementation:

- `test_install.py -b`: 85 passed.
- `test_overlay_materialize.py`: 15 passed.
- `git diff --check`: pass.

## 3. Static Analysis Notes

- preflight는 profile/team 검증 직후, 첫 project/global write 이전에 실행된다.
- 기존 manifest는 preflight 전 read-only로 로드하고 성공 경로의 `_manifest`에도 같은 snapshot을 전달한다.
- ancestor symlink/non-regular target은 모든 모드에서 차단하고 leaf symlink는 force에서도 외부 target을 덮어쓰지 않는다.
- non-UTF-8와 malformed marker는 render/manifest bytes를 보존한 채 inventory와 rc=1로 종료한다.
- materialization snapshot의 anchor가 current bundle expected와 일치해야 manifest write로 진행한다.
- force write는 symlink/hard link target을 따라 truncate하지 않는 atomic replacement이며 기존 mode를 보존한다.
- shared `AGENT_GUIDE` receipt는 installed host 전체에 같은 current snapshot을 기록한다.
- malformed manifest non-force는 원본 manifest와 CORE render를 보존한 채 rc=1로 종료한다.
- mapping-shaped manifest 구조 손상도 핵심 필드 검증에서 차단하고 `--force` recovery만 허용한다.
- force recovery는 invalid mapping entries를 제거하고 primary host history/shared guide receipt를 복구한다.
- nested asset/receipt 구조도 shipped JSON Schema와 동등한 dependency-free validator로 검사한다.
- same-permission concurrent path replacement의 완전한 transaction isolation은 FB-15 residual risk다.
- global Codex skill은 `core_renders` 대상이 아니므로 이 사이클이 아니라 install scope 후속 항목에서 다룬다.
- 전체 overlay/domain preflight 순서 및 원자성은 FB-15 범위로 유지한다.

## 4. Review Boundary

Phase 05 completed three-round independent review, finding triage, closure rework, and final acceptance.
