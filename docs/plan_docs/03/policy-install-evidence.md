# Overlay context delivery — policy/install 03 개발 근거

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: IMPLEMENTED — 소유 영역 결정적 개발 회귀만 검증, 04~06 미진행

## 소유 변경

- `sage/overlay_classify.py`: 적용 자격(`classify`)과 전달 방식(`delivery_mode`)을 분리했다. root 7종은 context, 기존 자격 worker 4종은 physical이다. `ROOT_CONTEXT_TARGET_SOURCES`를 collector와 공유한다. Fast 세 대상의 BACKING에 실제 실행 가능한 독립 oracle과 이름이 존재하는 적대적 테스트를 연결했다. 미분류 자산의 fail-closed는 유지한다.
- `sage/overlay_materialize.py`: root 7종의 `expected_block`은 source 존재 여부와 무관하게 빈 문자열이다. 정상 v1 마커와 정확한 대상 kind/id 헤더를 확인한 legacy span만 제거한다. 나머지 CORE/사용자 바이트와 trailing newline, 원본 source를 보존한다. 손상/외부 대상 span은 충돌이다. worker 물리 합성은 유지한다. install/sync/L1/validate가 이 정책을 공유한다.
- `sage/commands/install.py`: force upgrade도 context span 손상/소유 불명을 overwrite 전에 거부한다. force 설치 후 표준 shared/personal source가 Fast에 상속되는 경로를 본문 없이 안내한다. 개인 source 경로는 기존 `sage/asset_overrides.local`이다.
- `sage/commands/generate.py`: generated-artifact-write-guard를 양 host `matcher: "*"`로 등록한다. Codex SessionStart 및 UPS handler의 `additionalContextLimit`는 잠정 60000이다. 원래 write guard 판정은 유지한다. 확장 등록에서 Read 도구가 원래 write guard의 쓰기로 오인되는 회귀 수리는 parent 담당이었다.
- `sage/commands/doctor.py`: 순수 collector 유효성/최종 렌더 UTF-8 byte 수와 잠정 source 10000/catalog 49152/reentry 2048 budget, Codex handler 한도, source bundle 및 설치 runtime hash 영수증 상태를 분리한다. 필수 이벤트·모든 도구 matcher·handler 타입/timeout/한도를 검사한다. host 지원/신뢰/native acceptance는 항상 UNVERIFIED로 표시한다. 오류는 code/path만 내보내며 개인 본문/exception 원문은 표시하지 않는다.
- `scripts/sage_harness/hooks/generated_artifact_write_guard_core.py`: Fast 세 대상의 overlay 복구 경로 안내를 현재 자격과 정렬했다.
- 기존 `test_overlay_classify`, `test_overlay_materialize`, `test_overlay_reclassification_backing`, `test_overlay_local`, `test_install`, `test_generate`, `test_doctor`를 수정했다. 기존 BACKING 메타테스트는 유지하고 oracle callable 확인을 추가했다.

## RED → GREEN 관측

모든 명령은 `/Users/sejon/project/sage_project_worktree/overlay-context-delivery`에서 실행했다. 아래 `PY`는 `/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`이다. 승인 gate 명령을 실행하지 않았다. install/generate의 실행은 unittest 내부의 격리 temporary consumer fixture에 한정했다. 제품 전체 재생성은 하지 않았다.

| 최초 실패 명령 | 실제 RED | 수정 후 GREEN |
|---|---|---|
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_classify.py -q` | 17 tests: 새 policy 없음 1 ERROR; 동시 CORE 편집 중 spec 계약 1 FAIL | overlay 묶음 최종 GREEN |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_reclassification_backing.py -q` | 16 tests: Fast 세 자격 blocked로 3 FAIL | 동일 16 tests GREEN |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_materialize.py -q` | 33 tests: 외부 소유 span 수용 1 FAIL, root 2종의 trailing bytes 변경 2 FAIL | 동일 33 tests GREEN |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_generate.py -k OverlayNative -q` | 1 test, 양 host matcher 불일치 2 subtest FAIL | 전체 generate 58 tests GREEN |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -k OverlayDelivery -q` | 새 doctor API 없음 2 ERROR | 전체 doctor 41 tests GREEN |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_install.py -k OverlayContext -q` | force 외부 span overwrite 1 FAIL, 경로 안내 API 없음 1 ERROR | 동일 2 tests GREEN, 전체 install 묶음 GREEN |

doctor 최초 회귀에서 제 신규 fixture의 개인 경로를 `local_overrides`로 잘못 작성하여 검사가 부재를 반환한 1 FAIL도 있었다. 실제 정본 경로 `asset_overrides.local`로 고친 뒤 개인 크기 초과가 INVALID이며 본문이 출력되지 않음을 확인했다. 설치 상속 안내도 같은 실제 경로로 정렬했다.

## 최종 소유 영역 개발 회귀

