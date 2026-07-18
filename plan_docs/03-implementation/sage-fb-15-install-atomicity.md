# [Implementation] SAGE-FB-15 install preflight-first와 실패 원자성

Cycle-Stem: `sage-fb-15-install-atomicity`
Status: IMPLEMENTED_REVIEWED

## 0. Pre-Implementation Declaration

- Risk: L3 installer trust and mutation boundary.
- Compound rule: overlay policy, filesystem mutation, global skill, manifest가 교차하므로 최고 L3 적용.
- Required phases: 00~06.
- Review: 개발 완료 전 Claude 3회; Claude 오류/사용량 제한 시 매 회 fresh read-only headless session, no subagents.
- Components: SAGE engine only. ChatForYou Backend/Frontend/Desktop N/A.
- References: FB-12/14 Phase 05/06, 요구사항 SSOT, current install/materialization tests.

## 1. Planned Files

- `sage/install_transaction.py`: lock, fingerprint, rollback journal.
- `sage/commands/install.py`: preflight-first ordering and transaction wiring.
- `sage/overlay_materialize.py`: render-independent overlay/domain preflight.
- `scripts/sage_harness/hooks/tests/test_install.py`: command-level atomicity/concurrency regressions.
- `scripts/sage_harness/hooks/tests/test_install_transaction.py`: journal primitive tests.

## 2. Checklist

- [x] Split pure overlay/domain preflight.
- [x] Add destination lock and filesystem fingerprint.
- [x] Journal project/global writes and legacy prune.
- [x] Roll back all post-preflight failures.
- [x] Add force/global/concurrency/CAS tests.
- [x] Run full regressions.
- [x] Complete three independent reviews and triage.

## 3. Implemented Behavior

- `overlay_materialize.preflight_overlays`가 profile/domain/overlay inventory, eligibility, marker, relaxation을
  installed render 없이 검사하며 `plan_materialize`도 같은 helper를 재사용한다.
- NFC/casefold canonical path identity를 항상 유지하고 existing destination의 device/inode identity를 함께
  잠그는 non-blocking process lock이 생성 전후, symlink 및 case alias의 중복 `sage install`을 차단한다.
- `InstallTransaction`은 첫 mutation 전에 기존 object를 same-parent backup으로 이동하고 모든 write/remove의
  declared root 및 non-symlink ancestor를 검사한다. rollback은 installer-owned 출력만 제거해 원본 object를
  복귀시키며 concurrent output drift나 missing backup은 현재 값/backup을 보존한 채 명시적 충돌로 남긴다.
- Project `_write`/copy, materialization writer, Codex global skill, legacy prune, manifest가 한 journal을 공유한다.
- profile, manifest, overlay tree, CORE render/ancestor, global skill/legacy tree fingerprint가 preflight 이후 drift를
  optimistic CAS로 차단한다.
- 배포 source content hash를 preflight와 생성 예정 manifest에 결속해 실행 중 source 교체로 인한 혼합 설치를
  rollback한다.
- FB-12 exact blocked managed-block cleanup은 base/manifest를 건드리지 않는 명시적 보안 예외로 유지한다.
- YAML 원본과 현재 materialization에 일치하는 생성 JSON의 공존을 허용하고 동일 loader로
  preflight/materialization에 사용한다. stale JSON은 mutation 전에 차단하며 JSON-only 호환성도 유지한다.
  project profile과 overlay inventory의 symlink/non-regular 입력은 읽기 전에 거부한다.
- write journal과 semantic 예상 출력을 실제 mutation 전에 기록한다. final input/output/source CAS 직후 logical
  commit하고 backup 제거는 post-commit GC로 수행하며 성공 보고는 그 뒤에 수행한다. catch 가능한
  `BaseException`은 rollback 후 control signal을 재전파한다. SIGKILL/전원 중단은 보장 범위 밖이다.

## 4. Failure Injection Evidence

- first install N번째 write 실패: destination tree empty 복구.
- force N번째 write 실패 및 manifest replace 직후 실패: exact project tree 복구.
- materialization 첫 변경 직후 실패: render와 manifest bytes 복구.
- force 후반 실패: legacy skill tree와 Codex global CORE skills 복구.
- preflight 이후 overlay drift: install-owned CORE/manifest rollback, 외부 overlay 변경은 보존 후 차단.
- preflight 이후 SAGE source resource drift: 첫 install 전체 rollback.
- lock contention: 두 번째 holder가 `InstallBusyError`, release 후 재획득 성공.
- Round 1 보강: non-render/global ancestor symlink 차단, case alias lock, concurrent rollback 보존, backup missing
  fail-closed, commit-before-report, `KeyboardInterrupt` rollback, malformed JSON/symlink profile preflight.

