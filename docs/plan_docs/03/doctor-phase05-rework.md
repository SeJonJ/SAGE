# Phase 05 지적에 따른 doctor·오류 표시 최소 수정

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: REWORKED — 소유 영역 개발 회귀 확인, 전체 05 판정은 parent 담당

## 근거와 수정 범위

[05 기록](../05/overlay-context-delivery.md)의 R1-08 및 CONV-R1-01과 `overlay-context-phase05-20261106/reproductions-corrected/results.json`을 읽고 수정했다. 최초 잘못된 인자의 doctor 재현을 제품 결함의 근거로 사용하지 않았다. 정확한 root/profile/manifest 인자에서 nested `hooks:null`이 list 전제 comprehension에 들어가 `'NoneType' object is not iterable`을 일으킨 경로가 원인이다. `systematic-debugging` 절차에 따라 원인을 확인하고 실패 검사를 먼저 만들었다.

- `sage/commands/doctor.py`: JSON 문서, hooks mapping, event별 list, block mapping, block의 hooks list, handler mapping, matcher 문자열을 확인하는 입력 경계를 추가했다. 손상된 구조는 기존 `native_registration=invalid` 진단으로 수렴한다. 정상 빈 등록은 `incomplete`로 구분한다. 파일 본문이나 예외 원문은 출력하지 않는다. doctor의 정보성 exit 정책은 바꾸지 않았다.
- `scripts/sage_harness/hooks/runtime/overlay_context.py`: 오류 표시 함수만 `error_message(issue, root=None)`로 확장했다. 명시 root에는 기존 hook `i18n.context.resolve(root)`를 사용하고, root가 없으면 cwd를 추측하지 않고 기본 ko를 쓴다. 표시 설정의 예외 원문은 내보내지 않는다. 수집·검증 판정의 `current`는 수정하지 않았다.
- 기존 hook 메시지 소유자인 `runtime/i18n/ko.py`, `en.py`의 `FRAGMENTS`에 `hook.overlay_delivery.input_error` 한 쌍을 추가했다. `templates/core/framework/docs/agent/language-policy.md`에서 hook은 local profile→ko의 단일 언어이고 bare sage만 bilingual 예외다. 따라서 이전 ko+en hardcode는 정책 충돌로 확인했다. 오류 code/path와 gate 판정은 동일하고 사람 안내문만 선택 언어로 표시한다.
- `test_doctor.py`: 정확한 nested-null 재현, 두 host의 잘못된 중첩 형태 30조합, 정상 빈 등록, ko/en 메시지 소유자, root 부재 시 cwd 미조회, validator 예외 원문 비노출 회귀를 추가했다.

## RED → GREEN과 실제 명령

작업 위치는 `/Users/sejon/project/sage_project_worktree/overlay-context-delivery`다. 아래 `PY`는 `/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`, 원자료 폴더 `D`는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/doctor`다.

| 명령 | 실제 결과 | 원자료 |
|---|---|---|
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -k nested_null -q` | 수정 전 rc 1, 1 test ERROR, 정확한 NoneType iterable 예외 | `D/r1-08-red.log` |
| 동일 명령 | 수정 후 rc 0, 1 test OK | `D/r1-08-green.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -k registration -q` | rc 0, 4 tests OK; 두 host malformed 30조합 포함 | `D/registration-shapes-green.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -k OverlayErrorLanguage -q` | 수정 전 rc 1, 3 tests 중 bilingual 1 FAIL, root 선택 인자 부재 3 subtest ERROR | `D/conv-r1-01-red.log` |
| 동일 명령 | 수정 후 rc 0, 3 tests OK | `D/conv-r1-01-green.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -q` | rc 0, 48 tests OK | `D/doctor-full-green.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_language_context.py -q` | rc 0, 44 tests OK | `D/language-context-regression.log` |

기존 corrected consumer를 `D/corrected-doctor-fixture`로 복사하고 `.codex/hooks.json`에 원 재현과 같은 `{"hooks":{"SessionStart":[{"hooks":null}]}}`을 넣어 새 제품의 정확한 `_report_overlay_delivery(root, profile, {})` 인자로도 재검사했다. 예외 없음, 반환값 None, `[codex] native_registration=invalid`를 확인했다(`D/r1-08-corrected-fixture-green.json`). 이 함수 결과를 doctor 전체 CLI의 새 nonzero 정책으로 확대하지 않았다.

