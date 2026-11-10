# Overlay catalog collector — 03 개발 증거

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Status: IMPLEMENTED — 결정적 개발 검증 기록, 04~06/native acceptance 미실행

작업 branch는 `fix/overlay-context-delivery`, 작업 위치는 `/Users/sejon/project/sage_project_worktree/overlay-context-delivery`다. collector 소유 파일은 `sage/overlay_delivery.py`, `scripts/sage_harness/hooks/tests/test_overlay_delivery.py`, 이 기록의 세 파일이다. 다른 담당의 동시 변경을 보존했다. 커밋·푸시·SAGE gate에 의한 자기 승인 없이 03 범위만 수행했다.

## 구현

`collect_catalog(root: str, role: str="root") -> dict`, `render_catalog(catalog: dict) -> str`, 본문 없는 `OverlayDeliveryError(code, path="")`를 제공한다. schema 2의 canonical root/role/generation/sources/targets를 만든다. 공유·개인 `agents/skills/framework` 전체 Markdown inventory를 기존 `overlay_local._read`로 검증하고 root 일곱 skill만 본문으로 공급한다. 기존 `_check_path`, `overlay_filename_error`, CORE roster, `classify`, LF 읽기·예약 토큰 검사·완화 lint를 재사용했다. 승인된 Fast 정책표 `ROOT_CONTEXT_TARGET_SOURCES`와 `delivery_mode`를 소비하며 Fast는 shared-standard → shared-Fast → personal-standard → personal-Fast 순서다. blocked Fast target에 표준 본문만 상속하는 우회도 거부한다.

profile은 기존 `load_profile`로 한 번 읽어 YAML compile/JSON 일치 계약을 유지한다. 같은 profile 객체를 `expected_routing_block`에 전달하여 재로딩 없이 null·domain·routing 입력 계약을 검사한다. framework overlay는 기존 자격상 blocked이므로 domain_refs가 포함된 framework 파일 역시 공급 전에 거부된다. `preflight_overlays`/`scan_domain_contract`를 다시 호출하여 overlay 본문을 두 번 읽지 않는다. manifest가 있으면 UTF-8 JSON mapping인지 검사하며 손상을 정상 부재로 처리하지 않는다. event root 탐색·비SAGE pass-through·native 오류 변환은 parent runtime 소유다.

한 snapshot에서 읽은 LF 문자열을 그대로 lint/hash/content에 사용한다. 파일/디렉터리의 device/inode/mode/size/mtime_ns/ctime_ns와 디렉터리 목록, profile/manifest metadata를 수집 전후 비교한다. 변경 시 전체 수집을 한 번만 다시 시작하고 계속 바뀌면 `overlay_delivery.unstable_snapshot`이다. source가 없거나 공백뿐이면 제외하고 sources/targets가 모두 빈 catalog를 명시적으로 반환한다. 비root/미지 역할은 inventory 검증과 source 입력 한도 검사를 유지하며 root 본문을 공급하지 않는다. 영구 cache나 원본/렌더 쓰기를 하지 않는다.

source 최대 UTF-8 10,000 bytes, wrapper와 JSON escape를 포함한 `render_catalog` 최대 UTF-8 49,152 bytes는 **03 개발용 잠정 제품 값**이다. 공개 상수는 `MAX_SOURCE_UTF8_BYTES`, `MAX_CATALOG_UTF8_BYTES`다. `collect_catalog`도 최종 render 크기를 검사하므로 초과 catalog를 정상 반환하지 않는다. UTF-8 byte 수를 보수적 token upper bound로 사용할 수 있지만 tokenizer 실측치나 token 추정치라고 부르지 않는다. host의 추가 JSON escape, reentry, 두 handler 사본, 누적 대화 비용은 이 함수 바깥의 별도 합산/후속 실측 항목이다.