## 5. Review Round 1

- Claude fresh headless: session quota 초과(`resets 12:30pm Asia/Seoul`), 리뷰 증거로 계산하지 않음.
- User-authorized fresh Codex headless fallback: `019f6dcb-c880-7ed3-a79c-4017c341e6b8`.
- Verdict: BLOCK, 2 P0 + 4 P1. 여섯 finding 모두 재현/코드 대조 후 수용.
- Fixed: 전체 mutation ancestor guard, conflict-preserving rollback와 missing-backup 오류, inode lock,
  commit 직전 CAS, catchable BaseException rollback, unified safe JSON/YAML profile preflight.
- Scope correction: memory journal은 process crash durable atomicity를 제공하지 않음을 00~02에 명시.

## 6. Verification After Round 1

- `test_install.py`: 105 passed.
- `test_install_transaction.py`: 11 passed.
- `test_overlay_materialize.py`: 20 passed.
- focused aggregate: 136 passed.
- full Python: 1,183 passed, 1 skipped.
- official `run-all.sh`: `ALL HOOK TESTS PASS`.
- `git diff --check`: PASS.

## 7. Review Round 2

- Claude fresh headless: `570f9992-8321-4da6-8b5a-39aeaff270bf`, session quota 초과로 리뷰 증거에 미포함.
- User-authorized fresh Codex headless fallback: `019f6de1-c15a-73b0-a8a2-ef7b7048d25a`.
- Verdict: BLOCK, P1 3건 + P2 1건. 네 finding 모두 코드 경로와 중단 지점을 재현해 수용.
- Fixed: 생성 전후 동일 canonical path lock 유지, mutation 전 write-ahead journal, logical commit 이전 backup
  삭제 제거, framework overlay leaf 안전검사를 domain scanner보다 선행.
- Independent compatibility finding: 정상 `sage generate`가 YAML 옆에 생성하는 JSON을 dual-format 오류로
  차단하던 round-1 수정 결함을 발견했다. YAML materialization과 JSON의 exact equality 검증으로 교정했다.

## 8. Verification After Round 2

- `test_install.py`: 108 passed.
- `test_install_transaction.py`: 15 passed.
- `test_overlay_materialize.py`: 21 passed.
- focused aggregate: 144 passed.
- full Python: 1,191 passed, 1 skipped.
- official `run-all.sh`: `ALL HOOK TESTS PASS`.
- `git diff --check`: PASS.

## 9. Review Round 3

- Claude fresh headless: `abe8ec5f-8998-4623-8604-d52e5be43991`, HTTP 429 session quota로 리뷰 증거에 미포함.
- User-authorized fresh Codex headless fallback: `019f6df7-6b78-7160-996c-8128fb365793`.
- Verdict: BLOCK, P1 3건 + P2 4건. 일곱 finding 모두 구체적 실패 순서와 코드 경계를 대조해 수용.
- Fixed: backup rename 직후 original 재검증, repeated staged write의 output ownership 재검증, lock 획득 중
  destination identity 재검증, user-scoped 0700 lock root 검증, manifest read 전 symlink/regular-file 검증,
  profile deep type equality, process-global umask 조회 제거.

## 10. Verification After Round 3 Rework

- `test_install.py`: 112 passed.
- `test_install_transaction.py`: 20 passed.
- `test_overlay_materialize.py`: 21 passed.
- focused aggregate: 153 passed.
- full Python: 1,200 passed, 1 skipped.
- official `run-all.sh`: `ALL HOOK TESTS PASS`.
- `git diff --check`: PASS.

## 11. Closure Reviews

- Claude fresh headless: `c87bf21f-abee-4424-bffc-9602fc7fb0cb`, HTTP 429 session quota로 리뷰 증거에 미포함.
- Initial closure fallback: `019f6e08-a167-7600-9e6b-5fd294f7f7ec`, P2 1건.
- Decision: ACCEPT. `yaml.safe_load(text) or {}`가 `false`, `0`, `[]`, `""`를 빈 profile로 축소해
  non-mapping 오류를 조용히 통과시키는 것을 재현했다.
- Fixed: YAML `None`만 빈 mapping으로 정규화하고 falsy non-mapping 네 종류의 install no-mutation
  regression을 추가했다.
- Fresh closure re-review: `019f6e12-0bde-7452-a55b-ac37d331be05`.
- Final verdict: `CLEAN_FOR_FB15_CLOSURE` (P0-P2 none).
- Post-closure focused aggregate: 153 passed.
- Post-closure full Python: 1,200 passed, 1 skipped.
- Post-closure official `run-all.sh`: `ALL HOOK TESTS PASS`.