`test_*i18n*.py` 패턴 실행은 0 tests였으므로 회귀 PASS의 근거로 세지 않았다. 실제 언어 회귀는 위 `test_language_context.py` 44개다.

## 추가 R1-05 역할 식별 최소 수정

parent의 실제 Claude `--agent diagnostic-root` 관측(`runtime`의 별도 원자료)에서 main SessionStart/UPS에 `agent_type`만 존재하고 child id는 없었다. 기존 코드가 generic agent_type을 child로 해석하여 root catalog를 억제했다. parent 요청으로 같은 `overlay_context.py`의 `role_for`에서 `agent_type` 단독을 child 증거에서 제외했다. `agent_id`, `parent_session_id`, `parent_thread_id`는 양성 child 증거로 유지하고 명시 `SAGE_OVERLAY_ROLE`의 우선순위도 유지한다.

- `$PY D/reproduce_agent_type_role.py` → 수정 전 rc 1, agent_type 단독 actual child / expected root (`D/r1-05-role-red.log`).
- 동일 명령 → 수정 후 rc 0, main agent_type/root, 실제 세 child marker, 빈 event/root, 명시 reviewer 역할 우선순위 확인 (`D/r1-05-role-green.log`).
- 실제 native main/child 재시험과 runtime caller의 `root=root` 연결은 runtime 담당/parent 소유다. 이 직접 함수 시험을 native acceptance로 세지 않는다.

## 파일 식별과 미해결 경계

최초 doctor·언어·역할 5파일 freeze 시점은 `2026-11-06T03:49:17Z`다. 해당 파일별 SHA-256 및 그 시점 aggregate `sha256:46eeb88ab7d5e1c9da85a6faf9758d1c33d0ccc475b8fc5c4c7ec76eb8076c36`을 `D/source-hashes.json`에 보존했다. aggregate는 다른 담당의 병렬 수정 중 관측값이며 통합 acceptance의 최종 pin이 아니다.

runtime 호출부 연결, 새로운 literal inventory 재생성, 전체 통합 검증 및 05 재검토는 parent 담당이다. native 신뢰/지원 또는 모든 05 finding의 해소로 보고하지 않는다. 전역 설치, SAGE 자기 승인 gate/review-loop, commit/push는 수행하지 않았다.

## 추가 R1-04 혼합 설치의 공유 본문 유실 방지

parent가 새 package와 `8e17a88`의 구형 project runtime/CORE 및 API-1 manifest를 결합한 실제 재현을 전달했다. `runtime/mixed-old-runtime/result.json`에서 SessionStart rc 0, shared before true / after false, selector·collector·catalog 모두 없음이 관측되었다. 새 `overlay_materialize`의 무조건 legacy span 제거가 원인이었다.

`install.py`의 실제 순서는 step 4 새 runtime 복사 → step 5 새 CORE 복사 → materialization → step 6 manifest 기록이다. 그래서 manifest API-2 값만 요구하면 정상 staging을 막는다. 또한 현재 bundle과 runtime 바이트가 완전히 같아야 한다는 조건은 안전한 호환 API-2 설치까지 package patch마다 막는 과도한 조건이므로 채택하지 않았다.

`overlay_materialize.py`의 실제 legacy span 제거 직전에만 아래 지원 형태를 읽기 전용으로 확인한다.

- span 밖 CORE base가 해당 id의 기존 current target, `targets[id]`, schema-2 selector 계약을 포함한다.
- 기존 layout resolver가 선택한 설치 runtime의 `overlay_context.py`와 `hook_runtime.py`가 root 내부 안전한 일반 파일이며 Python AST로 읽을 수 있다.
- 설치 overlay `current`에 `collect_catalog`와 `render_catalog` 호출 및 `merge_output` 함수가 있다.
- 설치 SessionStart와 UPS 함수 각각에서 실제 AST `overlay_context.current`, `overlay_context.merge_output`과 해당 host 응답 renderer 호출이 존재한다. 주석에 호출 문자열을 넣은 경우는 통과하지 않는다.

이것은 **호환 지원 형태 검사**다. 코드 실행·native 전달·진위·무결성을 인증하지 않는다. 기존 CORE/base hash와 validate 권위 및 실제 native acceptance를 대체하지 않는다. 새 scalar marker/상태 DB를 만들지 않는다. span이 없으면 검사하지 않으며 `context_validated=True`도 CORE selector 부재를 면제하지 않는다.

