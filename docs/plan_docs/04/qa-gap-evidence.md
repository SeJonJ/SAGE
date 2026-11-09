# Phase 04 독립 QA — 설계·구현 gap과 검증 범위

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: NOT_TESTED — 발견 QG-01/QG-02 수리 후 독립 코드 경계 재검증 PASS, 통합 native acceptance 미판정
Evidence-Date: 2026-11-05

## 범위와 근거의 성격

독립 QA가 `00~03/overlay-context-delivery.md`, 03 소유별 증거, 정본 `docs/superpowers/specs/2026-11-05-overlay-context-catalog-design.md`와 실제 collector/runtime/materialize/CORE/test 소스를 읽었다. 이 기록은 parent의 요약 판정을 근거로 삼지 않는다. 제품 소스·테스트 파일을 수정하지 않았고, 엔진 root의 SAGE gate/review-loop/waiver, commit/push를 실행하지 않았다. 전체 suite·실제 모델·native host acceptance는 이 역할에서 실행하지 않았다.

재현은 `/Users/sejon/project/sage_project_worktree/overlay-context-phase04-qa-1105a/` 아래 격리 consumer 디스크 fixture와 실제 제품 Python 함수/host adapter를 사용했다. 아래 rc와 JSON은 코드 경계 관측이다. Claude/Codex 프로세스가 그 출력을 수신하고 실제 모델 요청·도구를 차단했다는 증거는 아니다. 다른 역할이 진행하는 native/CI 검증의 최종 상태는 이 문서가 대신 판정하지 않는다.

## 확인한 구현 계약

- `sage/overlay_delivery.py:112`는 shared/personal 전체 inventory를 기존 `_read`로 검사한 동일 LF 문자열에서 hash/content를 만들고 root 7종만 catalog에 싣는다. `:134`는 source 참조를 shared 표준 → shared Fast → personal 표준 → personal Fast 순서로 조립한다. `:167`은 snapshot 전후 비교와 1회 재시도를 구현한다.
- `sage/overlay_classify.py`의 7종 정책표와 Fast 3종 BACKING은 물리 worker와 context root 스킬을 구분한다. `sage/overlay_materialize.py:240` 이후는 소유가 확인된 legacy span만 제거하고 손상 span을 충돌로 반환한다.
- 7종 CORE spec/render에는 자기 고정 target과 현재 root/role/generation 확인, 다른 target 미적용, 공유 우선, 자동 Fast 선택 금지, child 진입/복귀의 view 계약이 있다. 이 문구의 존재는 모델의 실제 준수를 증명하지 않는다.
- SessionStart는 startup 본문을 생략하고 resume/fork/compact에서 공급한다. UPS는 catalog와 선언 risk 출력을 단일 JSON으로 합친다. 입력 source 오류의 UPS 차단·지원 도구 rc2는 unit fixture에서 확인됐다. 그러나 아래 L1/render 오류의 경로는 같은 보장을 충족하지 않는다.

## 발견 QG-01 — 최초 FAIL, 수리 후 코드 경계 재검증 PASS

원래 반례: L1에서 감지한 손상 render가 UPS/도구 검사에서 통과

