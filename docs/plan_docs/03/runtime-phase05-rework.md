# Phase05 재개 — runtime 재현과 최소 수리

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Status: IMPLEMENTED_SCOPED_VERIFIED — 독립 재검토/최종 통합 판정은 parent 담당

## 범위와 시험 subject

사용자가 2026-11-06 Phase05~06 재개를 승인했다. 이 담당자는 runtime 재현과 최소 수리만 맡았고
SAGE gate/review-loop로 엔진을 승인하지 않았다. 작업 위치는 기존
`/Users/sejon/project/sage_project_worktree/overlay-context-delivery`, branch `fix/overlay-context-delivery`다.
commit/push/release/global install이나 실제 계정 모델 호출은 수행하지 않았다.

원자료 B는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/`다.
제품을 수정하기 전 source 전체를 B/source-red에 복사했다. `source-red-hashes.json`은 복사본의
파일별 SHA256이며 native/혼합상태 재현은 이 고정 소스의 package를 사용했다.
실행 스크립트/원자료 hash는 [evidence-hashes.json](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/evidence-hashes.json)에 있다.
`red`는 수정 전 snapshot 이름이며 아래 R1-01이 실패했다는 뜻이 아니다.

모든 install/generate/hook subprocess의 cwd는 격리 consumer다. install은 지원 인자인
`--dest <consumer>`를 명시했고, generate는 `--root <consumer> --dest <consumer>`를 함께 명시했다.
hook entry는 `--root <consumer>`를 명시했다. 엔진 root에 profile/manifest를 생성하지 않았다.

## R1-01 — 현재 Claude native에서는 stdout 유실이 재현되지 않음

리뷰 원문의 “SessionStart exit2이면 stdout을 무조건 버려 compact reentry가 사라진다”를 실제
Claude Code `2.1.318`로 시험했다. 실제 모델 대신 localhost mock Anthropic endpoint를 사용했다.
`ANTHROPIC_BASE_URL`은 이 endpoint로 고정했고 API key는 synthetic 값이다. 실행된 네 요청은 모두
로컬 server의 `/v1/messages?beta=true`에서 기록됐다. 이는 모델 행동/의미 준수 시험이 아니다.

명령: 위 Python으로 `B/native_compact.py native-r1-01-red source-red`를 실행했다.
script는 fresh consumer 설치/생성 후 native CLI를 순서대로 실행했다.

1. `claude -p ... 'Reply PROBE_NATIVE_DONE.'` — warmup, rc0.
2. 같은 session의 `claude -p --resume <sid> ... '/compact ...'` — 실제 수동 compact, rc0.
3. 같은 session에서 다음 prompt — rc0.

wrapper는 실제 host가 보낸 `SessionStart source=compact` 직전에 오타 shared overlay 하나를
시험 consumer에 만들고 product hook을 실행했다. hook이 반환한 뒤 이 시험 입력을 외부에서
제거해 다음 UPS가 진행할 수 있게 했다. event source를 가짜로 바꾼 시험이 아니다.

- compact hook 실제 rc2, stdout에 reentry 존재, catalog 없음.
- 고유 `RUNTIME_REENTRY_SENTINEL_01`은 warmup/요약 요청에 없고, 다음 모델 요청에 2회 나타났다
  (cycle 표시와 ledger 명령의 같은 stem).
- 다음 실제 request에는 `SessionStart hook additional context:` 뒤에 reentry 본문이 있었다.
  현재 source의 resume 경로는 compact reentry를 만들지 않으므로 새 resume가 만든 본문과 구별된다.
- [native 원자료](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/native-r1-01-red):
  `hooks.jsonl`, `requests.json`, `summary.json`, 각 native stdout/stderr.

따라서 이 버전/경로에서는 해당 유실 주장을 입증하지 못했고 반대 관측을 얻었다. parent 지시에
따라 SessionStart exit 정책 및 `io_claude.py`/`io_codex.py`는 바꾸지 않았다. 다른 host/version,
자동 compact 오류, 실제 모델 의미 복구까지 반증했다고 확대하지 않는다. 이 원자료를 fresh peer가
재판단할 대상으로 남기며 이 담당자가 reviewer verdict를 부여하지 않는다.

### R1-01 Codex 추가 경계 — 별도 분기에서는 유실 재현

parent 요청으로 immutable `subject-r1` 제품 hash
`sha256:6450e36ece176d4216f87c51622e173de9409923f90b8e22d9285e970a41e809`를 사용해
Codex CLI `0.166.0`에서도 한 manual compact 실패 경계를 확인했다. 기존 QA consumer는 변경하지
않고 B/native-codex-r101/consumer를 새로 install/generate했다. mock Responses provider는
localhost로 고정했고 `requires_openai_auth=false`, fresh CODEX_HOME, `REAL=False`로 실행했다.
추가 실제 계정 모델 호출은0이며, 요약/응답 내용은 mock이다.

`run_native.py mock-compact-r101-shared`는 app-server의 실제 thread를 열고 정상 turn,
`thread/compact/start`, 다음 turn 순으로 실행했다. recorder는 host가 보낸 실제
`SessionStart source=compact` 직전에 오타 shared source를 만들고 product hook을 호출한 뒤
외부에서 제거했다. hook은 exit2, stdout reentry 있음/catalog 없음이었다. 그런데 localhost에
기록된 다음 `/v1/responses` 요청에는 고유 `CODEX_R101_REENTRY_SENTINEL`이0회였다.
정상/compact/후속 세 요청 모두0회였고, 수리 뒤 catalog는 다음 요청에 정상 공급됐다.

대조를 위해 먼저 보존한 `mock-compact-r101`은 personal 오타 입력이라 SessionStart rc0이었다.
이 경우 다음 요청의 reentry marker는2회였다. 이 첫 사례는 요청한 rc2 실패 경계의 성공 근거로
세지 않고 대조 자료로 보존한다. 동일 host의 rc0/rc2 차이에 따라 전달 여부가 달랐다.
따라서 Claude의 반대 관측을 Codex 분기에 확대할 수 없으며, Codex의 rc2 reentry 유실은 실제로
재현됐다. 이 결과를 제품 수리 전에 parent에게 보고했고 제품/테스트는 아직 변경하지 않았다.

해당 thread `01a1af0a-312e-7183-8768-e307cda9dc60`의 실제06 baseline은
`plan_docs/06-owned-baseline.md`의 SHA256을 포함해 작성됐고, compact 전후 snapshot hash는
`6124602113d523a178e75df1d81960de43278aa639fe40ffd455f6e1b2436de6`로 같았다.
immutable snapshot의 등록 파일 hash도 전후 drift0이다.

[최종 Codex 원자료](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/native-codex-r101/mock-compact-r101-shared)의
`assessment.json`, `requests.json`, hook records, app events와 result를 보존했다.
[증거 hash 목록](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/native-codex-r101/evidence-hashes.json)은
대조 자료와 실행 driver/recorder를 함께 결속한다. 준비 중 optional `pdca.retro` mapping 부재와
phase06만 남긴 fixture의 선행 phase 참조 오류가 있었으며, native 호출 전에 fixture를 정상 전체
phase 구성으로 고쳤다. 이 두 harness 준비 실패는 별도 오류 파일로 보존했고 제품 결함이나
호스트 전달 결과로 세지 않는다. 기존 QA consumer와 immutable source를 수정하지 않았다.

### R1-01 Codex 재현 후 C2 최소 수리 및 양 호스트 재검증

위 Codex 분기 실패를 보고한 뒤 parent가 추가 수리를 승인했다. 현재 `hook_runtime.py`의
SessionStart 부분만 변경했고 parent의 `make_rel` alias fallback은 건드리지 않았다.

- shared L1 오류는 기존처럼 stderr 진단 및 catalog 억제로 처리하지만 overlay-only exit2를
  SessionStart 최종 반환에 합치지 않는다.
- merged context 초과도 catalog를 제외하고 독립 reentry를 남기며 baseline rc를 덮지 않는다.
- 최종 반환은 독립 baseline helper의 기존 rc다. baseline 실패의 nonzero는 유지한다.
- UPS·PreToolUse의 입력 차단은 바꾸지 않았다.

수리 전 32개 runtime suite에서 이 새 반환 계약을 검사하는4개가 RED였다. 수리 후32개가 모두
통과했다. baseline 실패2가 overlay 오류 때문에 숨겨지지 않는 양 host 회귀도 포함한다.
넓은254개 scope에서는 기존 `test_hook_runtime`의 SessionStart malformed-span 검사가 옛rc2를
기대해1건 실패했다. parent 승인에 따라 이름을
`test_malformed_block_is_diagnosed_and_other_target_is_cleaned`로 바꾸고 wrapper rc0 기대를
정렬했다. BLOCK/중복 진단·다른 target 정리 검사는 유지했고 direct L1 helper의 오류2도 유지했다.
이 test-only 차이는 C2 보존 후 C3 후보로 분리한다.
최종 동일254개 scoped 재실행은 failures0/errors0/skipped0/exit0였다.
`runtime-c2-scoped-summary.json`에는 모듈명·검사 수·최종 제품/테스트 SHA가 있다.

수리한 제품 전체를 B/source-native-c2에 복사해 두 host의 새 consumer에서 시험했다.
제품 hash는 `sha256:5f52ff3bac656b4e4b4200ddaf6f6c25d12918c20b48916524df1f497737bb1f`다.
공식 `subject-c2`와 비교했을 때 제품216개 및 전체 등록파일495개 각각 SHA 차이0이었다.
[C2 비교 기록](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/native-codex-r101-green/subject-c2-comparison.json).

| host / mock native 경계 | compact hook | 다음 모델 요청 | 독립 baseline |
|---|---|---|---|
| Codex0.166.0, 이전 C1 | rc2, reentry stdout, catalog 없음 | 고유 reentry marker0 | 전후 동일 |
| Codex0.166.0, 수리 C2 | rc0, reentry stdout, catalog 없음 | 고유 reentry marker2 | 전후 동일 |
| Claude2.1.318, 수리 C2 | rc0, reentry stdout, catalog 없음 | 고유 reentry marker2 | baseline 계약은 unit/별도 Codex 관측과 구분 |

Codex C2 thread는 `01a1af0d-3129-7b10-9ffb-e59237cf78bc`, baseline 전후 hash는
`a197a784f4793e1ab8b3ce9b0a54eba5f5867b97a62e17c19d25350abe466f4b`였다.
warmup→실제 manual compact→다음 turn의 local Responses3요청/3.32s였던 RED와,
같은 흐름의3요청/4.32s GREEN을 각각 보존한다. Claude의 warmup→실제 `/compact`→다음 prompt도
local Anthropic4요청으로 확인했다. 전송·요약이 mock인 native 경계 시험이며 실제 계정 모델의
의미 복구/자동 압축/다른 버전까지 검증한 것은 아니다. 실제 계정 추가 호출은0이다.

[Codex GREEN 원자료](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/native-codex-r101-green/mock-compact-r101-shared),
[Claude GREEN 원자료](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/native-r1-01-green),
[최신 scoped 로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/runtime-c2-scoped.log)를 따른다.
수리 C2의 `hook_runtime.py` SHA는
`f4b0bdd8f20b279dafffe7a79a713e1707a7ce5d6c1b3efbc2d50539bb97ba80`이며 native consumer에
복사한 runtime과 현재 제품 파일이 같다. 이후 제품 source는 변경하지 않았다.

## R1-04 — new package + old installed runtime의 shared 유실 재현

B/source-red의 new package와 git `8e17a88`의 구 project-local hook 전체·구 `sage-team` CORE를
결합한 격리 consumer를 만들었다. 구 manifest 의미에 맞춰 required runtime API는1로 설정했다.
공유 원본과 구 정상 managed span에 같은 synthetic sentinel을 넣었다.

`python -m sage.hook_entry --runtime claude --hook session-start-snapshot --root <consumer>`를
실행한 결과:

| 관측 | 값 |
|---|---|
| entry/hook rc | 0 |
| shared span sentinel | before 있음 → after 없음 |
| 구 CORE에 catalog selector | 없음 |
| 구 runtime의 `overlay_context.py` | 없음 |
| stdout catalog | 없음 |

구 runtime을 선호하는 entry가 API1 requirement를 허용하고, 구 L1에서 new package의
`overlay_materialize.materialize`를 호출해 span을 제거했다. 실제 소비자 안내의 조용한 유실이
재현됐다. [혼합 재현 원자료](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/mixed-old-runtime)의
`commands.json`에는 명령/cwd/rc/stdout/stderr, `result.json`에는 전후 render hash가 있다.
설치·materialization 정책 소스는 이 담당자가 편집하지 않았고 parent에게 수리를 요청했다.

이후 policy 담당이 guard를 추가한 현재 제품 전체를 B/source-green에 새로 고정하고
`source-green-hashes.json`으로 결속했다. 기존 유실 consumer를 재사용하지 않고
`B/mixed_runtime.py source-green mixed-old-runtime-guarded old` 및
`B/mixed_runtime.py source-green new-runtime-guarded new`를 실행해 비교했다.

| 새 consumer | rc | span | 원본 | selector / stdout catalog |
|---|---:|---|---|---|
| 구 runtime+구 CORE | 2 | 전후 동일 hash로 보존 | 보존 | 없음 / 없음, 명시 upgrade 진단 |
| 현재 runtime+현재 CORE | 0 | 정상 legacy span만 제거 | 보존 | 있음 / 있음 |

각 case의 `commands.json`/`result.json`과 consumer를 보존했다. 처음 selector 계측이 대문자
`SAGE_OVERLAY_CATALOG` 문자열만 찾아 정상 새 CORE도 false로 표시한 harness 오류가 있었다.
실제 보존된 render의 fixed target와 schema-version-2 문구로 계측을 정정했고, 초기 결과는
`result-initial-selector-probe.json`으로 별도 보존했다. 초기 구 설치에는 두 기준 모두 selector가
없었으므로 유실 재현 결론은 변하지 않았다.

## R1-07 — 재현한 세 상태 변경 문제의 최소 수리

제품 코드 변경 전 실제 파일 상태를 검사하는 세 회귀를 먼저 만들었다.

- invalid UPS가 SessionStart 누락 시 독립06 baseline을 쓰지 않는다.
- merged context overflow로 UPS가 차단돼도 새 declared-risk 파일을 쓴다.
- 같은 overflow에서 기존 declared-risk 파일을 삭제한다.

이 세 test를 `python -m unittest`의 fully-qualified test 이름으로 실행해 3 tests/failures3/exit1을
확인했다. baseline 파일 부재, risk 파일 생성, 기존 risk 파일 삭제가 각각 실패 원인이다.
overflow는 현재 작은 정상 risk 안내만으로 자연 발생했다고 주장하지 않는다. IO renderer에 큰
문자열을 주입해 예산 방어 경로를 열되 실제 risk core/파일 commit을 그대로 사용한 재현이다.

`hook_runtime.py`만 다음과 같이 수리했다.

- `run_capture_declared_risk`의 overlay 검사 전에 기존 `_ensure_session_06_snapshot`을 실행한다.
  baseline claim 실패 시 기존 exit2를 유지한다. 같은 session의 write-once 계약은 그대로다.
- `_capture_declared_risk`에 선택적 `before_commit` 검사를 추가했다. risk 안내를 한 번 render하고
  catalog와 병합한 문자열을 검사한 뒤에만 risk cleanup/write/clear를 수행한다. 검사 실패 시
  body-free native block만 반환하고 해당 risk 상태와 만료 상태도 변경하지 않는다.
- 성공한 commit 뒤에는 미리 검사한 같은 risk 출력 문자열을 사용한다. 비SAGE의 기존 출력은 유지한다.
- parent/doctor 담당의 언어 helper 계약에 맞춰 `error_message` 호출 여섯 곳 모두 `root=root`를 넘겼다.
  error helper/i18n 파일은 이 담당자가 편집하지 않았다.

수정 후 overlay runtime module 30개가 모두 통과했다. 새 baseline 회귀는 차단 입력을 외부 수리한
다음 UPS가 성공하고 기존 baseline 바이트를 덮어쓰지 않는 것까지 검사한다. overflow 회귀는
capture/clear뿐 아니라 다른 만료 risk 파일의 cleanup도 실행되지 않음을 검사한다.

## R1-05 역할 회귀 연결

parent가 실제 `claude --agent diagnostic-root`의 main payload에 `agent_type`만 있고 child 식별자는
없음을 재현했고, doctor 담당이 `overlay_context.role_for`를 수정했다. 이 담당자는 다음 runtime
소비자 회귀를 추가했다.

- `agent_type`만 있는 main event는 root catalog를 받는다.
- `agent_id`, `parent_session_id`, `parent_thread_id` 각각의 양성 child 식별자는 새 root catalog를 억제한다.
- 두 IO host에서 위 계약을 검사했다. 실제 main-agent native 최종 재검증은 parent 담당이다.

## scoped 검증과 한계

Python: `/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`.
`SAGE_TEST_TMPDIR`와 `TMPDIR`는 B로, `PYTHONPATH`는 repository tests 디렉터리로 명시했다.

넓은 scoped 검사의 첫 harness는 존재하지 않는 `test_io_claude`/`test_io_codex`를 지정해
218 executions/failures0/import errors2/exit1이었다. 이를 제품 결함이나 성공으로 세지 않았다.
`harness-error-runtime-scoped.log`와 summary를 보존하고 실제 suite 이름을 확인해 재실행했다.

정상 scoped 대상은 `test_overlay_runtime_delivery`, `test_hook_runtime`, `test_capture_declared_risk`,
`test_compact_reentry`, `test_runtime_api_preflight`다. 252 tests/failures0/errors0/skipped0/exit0.
[상세 로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/runtime-scoped.log),
[집계와 subject hash](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/runtime-scoped-summary.json).
그 후 parent의 혼합설치 guard가 추가되어 기존 `# CORE`만 둔 legacy-span toy fixture가 차단되는
30개 재검사 실패1을 발견했다. 제품 guard를 완화하지 않고, 정상 새 설치를 시험하는 해당 fixture에
실제 현재 CORE selector와 runtime 두 파일을 배치했다. 실패 원자료는
`guard-fixture-r1-runtime-final-30.log`에 보존했다. 최신 전체 scoped252개 재실행은
failures0/errors0/skipped0/exit0, 9.191s였다. 위 링크의 최신 log/summary는 이 결과를 가리킨다.