지원이 없으면 legacy shared span과 나머지 bytes를 보존하고 `overlay.context_upgrade_required`를 반환한다. CLI `sage/i18n/ko.py`, `en.py`와 기존 hook owner의 ko/en에 진단 쌍을 추가했다. 구형 runtime의 i18n에는 새 key가 없을 수 있으므로 Diagnostic의 고정 machine evidence에 `sage upgrade --apply`를 담아 기존 message-key fallback에서도 수리 명령이 남게 했다. 개인 본문과 예외 원문은 evidence로 넣지 않는다.

| 명령 | 실제 결과 | 원자료 |
|---|---|---|
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_materialize.py -k LegacyContextCapability -q` | 수정 전 rc 1, 3 tests 중 8 subtest FAIL | `D/r1-04-materialize-red.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_materialize.py -q` | 수정 후 rc 0, 40 tests OK | `D/r1-04-materialize-green.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_install.py -k OverlayContext -q` | rc 0, 3 tests OK | `D/r1-04-install-upgrade-rollback-green.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_overlay_*.py' -q` | rc 0, 182 tests OK | `D/overlay-regression-after-r104.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -q` | rc 0, 48 tests OK | `D/doctor-regression-after-r104.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_language_context.py -q` | rc 0, 44 tests OK | `D/language-context-regression-after-r104.log` |

새 회귀는 구CORE/구runtime/한쪽만 새 버전일 때 shared 원문 보존, context validated flag로 우회 불가, 안전한 호환 runtime의 바이트 차이 허용, 손상 AST·주석만 있는 가짜 연결 거부, 실제 새 CORE/runtime에서는 소유 span 제거, 기존 foreign/malformed 거부를 확인했다. 기존 owned-span 정상 제거 fixture는 실제 bundle의 selector와 runtime 파일을 배치하도록 정렬했다.

추가 install fixture에서는 구형 CORE와 runtime을 만든 뒤 force upgrade가 새 지원 파일을 먼저 설치하고 source 원문을 유지하는 것을 확인했다. manifest 작성 시점에 실패를 주입하면 전체 이전 tree가 동일 bytes로 복구되어 legacy span과 구runtime도 복원되었다. 두 경우 모두 전역 설치 없이 임시 consumer에서 시험했다.

R1-04 추가 10파일 freeze의 `2026-11-06T03:56:53Z` 관측 aggregate는 `sha256:6450e36ece176d4216f87c51622e173de9409923f90b8e22d9285e970a41e809`이며 각 파일 SHA-256은 `D/source-hashes-after-r104.json`에 있다. 이것도 parent의 최종 통합 pin을 대신하지 않는다. 제품·테스트 10경로 `git diff --check`는 rc 0이었다. parent의 최종 freeze 통보 이후 제품/테스트 수정은 하지 않았다. 혼합 설치 native 재시험, 전체 통합, 독립 리뷰 최종 판정은 parent/runtime 담당이 기록한다.

## 유효 R1 재검토 후 C4-P-02·C4-P-03 보완