- 중요도: 높음. 위험: 설치된 CORE의 손상 managed span이 남은 상태에서 정상 catalog가 제공되고 지원 제품 도구 실행 전제 검사가 성공한다. A5의 공유 L1 오류/손상 마커 fail-closed, M4/M5에 해당한다.
- 위치: `scripts/sage_harness/hooks/runtime/overlay_context.py:28~42`, `hook_runtime.py:868~896`, `hook_runtime.py:2007~2028`; 설치 render 검사는 `sage/overlay_materialize.py:240` 이후에만 있다. `current()`는 source/profile/manifest collector를 호출하고 render/L1 상태는 검사하지 않는다.
- 입력: 정상 `sage/project-profile.yaml={}`, 정상 shared `sage-team.md`; `.claude/skills/sage-team/SKILL.md` 또는 `.codex/skills/sage-team/SKILL.md`에 `BASE\n` + `overlay_common.MARKER_START` + 닫히지 않은 본문. Codex는 실제 local CORE 파일을 통해 project-local scope가 확인된다.
- 명령: `$PY /Users/sejon/project/sage_project_worktree/overlay-context-phase04-qa-1105a/probe_l1.py`, `$PY=/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`.
- 관찰: 두 adapter 모두 SessionStart resume는 `rc=2`, catalog 없음, malformed marker BLOCK 진단. **파일을 고치지 않은** 다음 UPS는 `rc=0`, catalog 있음. 같은 fixture의 `run_hook.dispatch(... generated-artifact-write-guard ..., tool_name=Bash)`는 `rc=0`, stdout/stderr 없음.
- 근거: scratch의 `probe_l1.py`, 최초 tool 관측 요약 `initial-red-observation-summary.json` (재실행 결과는 아래 별도 기록). SessionStart/UPS/PreToolUse 제품 함수를 실제 호출했고 이 재현 분기에는 mock을 사용하지 않았다. session_id를 생략해 이번 반례와 독립적인 baseline 디스크 쓰기를 피했다.
- 최소 수정 제안: 공통 event 입력 검사에 현재 host/scope의 설치 render malformed/소유 충돌을 읽기 전용으로 확인하는 경계를 포함하고, UPS/PreToolUse에서 같은 오류를 block으로 변환한다. 과거 오류 latch 대신 매 경계의 현재 파일을 검사해야 외부 수리 후 즉시 복구한다. 정상 source를 재읽는 중복은 피한다.
- 필요한 회귀: 두 host에서 malformed/소유 불명 span → SessionStart 본문 없음 → 다음 UPS block → Read/Bash 등 지원 도구 deny → 외부 span 수리 후 다음 UPS/도구 정상 복구. 기존 `test_shared_l1_error_does_not_skip_baseline_or_reentry`는 잘못된 **source inventory**만 쓰며 손상 설치 render를 시험하지 않는다.

## 발견 QG-02 — 최초 FAIL, 수리 후 코드 경계 재검증 PASS

원래 반례: 실제 legacy span 제거의 권한 오류를 정상 catalog와 함께 통과

- 중요도: 높음. 위험: stale legacy shared body와 새 context catalog가 함께 남아 두 전달 경로가 다른 본문으로 움직인다. 정본 §10/M4의 shared 디스크 사본 제거, A5의 예외 fail-closed를 어긴다.
- 위치: `scripts/sage_harness/hooks/runtime/hook_runtime.py:1902~1907`. `materialize`의 예외를 문자열 포함 WARN으로 출력하고 0을 반환한다. 호출부 `:2013`은 반환값이 0이면 catalog를 억제하지 않는다.
- 입력: 정상 profile/source, 설치 SKILL에 `BASE\n` + `overlay_common.compose_block('OLD_SHARED_BODY','skills','sage-team')`; 해당 SKILL 디렉터리 권한 `0555`. 정상 span 제거를 위한 임시 파일 생성이 실제 `PermissionError`로 실패한다.
- 명령: `$PY /Users/sejon/project/sage_project_worktree/overlay-context-phase04-qa-1105a/probe_permission.py`.
- 관찰: 두 adapter 모두 SessionStart resume `rc=0`, catalog 있음, `legacy_body_remains=true`; stderr는 `overlay convenience sync 실패: PermissionError`. mock 없는 실제 파일 권한 오류다. fixture 디렉터리 권한은 probe의 finally에서 `0755`로 돌렸으며 제품 파일은 변경하지 않았다.
- 근거: scratch의 `probe_permission.py`, 최초 tool 관측 요약 `initial-red-observation-summary.json` (재실행 결과는 아래 별도 기록). 보조 주입 실험은 `materialize` 예외 문자열 `PRIVATE_L1_ERROR_SENTINEL`이 그대로 stderr로 출력됨도 보였다(최초 tool 관측 요약 `initial-red-observation-summary.json`). 실제 권한 반례의 stderr는 파일 경로이며, 이 관측만으로 실제 개인 본문 누출이 있었다고 주장하지 않는다.
- 최소 수정 제안: 설치 확인된 checkout의 materialize 예외를 본문 없는 안정 code/path와 실패 결과로 변환해 SessionStart catalog를 억제한다. baseline/reentry는 계속 시도한다. QG-01 수정 경계에서도 현재 legacy span/충돌 상태가 해결되지 않았으면 UPS/도구를 보류하고 외부 수리 후 해제한다. 예외 원문 출력도 제거한다.
- 필요한 회귀: 정상 legacy span + write permission failure/예외 → catalog 없음, baseline/reentry 보존, UPS/도구 보류; 권한/원본 수리 후 정상 수렴. 현재 runtime 테스트의 예외 시험은 collector 예외만 주입한다.