render는 `SAGE_OVERLAY_CATALOG_V2` 시작줄, root/role·자기 target·공유 우선·CORE/gate 유지·자동 Fast/호출/승인 아님 계약, compact sorted JSON, `END_SAGE_OVERLAY_CATALOG_V2` 끝줄을 포함한다. 본문이 초과하면 자르거나 preview로 바꾸지 않고 오류를 반환한다. 개인 본문·읽기 예외 내용을 오류 문자열에 넣지 않는다.

## 실제 실행

모든 Python 개발 검증은 다음 interpreter를 사용했다.

```text
/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python
```

새 fixture는 `SAGE_TEST_TMPDIR` 환경변수로 지정 가능하며 기본 위치는 공통 worktree parent 아래 `.sage-fixtures`다. 테스트 임시 디렉터리는 정상 cleanup한다.

| 단계 | 실제 명령 | 결과 |
|---|---|---|
| 최초 RED | 위 Python `scripts/sage_harness/hooks/tests/test_overlay_delivery.py` | rc 1; 20 tests, 20 failures. `sage.overlay_delivery` 미구현을 assertion으로 확인 |
| 최초 GREEN | 같은 명령 | rc 0; 20 tests, 0.064s, OK |
| 경계 추가 RED | 같은 명령 | rc 1; 24 tests, 1 failure. `test_nonroot_still_enforces_root_source_input_limit`: 비root 경로의 10,001-byte 입력이 오류 없이 통과 |
| 경계 수정 GREEN | 같은 명령 | rc 0; 24 tests, 0.074s, OK |
| 관련 회귀 R1 | 위 Python `-m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_overlay*.py'` | rc 1; 155 tests, 154 pass/1 failure, 0.413s. 기존 `test_overlay_local.LocalOverlayTests.test_all_currently_eligible_targets_and_no_new_eligibility`의 `len(COMPOSE_ALLOWED)==8`이 Fast 3종 추가 후 실제 11과 불일치. 정책 담당에게 전달; collector 범위 밖 파일은 수정하지 않음 |
| 관련 회귀 R2 | 위 Python `-m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_overlay*.py'` | rc 0; 155 tests, 0.415s, OK. 정책 담당의 기존 자격 수 기대 정렬 후 재실행 |
| 최종 collector 재확인 | 위 Python `scripts/sage_harness/hooks/tests/test_overlay_delivery.py` | rc 0; 24 tests, 0.069s, OK |
| diff whitespace | `git diff --check` | rc 0, 출력 없음 |

24개 collector 검사는 최대 14 source/7 target, 정확한 Fast 상속과 역상속 없음, empty/whitespace/삭제 상태, 원본 불변·단일 LF 읽기·hash 일치, agent 검증/본문 제외, 공유/개인 unknown/blocked/case/완화/예약 토큰 오류, symlink/디렉터리 위장/UTF-8 오류, profile 손상·routing null·YAML/JSON 불일치·manifest 손상, root 분리·역할 억제, blocked Fast 상속, content/inventory/profile 변화·1 retry·계속 변화 오류, UTF-8 byte 경계·JSON escape 총량, render JSON 복원·결정성, 예상 밖 예외의 본문 비노출, 외부 수리 후 재검사를 다룬다.

## 한계와 후속 범위

전체 suite는 parent가 통합 후 수행한다. collector 개발 검증은 설치·실제 host 전달·native 차단·실제 모델의 target scope·compact/resume/fork·spill/최대 문맥 비용·clean wheel consumer의 수용 증거가 아니다. stat/list 전후 비교는 관측 가능한 변경을 탐지하는 방식이며 OS 전체의 atomic snapshot 또는 악의적인 동시 변경의 부재를 보장하지 않는다. 후속 04/A1~A8, 독립 L3 05, 06 종료와 출시 승인은 모두 열려 있다.

## 2026-11-06 R1 F02 최소 재작업