`round1-triage.json`, `peer-repro-r1/results.json`과 두 whole-round refuter의 결과를 확인했다. C4-P-02와 C4-P-03은 양쪽 모두 upheld였다. C4-P-04의 no-span 구설치 기능 활성화 주장은 두 refuter가 반증했으므로 guard 범위를 확대하지 않았다. 아래 원자료 `E`는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/doctor-round2`다.

### C4-P-02 — root routing 블록 수렴

root context 분기가 legacy shared span만 제거하고 `insert_routing_block` 이전에 반환한 것이 원인이었다. `_materialized_render`와 `plan_blocked_cleanup`의 context 경로 모두 기존 routing helper로 routing 블록을 제거한다. routing이 없으면 helper가 받은 문자열을 그대로 반환하므로 다른 bytes와 trailing newline을 바꾸지 않는다. legacy shared span의 실제 삭제 전에만 기존 capability guard를 적용하는 범위는 유지했다. guard에는 routing이 아닌 실제 CORE base를 공급해 routing 본문이 selector를 대신할 수 없게 했다. 손상·foreign marker 충돌 처리는 유지했다.

- RED: `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_materialize.py -k ContextRouting -q` → rc 1, 3 tests 중 3 subtest FAIL (`E/p02-red.log`).
- GREEN: `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_materialize.py -q` → rc 0, 43 tests OK (`E/p02-green.log`).
- 양 host routing-only root의 read-only plan은 변경 필요를 반환하며, cleanup과 materialize가 routing을 제거한다. 무routing/무shared span의 전체 bytes 보존, legacy capability·foreign/malformed 거부도 회귀로 확인했다.
- runtime 회귀에서는 양 host UPS가 pending routing을 native block으로 보고 정확한 외부 sync 명령을 안내하고 개인·routing 본문을 출력하지 않았다. 외부 수렴 후 새 catalog가 공급되었다. `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_runtime_delivery.py -q` → rc 0, 33 tests OK (`E/runtime-green.log`).

### C4-P-03 — 오류별 외부 복구와 읽기 전용 doctor

hook의 기존 단일 언어 owner에서 오류 code별 안내를 선택한다. profile pair mismatch는 외부 hook/profile generate, pending render는 외부 `sage sync-overlays`, legacy capability는 외부 `sage upgrade --apply`를 안내한다. 다른 입력 오류의 일반 외부 수리 안내와 실패 판정은 유지한다.

profile generate의 기본 Claude target이 Codex-only 등록을 변경하지 않도록, 해당 오류에서만 root의 안전한 기존 manifest를 읽어 `installed_hosts`에 맞는 claude/codex/both target을 명시한다. 구 영수증은 `host_runtime`을 사용하고, 부재·손상·symlink 경로는 target을 추측하지 않고 `<claude|codex|both>` 선택을 명시한다. 기존 설치 host를 유지하고 양쪽을 쓰면 both를 선택하라는 설명을 함께 낸다. runtime 인자나 entry 코드, manifest 값은 변경하지 않았다.

실제 gate entry는 collector보다 먼저 `entry.profile_pair_mismatch`를 낼 수도 있으므로, 그 기존 ko/en FRAGMENTS 두 문장도 외부 프로젝트 터미널·정확한 target 명령·기존 설치 host 유지·필요시 외부 sync 안내로 마지막 보정했다. 최초 entry 시험은 profile preflight 대상이 아닌 generated-artifact guard를 골라 collector 경로가 호출되었으므로, 그 실패를 entry 결함 재현으로 세지 않았다. `_PROFILE_HOOKS`를 확인한 후 실제 `pre-implementation-gate` CLI로 정정했다.

`doctor`는 catalog 입력의 유효성과 별개로 host별 `render_sync=CURRENT|REQUIRED|INVALID`를 출력한다. collector가 성공한 경우 실제 `current`와 같은 `plan_materialize(..., context_validated=True)` 읽기 전용 계획을 사용한다. pending plan은 REQUIRED, planning/input 오류는 해당 code의 INVALID다. 개인 본문·렌더 본문·예외 원문은 출력하지 않는다. 파일 bytes 불변과 materialization 적용 함수 미호출을 검사했다. budget·지원/신뢰의 별도 UNVERIFIED 및 doctor 정보성 exit 정책은 바꾸지 않았다.

| 실제 명령 | 결과 | 원자료 |
|---|---|---|
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -k render_sync_diagnostic -q` | RED rc 1, 1 test의 4 상태 FAIL | `E/p03-doctor-red.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -k issue_specific -q` | RED rc 1, 1 test의 6 ko/en 조합 FAIL | `E/p03-message-red.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -k preserves_installed_hook_targets -q` | RED rc 1, 5 target 조합 FAIL | `E/p03-target-red.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -k entry_profile_pair_mismatch -q` | 정정된 RED rc 1, 양 host 외부 명령 안내 FAIL → GREEN rc 0 | `E/p03-entry-corrected-red.log`, `E/p03-entry-green.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_overlay_*.py' -q` | rc 0, 188 tests OK | `E/overlay-final-green.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -q` | target 보정 후 rc 0, 51 tests OK; 마지막 entry 보정 후 결과는 아래 추가 | `E/doctor-final-green.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_language_context.py -q` | rc 0, 44 tests OK | `E/language-final-green.log` |

### 안내한 명령의 실제 소비자 복구 시험

격리 임시 consumer에만 CLI를 실행했다. source tree나 전역 설치를 바꾸지 않았고 엔진 자신의 승인 근거로 사용하지 않는다.