## 테스트 실행과 coverage 공백

독립 QA가 아래 scoped 일반 unittest를 다시 실행했다. 모두 exit 0이다. 합계 60개 통과는 코드 fixture 결과이며 A1~A8 native/행동 PASS가 아니다.

| 명령 (`$PY -m unittest discover -s scripts/sage_harness/hooks/tests`) | 결과 | 입증 범위 |
|---|---|---|
| `-p test_overlay_delivery.py -q` | 24 tests, OK | source/target/schema/hash/snapshot/입력 오류/collector 예산 |
| `-p test_overlay_runtime_delivery.py -q` | 20 tests, OK | 함수 단위 event 출력·source 오류·역할/root·기초 복구 |
| `-p test_overlay_reclassification_backing.py -q` | 16 tests, OK | 일반 순수 구조 oracle의 단계/감사/보고/acceptance 하한 |

Fast four-slot 시험(`test_overlay_reclassification_backing.py:191~249`)은 네 slot 이름마다 동일한 악성 **상태**를 독립 oracle에 주입한다. oracle은 overlay 본문을 읽지 않는다는 설계 §12의 구조 검증에는 맞는다. 실제 네 파일의 악성 지침을 모델이 받고 자동 Fast 선택을 하는지, 다른 target을 적용하는지는 시험하지 않는다. 이 구분을 A3/A6 통합 PASS로 축소하면 안 된다.

예산 probe는 정상 shared 4 source에 각각 double quote 5,000개를 넣었다. collector catalog는 **41,943 UTF-8 bytes**, outer native JSON stdout은 **82,135 bytes**, JSON을 해석한 additionalContext는 **41,943 bytes**, `rc=0`이었다. 원자료는 `probe_budget.py`, `budget-results.json`이다. `render_catalog`는 inner catalog wrapper/escape만 계산하며 outer host envelope/같은 handler의 다른 문맥은 이후 조립된다(`overlay_delivery.py:191`, `io_codex.py:126`, `hook_runtime.py:883`, `:2025`). 이 숫자로 `additionalContextLimit=60000`의 초과나 실제 host 잘림을 단정하지 않는다. host limit 단위, 전송 envelope bytes, decoded context bytes, tokenizer 계측, 두 사본/누적 문맥 비용을 별개로 실측할 필요가 있다. 현재 명시적인 최종 host payload 합산 검사/실측 지원 한도는 독립 확인되지 않았다.

설치/upgrade/rollback/clean wheel 결과는 다른 역할의 일반 consumer 실행 증거가 필요하다. 이 QA는 root 설치나 전역 설정을 바꾸지 않았다. 기존 03 전체 suite 결과나 지금 진행 중인 CI 수리를 최종 성공으로 재분류하지 않는다.

## 수용 조건 현증거

상태는 이 **독립 QA 범위의 현재 통합 증거** 기준이다. 일부 소항목의 unit PASS를 전체 항목 PASS로 승격하지 않는다. 필수 A1~A8 중 N/A 항목은 없다.