초기 R1-07 수리 시점 소유 파일 hash(위 C2 후속 수리와 구분):

- `hook_runtime.py`: `4e859f2649a4b7f15625a52914a072ba7ce42c0b3b3feeac7a9fa0dfdaee2cbe`
- `test_overlay_runtime_delivery.py`: `51975194890c1c698120bc2d2c4ed7dd8b731abc9740bda2ee579ebc07bb54a9`

`git diff --check` exit0와 두 Python 파일의 AST parse를 확인했다. parent 요청에 따라 제품·테스트를
초기 상태로 고정했다. 이후 Codex native 반례에 따른 parent 승인 추가 수리와 C2/C3 구분은
위 후속 기록을 따른다.

전체 공식 runner, 최종 clean wheel consumer, 다른 OS/Python, 실제 계정 모델, 새 유효 Phase05
독립 리뷰와 Phase06 판정은 이 담당자가 실행하지 않았다. native R1-01 반대 관측과 R1-04 실제
유실 재현 및 R1-07 코드 수리·단위 회귀를 각각 분리해 보고하며 통합 승인으로 표현하지 않는다.

## 유효 R1 후 C4-P-01 — 설치 정책 정체성과 catalog root 분리

`round1-triage.json`, `peer-repro-r1/results.json` 및 두 whole-round refuter 원문에서 양측이
유지한 C4-P-01을 재현·수리했다. 이전 R1-02의 catalog 격리 의도를 기각한 것이 아니다.
중첩 비SAGE Git 경계N의 catalog를 부모 설치P로부터 격리하는 동작은 유지하면서, 비overlay
위험 선언·06 baseline·Stop 집행까지 N으로 옮긴 회귀를 수리하는 범위다.