- YAML 편집 후 pair mismatch를 재현하고 `sage generate --kind hook --write`를 실행하여 rc 0 및 `current` issue 없음으로 복구했다. physical worker overlay의 pending render는 `sage sync-overlays`로 rc 0 및 issue 없음으로 복구했다.
- legacy shared span과 구 CORE/runtime을 재현한 뒤 `sage upgrade --apply`가 rc 0으로 CORE와 hook을 실제 교체했다. source 원문은 보존되고 `current` issue가 없어졌다. 단지 API marker나 선언만 바뀐 것으로 세지 않았다. 설치된 sage-team CORE bytes가 bundle과 동일한 SHA-256 `5e79b5779adbe2c2694beed898be48ab48d3107cbc8087669f888a7c9596f2cb`인 것을 별도 확인했다. 실제 hook의 context 호출 존재, 설치 API 3도 기록했다 (`E/recovery-command-results.json`, `E/upgrade-artifact-check.json`). 이 시험의 before/after source hash는 `sha256:377417e376be773d48241efc6d45f2d442eb8c3c3eaa06dcfb7bcff9e15f1ca3`로 동일했다.
- target 보정 후 Claude-only, Codex project-local-only, 양 host consumer를 각각 설치하고 안내된 `sage generate --kind hook --write --target claude|codex|both`를 실제 실행했다. 모두 rc 0, pair issue 해소, 기존 등록 surface 유지가 확인되었다. 특히 Codex-only에는 `.claude/settings.json`이 생기지 않았고 Claude-only에는 `.codex/hooks.json`이 생기지 않았다 (`E/recovery-target-results.json`). before/after source hash는 `sha256:477051110b91eb29e0a7d64dae52fec8710c71fb0edff32c9e2e48f688b9db2b`로 동일했다.

마지막 entry 메시지 보정 후 `2026-11-06T11:45:33Z` 관측 aggregate는 `sha256:59a43307c6afc428b2bf3442a19d4e18bf9f5097a57aaecf4adcdc69a88bd534`다. 소유 제품/테스트 8경로의 개별 hash는 `E/source-hashes-final-entry.json`에 보존했다. 해당 8경로 diff check는 rc 0이었다. parent에게 제품/테스트 freeze를 통보했고 이후에는 문서·해시 근거만 추가했다. 전체 R10·wheel·C5 snapshot·R2 독립 판정은 parent 담당이다.

마지막 entry 보정 후 doctor 전체를 다시 실행한 실제 결과는 rc 0, 52 tests OK다 (`E/doctor-entry-final-green.log`). 양 host 실제 entry의 차단 rc 2·`entry.profile_pair_mismatch`·영어 선택 유지·profile marker 비노출·외부 target 명령을 함께 확인했다. 이 마지막 보정의 수정 파일은 기존 hook i18n 두 파일과 `test_doctor.py`뿐이며 entry/runtime 판정 코드는 변경하지 않았다.

## 재시작 리뷰 F03 — dual-host local upgrade 순서 최소 수정

두 refuter가 upheld한 F03과 `overlay-context-phase05-restart-20261106/repro-LIFE01.json`, `reproduce_life01.py`를 확인했다. 실제 `8e17a88` installer/generate/sync로 두 host에 공유 span을 만든 소비자에서 새 upgrade가 primary CORE만 갱신하고 all-host sync를 실행해 secondary의 구 selector guard에 막힌 뒤 rc 1로 롤백되는 경로였다.

수정 소유는 `sage/commands/upgrade.py`, `test_upgrade.py`, 이 03 기록으로 제한했다. `_plan`이 기존 manifest의 primary·installed hosts·scope 영수증으로 CORE staging 목록을 한 번 고정한다. 기존 `core-assets` 단계 안에서 기존 primary install 다음 secondary의 **project-local Codex 또는 Claude local**만 기존 `install.run`에 위임한다. 그 뒤 기존 generate→all-host sync→validate 순서가 이어진다. apply에서 manifest를 다시 읽어 staging 대상을 계산하지 않는다.

- secondary Codex global/disabled는 추가 staging하지 않는다. primary Claude + secondary Codex global에서 새 외부 global 쓰기나 rollback 소유를 만들지 않았다.
- 기존 primary Codex global 선택은 유지한다. 그 기존 동작의 외부 쓰기를 새로 root rollback에 포함한다고 주장하지 않는다.
- 선언된 Codex 설치의 scope가 missing/malformed이면 기존 no-scope blocker로 mutation 전에 중지한다. global로 추측하지 않는다.
- root의 양 host 경로는 기존 upgrade snapshot 범위에 이미 들어 있다. 새 transaction framework·service·public CLI 인자·global write scope를 추가하지 않았다.
- 기존 `host_runtime`, `installed_hosts` 순서, host별 scope를 보존했다. 각 설치가 갱신하는 버전/hash 영수증은 기존 install 소유로 남겼다.