| ID | 상태 | 확인된 부분 근거 | 남은 증거 또는 실패 |
|---|---|---|---|
| A1 | NOT_TESTED | 14 source/7 view collector와 양 adapter UPS fixture PASS | 제품 설치 후 두 native host의 직접/구조화/암묵 진입 실제 요청, 앞/중간/끝/hash, fetch 없음 |
| A2 | NOT_TESTED | resume/fork/compact event 함수 fixture PASS | 두 host의 수동·자동 압축/resume 뒤 실제 새 공급과 다음 작업의 복구; 요약 잔존과 구별 |
| A3 | NOT_TESTED | 7종 selector와 순서 존재, 구조 oracle PASS | 실제 모델 표준 두 슬롯/Fast 네 슬롯만 적용, 타 target/root 유혹, 요청하지 않은 Fast 선택·전환 방지 |
| A4 | NOT_TESTED | env reviewer와 명시 없는 child의 신규 root 본문 억제 fixture PASS | 실제 중첩 plan/team/review/return, worker packet·headless reviewer 본문/refs, inherited context 구별 |
| A5 | NOT_TESTED | source 오류 fixture PASS; QG-01·QG-02 최초 FAIL → 수리 후 독립 반례·외부 수리 복귀 PASS | 코드 경계 반례는 닫힘. 두 실제 native host의 요청/지원 도구 차단과 coverage 전체 수용은 별도 필요 |
| A6 | NOT_TESTED | Fast BACKING·악성 상태 구조 oracle, 표준→Fast source 참조 fixture PASS | 실제 최초 상속/모델 행동 및 fresh/convert/review/close 통합 증거를 source fixture와 연결해야 함 |
| A7 | NOT_TESTED | 정책/소유 span 검사 소스 확인; QG-02의 제거 실패 반례 보존 | global/local·두 checkout·upgrade/rollback·clean wheel·원본/비노출·멱등성의 실제 consumer 증거 필요 |
| A8 | NOT_TESTED | source/inner catalog byte 한도 테스트 PASS, escape 계측 위 수치 | 최대 지원 입력·두 사본·여러 turn·한국어·CORE/대화 여유·spill/잘림/연속 자동 압축 루프·확정 host 단위/버전/비용 |

## 후속 확인 경계

QG-01/QG-02는 아래 수리 재검증으로 코드 경계 반례를 닫았다. 실제 native 호스트의 차단/복구 증거는 별도로 확인한다. source/설치/함수 출력/native host 전달/실제 모델 행동/독립 05 리뷰/최종 사용자 승인 기록을 서로 대신 세지 않는다. 이 문서는 발견과 검증 gap의 근거이며 최종 승인·출시·cycle 종료 판정이 아니다.


## QG-01/QG-02 수리 후 독립 재검증

parent의 제품 수리 보고 후 이 QA가 수정 소스를 직접 읽고 원래 `probe_l1.py`와 `probe_permission.py`를 동일 Python으로 재실행했다. 이후 신규 scratch `probe_repair_recovery.py`에서 외부 수리·복귀까지 독립 assert했다. 제품 소스/제품 테스트는 수정하지 않았다. 재실행한 두 기존 probe는 고정 결과 파일명을 사용하므로 `l1-results.json`/`permission-results.json`이 최신값으로 갱신됐다. 최신 사본은 `l1-recheck-results.json`/`permission-recheck-results.json`에 보존했다. 최초 tool stdout 관측의 주요 값은 `initial-red-observation-summary.json`에 출처 성격을 명시해 기록했으며, 이를 최초 전체 raw JSON 사본이라고 부르지 않는다.

변경 소스에서 `overlay_context.current(..., runtime=..., validate_materialization=True)`는 source collector 후 `plan_materialize(context_validated=True)`를 읽기 전용으로 실행한다. 현재 render 오류 또는 실제 변경 필요 span이 있으면 정상 catalog 대신 오류를 반환한다. SessionStart는 L1 수리를 먼저 허용하기 위해 이 사전 render 검사를 생략하되 L1 예외를 본문 없는 `render_sync_failed`/rc2로 변환한다. UPS/PreToolUse는 실제 runtime을 넘기며 동일 읽기 전용 검사를 쓴다.