두 refuter가 유지한 F02의 재현 JSON(`overlay-context-phase05-restart-20261106/repro-CONC01.json`)과 실제 스크립트 `reproduce_conc01.py`를 확인했다. stat 이후 listdir 직전에 디렉터리를 rename하면 최초/최종 `_snapshot`의 획득 예외가 최상위 `validation_failed`로 곧바로 변환되어 기존 한 번 재시도 계약을 지키지 못했다. 새 API·scanner·영구 상태 없이 `collect_catalog`의 기존 두 attempt 안에서 두 snapshot 획득을 감싸고, 획득 중 `FileNotFoundError`/`NotADirectoryError`만 한 번 재시도하도록 최소 수정했다. 두 번째 획득 불안정은 `overlay_delivery.unstable_snapshot`으로 끝난다. `_collect`의 정상 검증 오류는 기존대로 따로 보존하여 이 재시도 catch에 들어가지 않는다. `PermissionError`와 안정된 lint 오류의 기존 오류 코드·본문 비노출은 유지한다.

먼저 새 테스트 5개 method를 추가했다. 실제 파일시스템 rename을 listdir 경계에서 실행하여 첫/최종 snapshot 각각의 disappearance/replacement를 재현한다. 지속 race는 두 attempt의 정확히 두 획득 실패에서 종료하는지 검사한다. 첫/최종 snapshot의 PermissionError는 각 한 번만 실패하며 부분 catalog를 반환하지 않고, 안정된 완화 lint 오류도 한 번만 읽고 실패하는지 검사한다. PermissionError는 실행 계정의 파일 권한과 무관하게 경계 예외를 주입하며, rename/disappearance/replacement는 실제 디렉터리와 파일 연산을 사용했다. 전체 suite나 실제 host/native/model acceptance를 이 재작업으로 대신하지 않는다.

검증 cwd는 `/Users/sejon/project/sage_project_worktree/overlay-context-delivery`이며 아래 모든 명령의 `TMPDIR`와 `SAGE_TEST_TMPDIR`는 B2 아래로 지정했다. 테스트 fixture는 해당 부모 아래 `TemporaryDirectory`를 만들고 cleanup했다.

RED와 GREEN은 생산 코드 수정 전/후 각각 같은 명령으로 실행했다.

```sh
TMPDIR=/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106 SAGE_TEST_TMPDIR=/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106 /Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python scripts/sage_harness/hooks/tests/test_overlay_delivery.py
```

| 실행 | rc | 실제 결과 | 보존 로그 |
|---|---|---|---|
| F02 RED | 1 | 33 tests, 0.085s; 8 subtest failures, 0 errors. transient 네 경우가 즉시 `validation_failed`, persistent 네 경우가 기대 `unstable_snapshot`과 불일치. permission/안정 lint 회귀는 이때도 통과 | `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106/f02-collector-red.log` |
| F02 GREEN | 0 | 33 tests, 0.100s, OK | `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106/f02-collector-green.log` |

관련 overlay 회귀 명령은 다음과 같다.

```sh
TMPDIR=/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106 SAGE_TEST_TMPDIR=/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106 /Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python -m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_overlay*.py'
```

결과는 rc 1, 194 tests, 0.664s, 2 subtest failures다. 모두 동시 작업 중인 F01의 `test_overlay_materialize.TestContextRoutingConvergence.test_routing_cleanup_preserves_trailing_user_bytes_in_both_plans`에서 host `claude`/`codex`가 trailing LF 두 개를 보존하지 못한 실패다. 이 담당은 소유 밖 파일을 수정하지 않고 parent에게 전달했다. 로그는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106/f02-overlay-regression.log`다. 소유 세 파일에 대한 `git diff --check -- sage/overlay_delivery.py scripts/sage_harness/hooks/tests/test_overlay_delivery.py docs/plan_docs/03/collector-evidence.md`는 rc 0이었다.

이 기록 작성 후 소유 세 파일을 freeze하여 추가 수정하지 않는다. 커밋·푸시·모델 호출·SAGE 자기 승인 명령을 실행하지 않았다. F02 개발 검증 결과이며 통합 리뷰 수렴·다른 finding 처분·출시 승인 결과로 주장하지 않는다.