아래 `U`는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106/upgrade-f03`다. 모든 실제 fixture를 이 폴더 아래에 두었고 실사용 프로젝트·전역 설치는 사용하지 않았다. `PYTHONPATH`는 현재 source worktree, `TMPDIR`는 `U/unit-tmp`로 지정해 소비자 hook subprocess도 같은 package를 보도록 했다.

| 실제 명령/관측 | 결과 | 원자료 |
|---|---|---|
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_upgrade.py -k DualHostLocal -q` | 최초 RED: 6 tests, 9 subtest FAIL. 그중 secondary-global의 smoke import 실패는 아래 harness 한계로 제외 | `U/red.log` |
| 동일 scoped 명령 | 수정 후 rc 0, 6 tests OK | `U/green-final.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_upgrade.py -q` | primary-global 기존 선택·missing receipt 검사까지 포함한 최종 rc 0, 68 tests OK | `U/upgrade-suite.log` |
| `$PY U/reproduce_actual_dual.py` | 실제 old-source 재현에서 primary Claude와 primary Codex 모두 새 upgrade rc 0 | `U/actual-dual-results.json`, host별 stdout/stderr |
| 소유 제품/테스트 두 경로 `git diff --check` | rc 0 | 도구 실행 출력 |

새 회귀는 양 primary 방향의 dual-local 업그레이드, validate 단계 직전의 late failure에서 root bytes/mode 롤백, secondary-global의 새 install 호출·global writes 없음, 계획 후 manifest scope를 바꿔도 고정한 staging을 사용하는 것, disabled/missing/malformed scope의 global 비선택, 기존 primary-global 선택 보존을 확인했다. root rollback은 기존 계약인 bytes/mode로 대조했고 managed 파일 mtime까지 복원한다고 주장하지 않는다. 실패 보고서는 기존 계약대로 남는다.

첫 수정 후 실행 중 한 fixture install에서 다른 담당의 runtime resource 변경에 따른 source fingerprint drift가 발생했다. 그 실행은 통과 근거로 세지 않았다(`U/green.log`). 다른 실패에서는 in-process upgrade가 띄운 consumer smoke subprocess에 source package 경로가 전달되지 않아 `validator_unavailable`을 반환했다. test 환경의 `PYTHONPATH` 전달을 고쳤으며 product의 validator/gate를 완화하지 않았다(`U/green2.log`). 최초 RED 중 해당 harness 실패도 F03 제품 결함의 별도 증거로 세지 않는다. 실제 원인 귀속은 원 old-source 재현과 양 refuter의 caller trace에 따른다.

실제 old-source 검사는 보존된 `repro-LIFE01/source-base`의 `8e17a88` 코드를 사용해 두 설치 순서를 각각 처음부터 만들고 old generate·old sync를 실행했다. 양 host의 legacy 본문 존재를 확인한 뒤 current `upgrade --apply --force`를 실행했다. 두 경우 모두 양 host에 새 selector가 설치되고 shared source가 보존되었다. primary/installed host 순서/scope는 전후 동일했고, 별도로 지정한 미사용 global directory도 생성되지 않았다. model call은 하지 않았다.

실제 재현의 source before/after는 모두 `sha256:93d541024b737af26048290415aa8b513855330ef411aa9e591d2ded5efbb611`이었다. `2026-11-06T13:11:31Z`에 같은 aggregate와 아래 두 파일 hash를 `U/source-hashes.json`에 보존했다.

- `sage/commands/upgrade.py`: `8a438530f9609c2aed1a719e655622820385c74f3b00c9dd2831af666f5a5461`
- `scripts/sage_harness/hooks/tests/test_upgrade.py`: `0558bbddbcbf92eb502bfc6cc584f8a2148b5466150d9f9939f0ea7097323107`

제품/테스트 freeze를 parent에게 통보했다. F01 materialize, F02 collector, F04 runtime은 다른 담당 소유이며 이 수정에서 건드리지 않았다. 전체 통합·새 snapshot·독립 리뷰 종료 판정은 parent 소유다. commit/push, model call, 실사용 설치, 엔진 자기 승인 gate/review-loop는 수행하지 않았다. consumer 내부 validate는 격리 제품 회귀이며 엔진 변경 승인으로 사용하지 않는다.