### RED와 구현

실제 `python -m sage.hook_entry` subprocess를 쓰는6개 신규 test를 먼저 추가했다.
양 host의 P risk 상태, P baseline, P Stop first/retry 실제 평가, 부모 개인 catalog 비노출,
다른 SAGE rootB와 explicit root 우선, 구 dispatch 혼합 경계를 검사했다. 새 API 설치 요구를
구 API2 package가 거부하는 검사도 포함한다. 최초6 tests/failures6/exit1이었다.
실패는 부모 risk 파일 부재(양 host subtest), 부모 baseline 부재, 부모 Stop report 부재,
구 dispatch가 잘못 실행됨, 새 설치가 API2로 표시됨이었다. 실제 rootB/explicit 우선 회귀는
이전 동작부터 정상이라는 것도 분리해서 확인했다.

소유 제품 네 파일만 수정했다.

- `sage/hook_entry.py`: 상속된 `SAGE_PROJECT_ROOT`/host root를 덮기 전에 보존한다.
  explicit root가 없고 event rootN에 SAGE marker가 없으며 상속P에 설치 marker가 있을 때만
  정책 root=P/catalog root=N으로 분리한다. 실제 SAGE rootB·손상된 설치 marker 및 explicit root의
  기존 경계는 유지한다. profile/core/API preflight와 정책 환경은 P를 사용한다.
