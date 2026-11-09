# Phase04 CI consumer 검증 재작업

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Status: IMPLEMENTED_SCOPED_VERIFIED — 최종 freeze candidate 검증은 parent 담당

## 접근과 승인 경계

기존 `TestTheEngineIsNotStaleAgainstItself.test_self_validate_is_clean`은 엔진 checkout의 역사적 manifest와 변경 중인 소스를 비교해 실패했다. manifest 재스탬프·검사 삭제·skip·면제로 통과시키지 않는다. 엔진 root에는 consumer profile이나 cycle을 만들지 않는다.

일반 Python 회귀와 기존 독립 sdist resource guard는 유지한다. 새 표준 라이브러리 CI helper로 복사된 소스의 wheel을 만들고, clean venv와 fresh consumer에서 install → bootstrap 전 거부 확인 → fixture profile bootstrap → generate → validate 및 실제 consumer runtime 변조 거부를 제품 테스트한다. import와 resource 위치는 설치 wheel로 한정하며 원본 엔진의 manifest/profile/안내문/.sage sentinel은 실행 전후 동일해야 한다. 같은 helper를 로컬 회귀와 CI에서 사용한다.

이 기록은 엔진 승인·독립 reviewer 판정·원격 CI 실행·릴리스 근거를 대신하지 않는다.

## 구현 범위

- `.github/workflows/ci.yml`: root `python -m sage validate --check --schema` 대신 `python -I scripts/ci/check_consumer_integrity.py --work-dir "${{ runner.temp }}/sage-consumer-integrity"`를 실행한다. 기존 hook 회귀, sdist build/resource guard, packaging/platform/uninstall/release evidence job은 유지했다.
- `scripts/ci/check_consumer_integrity.py`: stdlib driver다. 원본 checkout 밖의 비어 있는 scratch만 허용한다. 소스를 복사해 build하므로 원본에 `build/`, `dist/`, egg-info를 만들지 않는다. private HOME/XDG/APPDATA/TMP, Python isolated mode, SAGE/Python/Pip/host override 제거, fresh venv/no-index 설치, 실제 import와 `_bundle` 경로 확인으로 source fallback을 배제한다.
- 제품 호출 전에 stdlib zip/csv/hash 검사로 wheel 필수 bundle 리소스, 중복 path, RECORD 전체 coverage 및 각 바이트 hash/size를 검사한다. 이는 SAGE gate나 manifest 판정을 호출하지 않는 package integrity 검사다.
- fresh consumer만 install/bootstrap/generate/validate한다. bootstrap 전 generate는 정확히 exit2, 정상 generate 후 validate는 exit0, 설치된 `runtime/overlay_context.py`의 실제 변조 후 validate는 exit3이어야 한다. subprocess 실패는 driver 실패로 전파된다.
- 원본 엔진의 안내문, profile YAML/JSON, 역사적 manifest, `.sage`, `.claude`, `.codex` sentinel을 전후 비교한다. 부재 파일 생성도 변경으로 잡는다. finally에서 차이가 나면 report와 driver가 실패한다. 개인/전역 사용자 설치는 실행하지 않는다.
- 각 subprocess 명령/cwd/실제 rc/기대 rc와 stdout/stderr를 scratch에 남긴다. `source-snapshot.json`의 파일별 hash와 집계 hash, wheel SHA256을 report에 기록해 복사된 시험 subject를 식별한다. report의 PASS는 이 제품 시험의 결과이며 엔진 자체 승인 의미가 아니다.
- `test_release_readiness.py`의 기존 self-staleness 한 항목을 consumer 제품 동작과 격리/실패전파/package integrity의 여섯 항목으로 바꾸었다. runner 등록은 기존 파일을 그대로 사용한다.

## RED → GREEN 및 scoped 검증

Python: `/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`.

