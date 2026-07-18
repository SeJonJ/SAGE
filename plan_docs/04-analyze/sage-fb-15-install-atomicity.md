# [Analyze] SAGE-FB-15 install preflight-first와 실패 원자성

Cycle-Stem: `sage-fb-15-install-atomicity`
Status: ANALYZED_REVIEWED

## 1. Design to Implementation Gap

| Design Item | Implementation | Gap |
|---|---|---|
| render-independent overlay/domain preflight | `preflight_overlays` shared by install and materialization | none |
| destination lock | stable NFC/casefold path key + existing destination inode key; POSIX/Windows backend | case-sensitive filesystem의 별도 case path도 보수적으로 직렬화 |
| project/global rollback journal | same-parent backup + ownership fingerprinted reverse restore | concurrent output은 강제 삭제하지 않고 recovery conflict로 보존 |
| legacy prune rollback | tree move retained until commit | none |
| optimistic CAS | file/tree fingerprints plus source content hash, logical-commit-before-report | backup cleanup은 post-commit GC라 중단 시 residue 가능 |
| force atomicity | same journal used for normal and force | none in injected paths |
| FB-12 cleanup exception | exact managed-block cleanup remains pre-transaction | documented exception |

## 2. Acceptance Evidence

| ID | Status | Evidence |
|---|:---:|---|
| FB15-AC1 | PASS | blocked/invalid/relaxing overlay and domain preflight tests |
| FB15-AC2 | PASS | first-install mid-write rollback leaves empty destination |
| FB15-AC3 | PASS | owned force/write/manifest/materialization failure exact snapshots; concurrent output 보존 |
| FB15-AC4 | PASS | force failure restores project tree and legacy directory |
| FB15-AC5 | PASS | Codex global skill bytes and project tree restored after late failure |
| FB15-AC6 | PASS | competing holder, symlink alias, case-insensitive alias lock tests |
| FB15-AC7 | PASS | overlay/output/source drift, safe ancestor, profile input tests |
| FB15-AC8 | PASS | existing install suite plus full regression green |
| FB15-AC9 | PASS | prior FB-12 cleanup regressions remain green |
| FB15-AC10 | PASS | three required independent rounds plus final clean closure re-review |

## 3. Review Finding Triage

| Round 1 Finding | Decision | Result |
|---|:---:|---|
| unguarded project/global ancestor symlink | ACCEPT | all staged mutation paths enforce declared root and non-symlink ancestors |
| rollback deletes concurrent mutation / ignores missing backup | ACCEPT | current path and backup preserved; explicit rollback conflict |
| case alias lock split | ACCEPT | existing destination device/inode lock identity |
| final CAS-to-commit reporting gap | ACCEPT | commit moved immediately after final checks, before reporting |
| BaseException/crash overclaim | ACCEPT | control signals rollback then re-raise; durable crash excluded in docs |
| profile referent and JSON/YAML scanner mismatch | ACCEPT | shared loader, YAML materialization과 JSON equality, symlink/non-regular reject |

### Round 2

| Finding | Decision | Result |
|---|:---:|---|
| destination 생성 전후 path→inode lock key 변경 | ACCEPT | stable canonical path key를 항상 획득하고 existing inode key를 추가 획득 |
| mkdir/replace/write 뒤 journal 기록 전 control-signal gap | ACCEPT | directory/journal/original/semantic output을 각 mutation 전에 write-ahead 기록 |
| backup 삭제 중 interrupt가 partial rollback 유발 | ACCEPT | logical commit을 cleanup보다 먼저 표시하고 cleanup을 post-commit GC로 제한 |
| framework overlay symlink를 domain scanner가 먼저 읽음 | ACCEPT | 전체 overlay leaf path를 먼저 검증하고 오류 시 scanner 호출 전 반환 |
| generated YAML+JSON 공존을 차단하는 compatibility regression | SELF-FOUND / ACCEPT | compiled YAML과 JSON exact equality를 요구하고 정상 pair/stale pair 테스트 추가 |

### Round 3

| Finding | Decision | Result |
|---|:---:|---|
| fingerprint와 backup rename 사이 concurrent replacement 유실 | ACCEPT | rename된 backup을 recorded original과 즉시 재대조하고 drift 시 rollback으로 concurrent 값 복귀 |
| staged render 재쓰기의 직전 output 소유권 미검증 | ACCEPT | repeated `stage_write`가 exact recorded output 불일치 시 overwrite 전 차단 |
| lock 생성 이후 destination realpath 변경 | ACCEPT | 모든 lock 획득 직후 canonical identity를 재검증하고 변경 시 lock 해제/차단 |
| shared lock root 소유권/권한/symlink 미검증 | ACCEPT | effective-UID별 0700 root와 lstat owner/type/mode 검증 |
| manifest symlink를 preflight 전에 읽음 | ACCEPT | manifest read 전 project-contained ancestor/regular leaf 검증 |
| Python equality가 bool/int 타입 drift를 허용 | ACCEPT | key/value type까지 보존하는 recursive exact data equality 적용 |
| umask 조회 중 control signal/thread race | ACCEPT | process-global `os.umask` 조회 제거, secure exclusive temp 생성 mode에 OS umask 직접 적용 |

### Closure

| Finding | Decision | Result |
|---|:---:|---|
| falsy YAML non-mapping이 빈 profile로 축소됨 (`019f6e08-a167-7600-9e6b-5fd294f7f7ec`) | ACCEPT | `None`만 `{}`로 정규화하고 `false`/`0`/`[]`/`""` no-mutation regression 추가 |
| fresh closure re-review `019f6e12-0bde-7452-a55b-ac37d331be05` | CLEAN | `CLEAN_FOR_FB15_CLOSURE`, P0-P2 none |

## 4. Verification Summary

- Focused transaction/install/overlay after round 1: 136 passed.
- Full Python: 1,183 passed, 1 skipped.
- Official `run-all.sh`: `ALL HOOK TESTS PASS`.
- Diff whitespace: PASS.

Round 3 rework focused verification:

- Transaction/install/overlay: 153 passed (20 + 112 + 21).
- Full Python: 1,200 passed, 1 skipped.
- Official `run-all.sh`: `ALL HOOK TESTS PASS`.
- Diff whitespace: PASS.
- Initial closure P2 accepted and fixed; fresh re-review CLEAN.
- Post-closure focused/full/official results remain 153 / 1,200+1 skipped / PASS.

Round 2 focused verification:

- Transaction/install/overlay: 144 passed (15 + 108 + 21).
- Full Python: 1,191 passed, 1 skipped.
- Official `run-all.sh`: `ALL HOOK TESTS PASS`.
- Diff whitespace: PASS.

## 5. Residual Boundary

Lock은 SAGE install끼리의 경쟁을 직렬화하고 CAS는 preflight 이후 핵심 입력 변경을 탐지한다. 동일 OS 계정의
비협조 프로세스는 어느 로컬 검사 직후에도 다시 파일을 바꿀 수 있으므로 절대적 권위 경계가 아니다. 성공 후
무결성은 `sage validate`, 원격 권위는 FB-08 attestation이 담당한다. 독립 리뷰는 이 제한을 현재
same-permission local boundary로 확인했고, 이번 실패 원자성 계약의 잔여 위험으로 명시 수용한다.