- `run_hook.dispatch(..., *, overlay_root=None)`를 통해 필요한 세 overlay 경계에만 N을 전달한다.
  risk/SessionStart baseline·Stop·기타 기존 집행은 P를 사용한다. standalone CLI에는 optional
  `--overlay-root`를 추가했고 explicit `--root`의 기본 계약은 바꾸지 않았다.
- `hook_runtime.py`: UPS의 catalog 검사, SessionStart catalog, 도구 전제조건은 명시된
  `overlay_root`를 사용하고 risk state/baseline/Stop의 기존 root는 그대로 둔다.
- `sage/runtime_api.py`: 설치 dispatch 입력 계약 변경을 API3으로 표시한다. 구 API2 package는
  API3 설치를 core import 전에 거부한다. 새 package가 구 project-local API2 dispatcher를 만난
  split-root 경로에서는 호출 전에 명시적인 API3/full-upgrade 진단으로 종료한다. 지원되지 않는
  keyword를 넘기거나 부모 catalog로 조용히 후퇴하지 않는다. same-root 구 dispatcher의 기존
  호출 계약은 유지한다.

Stop 재시도 규칙이나 gate 정책 자체는 바꾸지 않았다. Stop은 P에서 첫 평가를 수행하고,
재시도에서도 P runtime을 실행해 기존 WARN/exit0 정책으로 수렴한다. 누락 profile 때문에 N에서
첫 block→단순 retry pass로 빠지던 경로를 P의 실제 집행으로 바꾼 것이며 무한 block 대체가 아니다.

