# Overlay 전달 런타임 — 03 개발 근거

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: IMPLEMENTED_WITH_OPEN_CHECK — 최종 R3 및 scoped 재검사 기록 완료

## 구현한 경계
- runtime/overlay_context.py: lazy collector import, 진짜 비SAGE pass-through와 손상 marker 구분, root/명시 role/자식 신규 공급 억제, 본문 없는 오류, 기존 risk/reentry와 catalog 출력 합성.
- runtime/hook_runtime.py: UPS 자동 재검사·단일 JSON, startup defer, resume/fork/compact 새 공급, L1 실패 뒤에도 baseline/reentry 시도, 지원 도구 검증.
- runtime/run_hook.py: 기존 write guard 전에 inventory 검사. 확대 등록에서 Read/Bash를 쓰기 판정으로 오인하지 않고 실제 editing tool 또는 direct path만 원래 판정.
- runtime/io_claude.py,io_codex.py: 공통 모양의 이벤트 context 봉투, UPS native block/PreToolUse exit2 채널.
- sage/hook_entry.py: event cwd를 inherited 시작 root보다 우선, git 경계에서 상승 중지, capture-declared-risk fail-closed.
- sage/commands/review.py: 독립 headless launcher에 SAGE_OVERLAY_ROLE=reviewer 명시. reviewer CLI의 기존 1회 overlay 로딩 유지.
- tests/run-all.sh: 새 collector/runtime 개발 테스트를 공식 runner에 연결.

## 테스트 관측
Python: `/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`.
작업 위치: `/Users/sejon/project/sage_project_worktree/overlay-context-delivery`.

- runtime 테스트 최초14개 RED: 자동 전달/재개 공급/잘못된 inventory 차단 누락 등을 재현. `overlay-context-evidence/runtime-red.log`.
- 연결 후14개 GREEN: `runtime-green-attempt.log`.
- Read SKILL.md 허용 회귀1개를 추가하자15개 중1FAIL. `runtime-read-red.log`. 확대 matcher가 Read도 기존 guard에 넘기던 것이 원인. 쓰기 도구만 원래 guard로 보내도록 수정 후15GREEN.
- 잘못된 공유 L1/손상 marker/validator 예외 비노출 검사를 더해18GREEN.
- 기존 hook_entry39개 GREEN: `entry-tests.log`.

## 전체 회귀 시도 구분
처음 unittest discover 전체를 비동기로 실행한 뒤 소유 영역 구현을 병행했다. 이 실행은 immutable baseline이 아니다. 3990 tests/25 failures/1 error/14 skips를 보고했으나 설치 source mutation 탐지와 단일 프로세스 module 상태 영향 등이 섞여 최종 근거로 채택하지 않는다. 원자료 `/Users/sejon/project/sage_project_worktree/overlay-context-baseline.log`를 보존한다. 변경 전 기준선은 별도로 실제 완료한 overlay111개 GREEN뿐이다.

모든 제품 소유자가 freeze한 뒤 공식 `tests/run-all.sh`를 별도 실행했다. 개별 파일을 별도 Python process에서 실행하는 repository runner가 최종 개발 회귀의 기준이다. 결과와 수정 내역은 03 본 기록에 추가한다.

## 승인·한계
이 테스트는 합성 파일/이벤트 fixture를 소비하는 제품 코드의 개발 검증이다. 실제 Claude/Codex 세션의 전달·자동 압축·모델 행동·부모 fork 이력 제거·hook 미실행/timeout 시 강제 차단을 증명하지 않는다. 04~06 및 배포/전역 설치/커밋/푸시는 실행하지 않았다.

## 통합 중 추가 수정과 실패 근거