| 실제 명령 | 결과 | 원자료 |
|---|---|---|
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_overlay_*.py' -q` | rc 0, 156 tests, OK | 도구 실행 출력; collector의 동시 추가 test 포함 |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_generate.py -q` | rc 0, 58 tests, OK | 도구 실행 출력 |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_doctor.py -q` | rc 0, 41 tests, OK | `/Users/sejon/project/sage_project_worktree/overlay-context-evidence/overlay-doctor-policy-test.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_install*.py' -q` | rc 0, 170 tests, OK | `/Users/sejon/project/sage_project_worktree/overlay-context-evidence/overlay-install-policy-test.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_fast*.py' -q` | rc 0, 85 tests, OK | `/Users/sejon/project/sage_project_worktree/overlay-context-evidence/overlay-fast-policy-test.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_pre_implementation_gate.py -q` | rc 0, 142 tests, OK | `/Users/sejon/project/sage_project_worktree/overlay-context-evidence/overlay-preimpl-policy-test.log` |
| `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_generated_artifact_write_guard.py -q` | rc 0, 13 tests, OK | `/Users/sejon/project/sage_project_worktree/overlay-context-evidence/overlay-guard-policy-test.log` |
| `git diff --check --` 후 소유 제품/테스트 13경로 | rc 0, 출력 없음 | 도구 실행 출력 |

Fast BACKING 새 세 테스트는 shared-standard/shared-Fast/personal-standard/personal-Fast 각 출처가 유도하려는 악성 상태를 동일 독립 oracle에 넣는다. phase 생략, profile opt-in 해제, round/lens 하한, actual risk 불일치, 감사 chain/seq 손상, stem 불일치, fresh composite 부재, 승인 없는 fake report, 다른 review run 재사용, 필수 acceptance row 누락을 거부했다. 본문을 읽지 않는 구조 oracle 검사다. 실제 모델이 네 출처 지침을 적용하는지, 요청하지 않은 Fast를 고르는지의 행동 시험은 아니다. 진위가 위조된 완전한 evidence 내용까지 재실행 검증한다고 주장하지 않는다.

## 미실행 및 잔여 조건

- 전체 suite의 최종 통합 실행은 parent 담당이다. 동시 변경 중의 최초 전체 회귀를 이 기록의 PASS로 세지 않는다.
- 잠정 budget와 handler 설정은 제품 구성 지원이다. native 실제 전달/잘림/spill/자동 압축/두 사본 문맥 비용을 검증한 결과가 아니다.
- 두 host native 신뢰/지원 버전, 실제 모델 target 선택·자동 Fast 오적용, compact/resume/fork, 역할 packet, clean wheel 및 upgrade/rollback 전체 acceptance는 후속 범위다.
- 04~06, SAGE 엔진 자신의 승인 gate/review-loop, commit/push/배포를 수행하지 않았다. A1~A8을 완료로 표시하지 않는다.

## 통합 후 root source 중복 읽기 보완

parent의 SessionStart 통합 검사에서 collector와 L1 materialization preflight가 root 7종 shared 본문을 중복 읽는 경로가 확인되었다. collector 성공 후 동일 root/event에만 `context_validated=True`를 넘기는 경계를 사용한다. `materialize`, `plan_materialize`, `preflight_overlays`에 기본값 False인 keyword-only 선택 인자를 전파했다. True이면 root context source의 본문 read/검증만 생략한다. inventory·경로·파일명·CORE roster·자격 검사는 유지하고 physical worker의 기존 검사는 유지한다. install/sync 등 나머지 호출은 기본값 False이므로 독립 검증을 생략하지 않는다. `_materialized_render`는 context source를 본래 읽지 않으므로 추가 flag를 넣지 않았다.

- RED 실제 명령: `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_materialize.py -k ValidatedContext -q` → rc 1, 4 tests, keyword API 부재로 5 subtest ERROR.
- GREEN 실제 명령: `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_materialize.py -q` → rc 0, 37 tests, OK.
- 새 검사는 동일 event collector 성공 후 root source 추가 read 0회, worker 물리 본문 유지, 파일명/unknown/symlink fail-closed, 기본 CLI 경로의 악성 root 본문 거부를 확인했다.
- 이 변경으로 보장하는 것은 root context source의 중복 본문 읽기 제거다. worker의 기존 physical composition 검사는 별도 경로로 남으므로 전체 inventory의 모든 자산을 절대 1회 읽는다고 주장하지 않는다.
- collector 이후 디스크 source가 바뀌어도 L1은 새 root 본문을 읽거나 물리 적용하지 않고 해당 event의 검증된 catalog snapshot을 사용한다. 다음 event에서 다시 수집한다. native runtime 연결 및 통합 재실행 결과는 parent 기록이 소유한다.

보완 직후 병렬 runtime 수정 중 `$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_overlay_*.py' -q`도 실행했다. rc 1, 164 tests 중 parent 신규 `test_session_start_reads_each_root_source_once_for_validation_hash_and_body`만 1 FAIL(`len(reads)=0`, 기대 1)이었다. 이 실행을 전체 GREEN으로 세지 않는다. parent에게 즉시 전달했으며 runtime 연결 후 재검사는 parent 담당이다.