### GREEN, 전체 설치 probe 및 호환 경계

신규6 tests는 구현 후 OK/exit0, 1.110s였다. `test_hook_entry`, `test_runtime_api`,
`test_runtime_api_preflight`, `test_overlay_runtime_delivery`, `test_hook_runtime`,
`test_capture_declared_risk`, `test_compact_reentry`의319 scoped tests는
failures0/errors0/skipped0/exit0, 12.265s였다.
[로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/root-split/root-split-scoped.log),
[명령 대상·제품/test hash](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/root-split/root-split-scoped-summary.json).

부모 검토에서 새 test에 이번 실행 경로를 hardcode한 점을 발견했다. 제품 test는 기존 관례의
`tempfile.TemporaryDirectory(prefix='sage-root-split-')`로 보정하고, 로컬 실행 명령에서만
승인된 B/runtime/root-split을 TMPDIR로 지정했다. 이 portable 보정 후 같은 신규6 tests를
재실행해 OK/exit0, 0.959s를 확인했다. CI나 다른 checkout에 이번 실행 폴더를 만들지 않는다.

이어서 B/runtime/root-split/source에 고정한 소스로 각 host의 새 실제 consumer를
`install --dest P`와 `generate --root P --dest P --target <host>`로 설치했다.
각 hook은 consumer cwd에서 **`--root`를 강제하지 않고**, 상속 설치 root=P와 event cwd=N을
함께 전달한 실제 CLI subprocess로 호출했다.