- root7의 공유 원문은 SessionStart L1 preflight와 collector에서 2회 읽히고 있었다. `root-read-once-red.log`에서 19개 중1FAIL(2 != 1)을 확인했다. collector가 동일 event/root 전체 inventory 검증에 성공한 때에만 `context_validated=True`를 L1으로 넘겨 해당 root7의 추가 본문 읽기를 생략한다. 경로/roster/파일명과 worker 물리 합성 검사는 유지한다. worker의 기존 물리 합성 검사는 추가로 본문을 읽을 수 있으므로 모든 자산에 절대1read라고 주장하지 않는다. runtime19 및 materialize37 GREEN을 확인했다.
- 새 설치본이 `sage.overlay_delivery`라는 필수 package 모듈을 호출하므로 runtime API가2여야 한다. 실제 installer manifest를 API1로 시뮬레이션한 실행기가 거부해야 한다는 테스트를 추가했더니 rc1/1FAIL이었다(`runtime-api-red.log`). API2로 올린 후 runtime API19 GREEN. API1 설치를 API2 package가 계속 읽는 기존 호환성은 유지한다.
- 기존 L1 테스트는 root 스킬 파일의 물리 공유 body를 기대했다. 새 계약은 render에 없고 catalog source에 있는 것이다. render 비노출과 실제 catalog body를 함께 검사하도록 바꾸고 hook_runtime150 GREEN.
- validate safety 테스트는 엔진의 역사적 manifest 해시에 의존해 smoke 앞에서 STALE이 됐다. 엔진 manifest를 재생성하지 않고 격리 consumer와 실제 사본 hash를 사용하는 fixture로 바꿨다. validate safety51 GREEN(1 환경 skip).
- locality metadata의 코드 위치가 바뀌어 localization inventory check가 실패했다. 전용 Python generator로 해당 inventory만 갱신했다. framework/manifest 전체 생성이나 엔진 자기 승인은 수행하지 않았다.
- 새 runtime/overlay_context.py가 hook_runtime_hash 추적 목록에서 누락돼 변조 뒤에도 PASS였다. 신규 변조/삭제 테스트가 RED(`runtime-helper-hash-red.log`)를 확인했고 asset_paths의 공유 runtime roster에 추가했다. 관련 mock consumer fixture4곳을 정렬했다. 실제 원본/설치본 무결성 판정에 해당 모듈의 변경/삭제가 반영된다.
- .git 파일/디렉터리 경계 외 bare repo에서는 부모 checkout까지 올라가는 반례가 있었다(`root-bare-red.log`). 기존 doctor의 repo 경계 판정을 재사용해 bare 경계에서도 상승을 중지한다. 이 수정은 일반/linked worktree 기존 의미를 유지한다.
- 마지막 두 보완 후 runtime20 / asset_paths9 / validate safety52(1skip)의 개발 검증을 확인했고 전체 공식 runner R3를 시작했다. source snapshot 시작 hash는 `sha256:a28e77ee9c85b1e27eb0dbe70db36f1d07946aa9f824b13f9c03538fd98721bd`다.

R1/R2 로그는 실패와 새 반례 검출 이력으로 보존한다. R2가 진행되는 동안 테스트 파일에 hash/bare repo 반례를 추가했으므로 R2의 테스트 subject 목록은 immutable하지 않았다. 최종 R3는 코드와 테스트를 모두 freeze한 뒤 실행하며, R3가 최종 개발 검증 근거다. 전체 회귀 라운드는 Phase05 리뷰 라운드가 아니다.

## 최종 R3와 후속 사전검사

R3는4050 검사 실행/14skip/ERROR0/6실패 assertion, exit1이었다. 신규 collector24/runtime20은 통과했다. 실패 중5건은 API2에서 새로 집행하는 UPS의 구 baseline 기대값이며, 기대값을 정상 native 차단 계약으로 정렬한 뒤 test_runtime_api_preflight.py36개를 다시 실행해 GREEN을 확인했다. 제품 코드는 바뀌지 않았다. 남은 자가 manifest 검사1건은 OPEN으로 보존하고 03 본 기록에 설명했다. 전체 runner를 마지막 테스트 기대값 수정 뒤 다시 실행하지 않았으며 전체 PASS로 보고하지 않는다. 원자료는 overlay-context-evidence/final-test-summary.json과 full-run-r3.log다.