1. helper 구현 전 `python -m unittest scripts.sage_harness.hooks.tests.test_release_readiness.TestConsumerIntegrity`를 실행했다. 3 tests, failures3, exit1. missing helper의 CLI exit2와 명시적인 `isolated consumer helper is not implemented` assertion이 RED 원인이다. 새 검증 경로 부재를 먼저 확인했다.
2. helper/CI 구현 후 같은 명령은 3 tests, OK, exit0, 10.392s였다. 실제 wheel build/install, bootstrap 거부2, 정상 validate0, 실제 runtime drift 거부3, engine sentinel 불변을 확인했다. `PYTHONPATH`에 import시 예외를 내는 `sage.py`, 가짜 `SAGE_RESOURCE_ROOT`, 원본을 가리키는 `SAGE_PROJECT_ROOT`를 넣은 상태에서 통과했다.
3. 후속 `TestConsumerIntegrity.test_work_inside_engine_is_rejected_before_writing`, `.test_engine_sentinels_detect_created_profile_and_changed_manifest`, `.test_independent_bundle_check_rejects_record_tampering` 세 항목을 `python -m unittest`로 실행했다. 3 tests, OK, exit0, 0.006s. engine 내부 scratch 거부/무생성, manifest 변조·profile 생성 감지, wheel RECORD 변조 거부를 확인했다.
4. readiness module의 61개 중 fresh wheel 전체 경로 1개를 명시적으로 선택하지 않고 나머지 60개를 실행했다. 60 tests, failures0/errors0/skipped0, exit0. parent가 A5 제품 runtime 수리 중임을 알렸고 최종 freeze 후 전체 candidate를 재실행하기로 분담했기 때문이다. 이 선택 제외를 skip 또는 전체 module PASS로 세지 않는다. [상세 로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-ci/readiness-scoped.log), [선택·집계](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-ci/readiness-scoped-summary.json).
5. `git diff --check` exit0. 변경 helper와 readiness test의 `ast.parse` 통과. `python -I scripts/ci/check_consumer_integrity.py --help` exit0.

첫 3개 GREEN의 wheel은 병행 A5 runtime 재작업 전 후보이며 이후 제품 소스가 바뀔 수 있다. 시험용 TemporaryDirectory는 정상 종료 때 제거되어 해당 첫 후보의 wheel/hash 원자료는 보존하지 않았다. 따라서 이 관측을 최종 후보의 package acceptance로 승격하지 않는다. 후속 source snapshot 기록 추가 후 전체 helper는 아직 다시 실행하지 않았다. 최종 freeze source에서 parent가 재실행한 report/wheel/source hash가 최종 후보 근거다.

## 남은 실행과 경계

공식 `run-all.sh`와 최종 frozen candidate helper 재실행은 parent가 통합 변경을 고정한 뒤 수행한다. 이 담당자는 중복 실행하지 않았다. 실제 GitHub Actions CI, 다른 OS/Python matrix, 독립 Claude Phase05 review는 이 기록에서 실행·승인하지 않았다. historical engine manifest 재생성, engine profile bootstrap, 검사 skip/waiver, commit/push/release/global install도 수행하지 않았다. A1~A8 전체 수용 또는 source canonical reviewer verdict를 부여하지 않는다.

## 최종 frozen candidate 재실행

parent가 통합 소스 freeze 뒤 공식 runner R5와 별도 helper를 실행했다. runner exit0, Python 검사 실행4,066건(반복 포함)/skip14/실패0/ERROR0이다. 별도 helper도 exit0이며 원자료는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase04-final-consumer-r5/report.json`이다. wheel SHA256 `6cd508988e48635284c70ac2e90407aa2698d0842eef640b1f4b84bb001cde40`, source snapshot digest `709b1e07b4a0929f196f4a6b395dfa3ed508f8c0caee42055a6c7f77cc7936f9`;8개 subprocess 단계가 각각 기대 rc와 일치했고 engine sentinel 불변이다. 초기 삭제된 후보의 관측과 구분해 이 최종 후보/wheel/log를 보존한다. 제품 source 시작/종료 맵은 동일하다. 이후 phase 분석 문서만 갱신했다. 원격 CI/다른 OS 실행/05 독립 리뷰는 여전히 미실행이다.