| 전체 설치 probe | Claude | Codex |
|---|---|---|
| 설치 manifest runtime API | required3 | required3 |
| nested UPS risk 상태 위치 | P, rc0 | P, rc0 |
| N logs / P 개인 catalog 노출 | 없음 / 없음 | 없음 / 없음 |
| P baseline 보존 | 동일 hash | 동일 hash |
| Stop 첫 평가 | rc2, P report 생성 | rc0 + native decision:block, P report 생성 |
| Stop retry | rc0, P 정책 보고 | rc0, P 정책 보고 |
| 새 package + 실제 C4 구 runtime2 | API3 upgrade 진단/rc2 | API3 upgrade 진단/rc2 |
| 혼합 상태 TypeError / P catalog 노출 | 없음 / 없음 | 없음 / 없음 |

혼합 probe는 단순 함수 mock뿐 아니라 실제 보존 C4의 project-local hook 전체를 새 package와
결합해 확인했다. 원자료는
[설치/명령/rc/stdout/stderr](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/root-split/installed-consumer-commands.json),
[집계](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/runtime/root-split/installed-consumer-results.json),
`root-split/source-files.json`이다. 기존 QA consumer나 엔진 설치 상태는 변경하지 않았다.

최종 소유 제품 SHA256:

- `sage/hook_entry.py`: `34ca7c82af4caa249a3345b67bdf4b999188a60e32d40836764ab4376781a7e6`
- `sage/runtime_api.py`: `d379f1f5eb79cf4c9a5f5963b6a2b590dd5213ec3d70af84b564a751398a102a`
- `hook_runtime.py`: `ba50059d6b7ff0c4fe3ce4b09c843460c0a6b97a0f05da2b6f69a14d7a6acaf7`
- `run_hook.py`: `8f9c391640f341373a3137f5a8b7e048b1c4c75ddd9a1aff123e6262639d4eb2`