| 독립 관측 (Claude/Codex 두 adapter 동일) | 수리 후 결과 |
|---|---|
| QG-01 unclosed marker → SessionStart | rc2, catalog 없음 |
| 같은 손상 marker를 유지한 UPS / Bash PreToolUse | 각각 rc2, catalog 없음 / 도구 검사 차단 |
| 외부 editor로 marker를 제거한 다음 UPS / Bash | rc0 + catalog / rc0, latch 없음 |
| QG-02 정상 legacy span + directory 0555 → resume/compact SessionStart | 실제 PermissionError, rc2, catalog 없음. compact reentry 출력은 보존 |
| 같은 권한 오류 및 잔류 span의 다음 UPS / Bash | 각각 rc2, catalog 없음 / 도구 검사 차단 |
| 권한만 0755로 복구하고 span이 남은 다음 UPS | rc2 (`render_sync_required`). 실패 latch가 아니라 현재 실제 span이 남아서 차단 |
| 외부 수리로 actual materializer를 실행해 정상 span 제거 후 다음 UPS / Bash | legacy body 제거 확인, rc0 + catalog / rc0 |
| 주입 OSError sentinel | rc2, catalog 없음, exception sentinel은 stdout/stderr에서 제거됨 |

실행 명령은 `$PY <scratch>/probe_l1.py`, `$PY <scratch>/probe_permission.py`, `$PY <scratch>/probe_repair_recovery.py`이며 모두 exit0이었다. 마지막 probe는 위 차단·수리·복구 결과와 실행 전후 source hash 동일성을 assert하여 PASS했다. 상세 결과는 `<scratch>/repair-recovery-results.json`이다. 여기서 `<scratch>`는 이 문서 앞의 `overlay-context-phase04-qa-1105a` 절대 경로다.

`$PY -m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay_runtime_delivery.py -q`도 독립 재실행하여 **23 tests, OK, exit0**을 확인했다(`runtime-recheck.log`). 새 결함이나 반례는 이 재검증 범위에서 발견하지 않았다. QG-01/QG-02의 **동일 코드 경계 반례는 PASS로 닫지만**, A5 전체의 native host 요청/도구 coverage 검증은 여기서 수행하지 않아 NOT_TESTED를 유지한다.

재검증의 source hash 8개는 `repair-recovery-results.json`의 전후 두 map이 동일했다. 주요 파일은 아래와 같다. 이는 제품 전체 tree freeze나 이후 변경 부재의 증명이 아니다.

| 파일 | SHA-256 |
|---|---|
| `runtime/overlay_context.py` | `f1661ce6af0c58bf6dd926c61512f74b2cd9ef4bc079de8097032fded9faca96` |
| `runtime/hook_runtime.py` | `f81bd11adac9b27fdb9a48620ab2c5cc5ac931d99853cd9fd42017dd3e18abf1` |
| `runtime/run_hook.py` | `845a7e91befbfb3da713c006cd759c57e2d535ff55dbc74d832f99bc211db8e1` |
| `runtime/io_claude.py` | `a3c91bbcc569335954b6d9da27e7791b5795eb4ae9a5a428c3abc2cd8d916a1d` |
| `runtime/io_codex.py` | `d767b14a9f16a9690481b6e0bff340f78465e776c73bf5ba5af29d03acf3ca91` |
| `sage/overlay_delivery.py` | `10744157fbc08f92f29f968c342cae168066ccc4d9b1a0e7e911bc41f9b2225c` |
| `sage/overlay_materialize.py` | `e1b56f7d7823e1600f7a49ac3b0839567693b6da730fe14ccd3c871d7459de4c` |
| `sage/overlay_classify.py` | `9efabbce84f5005463d93b47d3d789c81ad2a6ee8942c9c9faeb2dba51fbd51d` |

표의 `runtime/`은 `scripts/sage_harness/hooks/runtime/`이다.