### 추가 native 설치 수용 범위

이 재작업은 실제 계정 모델이나 native app-server를 새로 호출하지 않았다. 최종 통합 수용에서는
API3 package/설치 core/runtime의 일치와 새 clean wheel을 확인하고, 양 native host에서
**상속 host identity=P 및 event cwd=N이 실제로 함께 도착하는지** 먼저 capture해야 한다.
N에서 UPS 선언→P baseline/state, Stop first→retry의 P report, 부모 개인 catalog 미공급 및
실제 SAGE rootB/explicit root 우선도 확인한다. `--root P`를 강제하는 기존 recorder는 explicit
우선 경로이므로 이 split-root 분기의 증거로 재사용하지 않는다. 구 API2 설치는 split-root에서
명시적 업그레이드 진단으로 닫히고 body fallback이 없는지도 기록한다. 위 CLI 제품 시험을 그
native 전송/모델 행동 수용 완료로 승격하지 않는다. 전체 runner/최종 wheel/독립 R2는 parent 담당이다.

## 재시작 유효 R1 F04 — 비SAGE 경계의 명시적 빈 catalog 대체

근거 B2는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106`이다.
`refuters-r1/refuter-a/result.txt`와 `refuter-b/result.txt`는 모두 F04를 유지하고 F05를 반증했다.
P의 독립 gate/risk/baseline을 보존하는 root 분리는 유지하되, catalog 소유가 비SAGE N으로 이동하면
직전 P catalog를 대체할 빈 묶음을 실제로 내보내야 한다는 범위만 수리했다. P overlay inventory를
N의 새 전제조건으로 추가하는 F05는 수리하지 않았다.

### 재현과 최소 구현

제품 수정 전 신규4 tests를 실행했다. 4 tests/failures9/exit1이었다. 양 host UPS는 risk 안내만
출력했고, resume/fork에는 catalog가 없었으며 compact에는 기존 reentry만 있었다. 또 explicit
absence 옵션이 구현되지 않았다는 assertion이 실패했다. startup/child 금지는 수정 전부터
통과했으며 이것을 새 기능 성공으로 세지 않았다.

소유 제품 `runtime/overlay_context.py`, `runtime/hook_runtime.py`만 수정했다.

- `current(..., empty_if_absent=False)`라는 backward-compatible optional 옵션을 추가했다.
  일반 비SAGE 호출은 이전처럼 `('', None)`이다. 설치된 정책 P와 명시 catalog root N이 분리되고
  N의 SAGE marker가 없을 때에만 UPS와 SessionStart가 옵션을 사용한다.
- root 역할에만 기존 API3 package에도 있는 `_collect(realpath(N), 'root', [])`와
  `render_catalog`를 재사용한다. schema2/root/role/generation/source/target 및 정렬·hash·host budget을
  새로 복제하지 않는다. N의 marker 부재 때 `load_profile(N)`은 빈 profile을 반환하고, inventory를
  명시적으로 비우므로 비SAGE overlay 본문이나 P catalog를 탐색하지 않는다. 중간에 marker가
  나타나면 `unstable_snapshot` 진단으로 종료한다.
- UPS는 실제 context가 없는 경우에만 legacy plain fallback을 사용한다. 따라서 N의 빈 묶음은
  risk 안내와 같은 native JSON 응답에 들어간다. risk/baseline의 기존 P 위치는 바꾸지 않았다.
- resume/fork/compact는 N의 명시적 빈 묶음을 포함한다. startup은 계속 본문을 defer한다.
  child 식별자/명시 worker role에는 새 root catalog를 넣지 않는다. 새 API4, dispatcher 인수,
  persistent state나 중앙 helper 체계를 추가하지 않았고 collector 파일을 수정하지 않았다.
- 기존 SessionStart의 P L1 advisory 실행 자체는 보존했다. 그 기존 P 읽기까지0이라고 주장하지
  않는다. 다만 P L1 오류가 독립 N의 정상 empty replacement를 지우는 조건은 분리했다.
  P에 잘못된 unused overlay가 있어도 N의 빈 대체가 공급됨을 회귀로 확인했다.

### GREEN과 API3 구 package 호환

신규 회귀를 포함한 runtime module38개는 OK/exit0, 1.107s였다. 양 host의 실제
`python -m sage.hook_entry` subprocess에서 상속 P/event cwd N을 사용해 P catalog → N empty →
P catalog 복귀를 확인했다. N의 sources/targets는 모두0이며 generation은 P와 다르고 같은 N에서
안정적이다. P risk 상태는 남고 N logs는 생기지 않았다. N의 resume/fork/compact도 같은 빈 묶음을
공급했다. 이는 entry/host-wire 제품 시험이며 native 호스트에서 전환이 자연 발생했거나 실제 모델이
빈 대체를 해석했다는 관측은 아니다. model 호출은 하지 않았다.

빈 catalog 생성 helper 자체에 대한 body read spy는 `read_text_lf`0회와 overlay `_read`0회였다.
N에 unused 비SAGE overlay 파일을 두어도 읽지 않았다. 일반 nonSAGE pass-through, startup defer,
`agent_id`/`parent_session_id`/`parent_thread_id`, 명시 reviewer role의 새 catalog 억제를 유지했다.

새 runtime helper를 실제 보존 C5 API3 package와 연결해 양 host에서 실행했다. 기존
`sage/overlay_delivery.py` hash `350df71a554a3a31206df44b108b5aa4925b1a637b09edc08c6dd52658383aad`의
`_collect`/render만으로 source0/target0, 같은 generation의 빈 schema2를 생성했다.
[구 C5 package 실행 결과](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106/runtime-F04/old-c5-package-results.json).

최종7module scoped 검사는324 tests/failures0/errors0/skipped0/exit0, 14.409s였다.
대상은 overlay runtime, hook runtime, hook entry, runtime API/preflight, declared risk, compact
reentry다. [상세 로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106/runtime-F04/scoped.log),
[대상·개수·hash](/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106/runtime-F04/scoped-summary.json).

최종 SHA256:

- `hook_runtime.py`: `36d0d6612e4c1da7887ba65b74f80cfdbf6c7f2a9329cd4215cc31c43e39dcf9`
- `overlay_context.py`: `e9f7f6b9504faf6d5301a34fecf5d8e4585969ffaefe540b6fbd0142022cfb01`
- `test_overlay_runtime_delivery.py`: `a348542a7a150893df41792d8d27cf61b12cc178f1d137ae33dcc39a1a7e0d1f`

`test_hook_runtime.py`, root identity, API3, collector, Stop/risk gate 정책은 추가 수정하지 않았다.
전체 runner/최종 consumer/native 수용/독립 리뷰 판정은 parent가 통합 source를 고정한 뒤 수행한다.
이 담당자는 commit/push/model 호출 없이 scoped 검증과03 기록 후 제품·테스트를 고정한다.
