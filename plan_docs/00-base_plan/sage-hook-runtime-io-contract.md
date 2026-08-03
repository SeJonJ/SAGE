# [Base Plan] SAGE 10-j-1 hook 런타임 IO 계약 정합

Cycle-Stem: `sage-hook-runtime-io-contract`
Risk Level: L3
Status: IMPLEMENTED (2026-08-03, 미커밋 · 독립 리뷰 전)

## 1. Context

10-j(장수 브랜치 다중 사이클 결속·선언 risk)의 첫 사이클이다. 결속 판정 자체가 아니라
**게이트가 내린 판정이 런타임 IO 계층에서 잘못 전달되거나 아예 트리거되지 않는** 결함 세 건을 닫는다.
셋 다 `0.9.77` 실측이며, 착수 전 소스에서 재확인했다.

| 결함 | 위치 | 확인된 사실 |
|---|---|---|
| 이동 파일 미추적 | `runtime/io_codex.py` `extract_phase4_changes` | `*** Add\|Update File:`만 수집하고 `*** Move to:` 목적지를 버린다. 같은 모듈의 `extract_changes`, `extract_logged_changes`는 Move를 처리한다 |
| BLOCK 채널 불일치 | `runtime/io_claude.py` | `render_gate`, `render_phase4`, `render_stop_result`가 BLOCK 문구를 stdout으로 낸다. Claude Code는 exit 2 hook의 차단 사유를 stderr에서 읽는다. codex 대응 함수는 셋 다 block을 stderr 또는 decision JSON으로 보낸다 |
| snapshot 형태 분기 | `runtime/hook_runtime.py` `_project_snapshot` | `plan_reads` 부재 시 `{}`를, 존재 시 `{"glob_results":…, "files":…}`를 반환한다. 공개 계약은 후자 하나뿐이다 |

### 1.1 실측된 피해

**미추적** — 임의 markdown을 `plan_docs/04-analyze/`로 이동하면 Phase 04 문서가 새로 생기는데
어떤 Phase04 게이트도 트리거되지 않는다. 게이트 우회 경로다.

**채널** — 게이트가 정상 판정하고 사유까지 만들었는데 사용자에게는
`PreToolUse:Write hook error: […]: No stderr output`만 보인다. ChatForYou hook 개발에서 원인 불명
차단으로 세션 여러 번을 소진했고, `sage-hook` 직접 호출은 stdout을 그대로 보여주므로 재현되지 않아
오진을 유발했다.

**형태 분기** — `plan_reads`를 선언하지 않은 project core가 `snapshot["files"]`를 읽으면 KeyError가
나고, 이는 catch-all에 걸려 `internal dispatch failure`로 표시된다. 저작자가 고칠 수 있는 오류를
SAGE 내부 버그로 안내한다 — 10-i에서 `ProfileLoadError`를 두고 고친 것과 같은 종류의 오분류다.

### 1.2 실제 범위는 정본 기술보다 넓다

착수 전 호출부 추적에서 두 가지가 추가로 확인됐다. 설계는 이 범위를 반영한다.

- `io.extract_phase4_changes`의 호출부는 둘이다 — `hook_runtime.py:601`(CORE
  `pre-phase4-checklist-gate`)과 `:756`(**등록된 project hook 전체의 `event.changes`**).
  이동 미추적은 CORE 게이트와 모든 project hook에 동시에 적용된다.
- claude의 stdout BLOCK은 `render_gate` 하나가 아니라 `render_phase4`, `render_stop_result`까지
  세 곳이다. 한 곳만 고치면 나머지 두 게이트의 차단 사유는 계속 사라진다.

`plan_reads` 자체가 optional인 것은 결함이 아니라 10-i가 확정한 계약이다(§6.3). 결함은 optional일 때의
**반환 형태**가 계약과 다르다는 것뿐이다.

## 2. Goal

- codex `apply_patch`의 파일 이동으로 생성되는 Phase 04 문서가 CORE 게이트와 project hook 모두에서
  다른 생성 경로와 동일하게 취급된다.
- 두 런타임에서 BLOCK 사유가 host가 실제로 읽는 채널로 전달된다. 판정·문구·exit code는 바뀌지 않는다.
- project hook의 `snapshot`이 `plan_reads` 선언 여부와 무관하게 단일 형태를 갖고, `plan_reads` 반환
  계약 위반은 `internal dispatch failure`가 아니라 저작자 대상 계약 오류로 차단된다.

## 3. Non-Goals

- 결속 판정, 위험도 계산, 선언 통로 — 10-j의 다른 사이클이 소유한다.
- `*** Delete File:`의 Phase04 트리거. 04 문서 삭제는 체크리스트 증거를 요구할 대상이 아니다.
- 게이트 문구(`messages` 모듈) 변경. 이번 범위는 채널이지 문구가 아니다.
- claude 쪽 이동 추적. claude는 Write/Edit/MultiEdit만 dispatch하므로 이동 연산 자체가 없다.
  런타임 간 추출기 차이는 host 입력 형식 차이이며 정당하다.
- project hook decision 메시지의 exit 0 채널 정책 변경(§5.2 경계 참조).
- `plan_reads`를 필수로 만드는 계약 변경.

## 4. Global Invariants

### G1. 판정 불변, 채널만 이동

BLOCK 채널 수정은 `decision["status"]`, `decision["exit_code"]`, `messages.*`가 만든 문자열을
바꾸지 않는다. 같은 입력에 대해 stdout+stderr를 합친 텍스트와 exit code가 수정 전과 같아야 한다.
바뀌는 것은 그 텍스트가 어느 스트림에 있느냐뿐이다.

### G2. 런타임 간 채널 대칭

같은 hook, 같은 status에 대해 두 런타임의 채널 선택 규칙이 같다.

```text
status == block   →  host가 차단 사유로 읽는 채널   (claude: stderr / codex: stderr | decision JSON)
status != block   →  host가 컨텍스트로 읽는 채널     (claude: stdout / codex: hookSpecificOutput JSON)
```

런타임별 wire 포맷은 다르지만 **어느 status가 어느 역할의 채널로 가는가**는 동일하다.

### G3. 추출기 간 연산 집합 정합

한 런타임 안에서 같은 host 입력을 읽는 추출기들은 같은 파일 연산을 인식한다. 특정 추출기가
연산을 의도적으로 제외한다면 그 이유가 코드에 남고 회귀가 그 결정을 고정한다.

### G4. snapshot 단일 형태

`_project_snapshot`의 반환은 언제나 `{"glob_results": dict, "files": dict}`다. 빈 경우는 빈 dict를
담은 이 형태이지 `{}`가 아니다.

## 5. Architecture

### 5.1 codex Phase04 추출기의 이동 수집

`extract_phase4_changes`가 `*** Move to:` 목적지를 `op: "move"` 변경으로 추가한다. codex apply_patch에서
이동은 `*** Update File: <old>` 다음 `*** Move to: <new>`로 표현되므로 결과는 원본 `update`와 목적지
`move` 두 건이다. 이는 `extract_changes`·`extract_logged_changes`가 이미 쓰는 표현과 같다.

Phase04 게이트 core와 project core는 `changes[*].path`로 phase 소속을 판정하므로 목적지 경로가
목록에 들어오는 것만으로 트리거가 복원된다. core 로직은 바꾸지 않는다.

`Delete File:` 제외는 유지하고 그 판단을 코드에 남긴다.

### 5.2 claude BLOCK 채널

`io_claude`의 세 렌더러가 BLOCK 문구를 stderr로 보낸다.

| 함수 | 현재 | 변경 후 |
|---|---|---|
| `render_gate` | 전 status stdout | block → stderr, 그 외 stdout |
| `render_phase4` | 전 status stdout | block → stderr, 그 외 stdout |
| `render_stop_result` | 저장 알림·`block_reason` 모두 stdout, exit 2 | `block_reason` → stderr, 저장 알림은 stdout 유지 |

`render_stop_result`는 Stop hook이라 PreToolUse와 wire가 다르지만 exit 2 시 stderr를 사유로 읽는
성질은 같다. 저장 알림은 차단 사유가 아니므로 stdout에 남긴다.

#### 경계 — 비차단 메시지의 claude 가시성은 별개 문제다 (→ EH-12)

이번 범위는 **차단 사유가 host 에 닿는가**이다. 통과 메시지가 닿는가는 별개이며 여기서 닫지 않는다.

Claude Code 는 exit 0 hook 의 평문 stdout 을 디버그 로그에만 쓴다. 컨텍스트로 올라가는 이벤트는
`UserPromptSubmit`·`UserPromptExpansion`·`SessionStart` 뿐이고 PreToolUse 는 아니다. 따라서
`render_gate`·`render_phase4` 의 OK/WARN 은 claude 에서 사용자·모델 어느 쪽에도 닿지 않는다 —
codex 는 같은 상황에서 `hookSpecificOutput.additionalContext` 를 쓰므로 보인다.

이는 이번 변경이 만든 회귀가 아니라 기존 성질이고, 고치려면 claude 비차단 출력을 평문에서 JSON 으로
바꿔야 해서 출력 프로토콜 변경이 된다. **OK/WARN 을 stdout 에 남긴 판단은 유효하다** — stderr 는 차단
사유 채널이므로 비차단 출력을 섞으면 진짜 사유가 묻힌다. 옮길 곳은 stderr 가 아니라 JSON 이다.

#### 경계 — project hook decision 메시지는 이번에 바꾸지 않는다

`run_project_hook`(`hook_runtime.py:761`)은 status와 무관하게 decision 메시지를 stderr로 낸다.
BLOCK은 올바른 채널이지만 OK/WARN은 claude에서 컨텍스트로 올라가지 않는다. 이는 런타임 중립 코드에
있어 두 host의 wire 포맷 분기를 새로 도입해야 하고, 10-i가 확정한 project hook 공개 계약의
관측 가능 동작을 바꾼다. **G2가 요구하는 것은 BLOCK 전달이며 그 부분은 이미 만족한다.**
OK/WARN 채널은 별도 항목으로 남긴다.

### 5.3 project snapshot 계약

```text
plan_reads 없음                       {"glob_results": {}, "files": {}}
plan_reads 있음, dict 아님             ProjectHookError
plan_reads 있음, "globs" 키 없음       ProjectHookError
plan_reads 있음, 여분 키               ProjectHookError  (현행 유지)
plan_reads 있음, globs 리스트 아님      ProjectHookError  (현행 유지)
```

현재 `set(reads) - {"globs"}`는 `{}`를 통과시킨다. `"globs"` 키의 **존재**를 요구해 계약 drift가
저작자 대상 `project hook contract failure`로 표면화되게 한다. `ProjectHookError`는 10-i가 만든
분류 분기를 그대로 타므로 새 예외 종류를 추가하지 않는다.

## 6. Failure Matrix and Required Regression Teeth

### 6.1 이동 추적

- codex apply_patch가 `Update File: docs/x.md` + `Move to: plan_docs/04-analyze/y.md`일 때
  Phase04 게이트가 다른 생성 경로와 같은 판정을 낸다.
- 같은 입력에서 등록된 project hook의 `event.changes`에 목적지 경로가 들어온다.
- `Delete File:`은 여전히 Phase04 changes에 들어오지 않는다.
- `extract_changes`·`extract_logged_changes`·`extract_phase4_changes` 세 추출기가 같은
  apply_patch 본문에서 인식하는 경로 집합을 대조한다.

### 6.2 채널

- claude 게이트 BLOCK을 실제 adapter subprocess로 실행해 **stderr가 비어 있지 않고** exit 2인지 단언한다.
- 같은 실행에서 OK/WARN은 stdout에 남고 stderr가 비어 있는지 단언한다.
- Phase04 BLOCK과 Stop block_reason에 같은 단언을 적용한다.
- 두 런타임의 stdout+stderr 합본과 exit code가 수정 전과 동일한지 대조한다(G1).
- codex 기존 채널 동작이 회귀하지 않는지 함께 단언한다.

### 6.3 snapshot

- `plan_reads` 없는 core가 `snapshot["glob_results"]`와 `snapshot["files"]`를 KeyError 없이 읽는다.
- `plan_reads`가 `{}`를 반환하면 `project hook contract failure`로 exit 2이고
  `internal dispatch failure`가 아니다.
- 기존 정상 `plan_reads` 경로의 glob 결과·파일 내용·root 이탈 차단이 그대로다.

### 6.4 Mutation requirements

다음을 되돌리면 최소 한 테스트가 **정확한 사유로** 실패해야 한다.

- `extract_phase4_changes`의 Move 분기 제거
- `io_claude` 세 렌더러 각각의 block 분기 제거(개별로)
- `_project_snapshot`의 부재 시 단일 형태 반환
- `"globs"` 키 존재 요구

rc만 같은 다른 결함으로 우연히 통과하는 테스트는 방어선으로 인정하지 않는다. 채널 테스트는
stdout과 stderr를 **각각** 단언해야 하며 합본만 보는 테스트는 mutation을 죽이지 못한다.

## 7. Acceptance

- codex에서 파일 이동으로 만든 Phase 04 문서가 게이트를 트리거한다.
- claude에서 세 게이트의 BLOCK 사유가 host 차단 메시지로 보인다.
- `plan_reads` 없는 project core가 계약대로 snapshot을 읽고, 잘못된 `plan_reads`는 저작자 대상
  계약 오류로 차단된다.
- 판정·문구·exit code가 수정 전과 동일하다.
- none/Claude/Codex 공식 hook suite, `sage validate --kind all --check --schema`, wheel smoke,
  `git diff --check`, mutation suite가 모두 통과한다.
- L3이므로 Phase 06 전에 독립 리뷰를 받는다. 리뷰는 코드 읽기만이 아니라 실제 adapter subprocess의
  stdout/stderr 분리를 재현해야 한다.

## 8. Verification Commands

```bash
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_pre_implementation_gate.py
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_pre_phase4_checklist_gate.py
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_stop_compliance_report.py
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_project_hook_lifecycle.py
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_hook_runtime.py
bash scripts/sage_harness/hooks/tests/run-all.sh
PYTHONPATH=. python3 -m sage validate --kind all --check --schema
bash scripts/ci/wheel_smoke.sh
git diff --check
```

## 9. Implementation Result (2026-08-03)

착수 전 세 결함을 adapter subprocess로 재현했다. 이동 입력은 rc=0(기준 입력은 rc=2), claude BLOCK은
exit 2인데 stderr가 빈 문자열이었다 — 실측 증상과 같다.

- `extract_phase4_changes`가 Move 목적지를 `op: "move"`로 수집한다. Delete 제외는 유지하고 판단을
  코드에 남겼다. 수정 후 이동 입력이 기준 입력과 같은 판정(미완료 rc=2 / 완료 rc=0)을 낸다.
- claude 세 렌더러가 BLOCK을 stderr로 보낸다. 저장 알림처럼 차단 사유가 아닌 출력은 stdout에 남겼다.
- `_project_snapshot`이 언제나 `{"glob_results": {}, "files": {}}` 형태를 반환하고 `globs` 키 존재를
  요구한다. 위반은 기존 `ProjectHookError` 분기를 타 `project hook contract failure`로 표시된다.

G1은 실측으로 확인했다. HEAD의 runtime 3파일을 임시 트리에 복원해 같은 adapter로 실행하고, 두 런타임
× BLOCK/OK/WARN 6조합에서 exit code와 stdout+stderr 합본이 모두 동일함을 대조했다. 바뀐 것은 스트림뿐이다.

변이 6종(Move 분기, 세 렌더러 block 분기 각각, snapshot 단일 형태, `globs` 키 요구)이 모두 의도한
테스트에서 죽었다. 기존 테스트 16건이 옛 채널을 단언하고 있어 함께 갱신했다 —
`test_claude_block_to_stdout_with_phase_text`는 결함 자체를 계약으로 못박고 있었다.

runtime 3파일 변경으로 `hook_runtime_hash`가, spec 3건 변경으로 `spec_hash`가 STALE이 되어
manifest의 해당 필드만 재스탬프했다. 엔진 루트에서 `sage generate`를 실행하지 않았다.

none/claude/codex 환경 run-all, all-kind validate, wheel smoke, compileall, `git diff --check`가 모두
통과했다.

### Phase 05 독립 리뷰 (2026-08-03)

패킷을 채널·이동추적·snapshot 세 갈래로 나눠 각각 독립 headless 세션에 맡겼다. 셋 다 PASS이며
BLOCKER·MAJOR는 없다. 리뷰어는 코드만 읽지 않고 대상 테스트를 실행했고, 채널 담당은 공식 hook 문서를
직접 조회해 wire 전제를 확인했으며 `io_claude`만 되돌리는 변이로 새 테스트가 정확한 사유로 죽는 것을
재현했다. 리뷰 중 작업 트리가 바뀌지 않았음을 파일 해시 350건으로 대조했다.

수용한 지적 세 건.

- claude PreToolUse의 exit 0 stdout은 컨텍스트로 올라가지 않는다. `additionalContext` 자동 승격은
  `UserPromptSubmit`·`UserPromptExpansion`·`SessionStart` 한정이다. 이를 단언하던 새 주석 두 곳이
  틀렸으므로 고쳤고, 파급은 §5.2 경계와 EH-12로 분리했다.
- Phase04 `event.changes`의 `op` 값 목록이 어디에도 없어 저작자가 `add|update` 하드코딩으로 놀랄 수 있다.
  hook spec과 한영 CLI 레퍼런스에 명시했다.
- `hook_runtime_hash` 계산이 비결정적일 수 있다는 관측은 6회 반복 실행으로 반증했다(전부 동일).

수용하지 않은 지적 하나. 이동추적 리뷰어가 자기 패킷 diff에 섞인 채널 수정을 "범위 밖 변경"으로
지목하고 커밋 분리를 권했다. 패킷을 파일 단위로 잘라 테스트 파일이 겹친 데서 생긴 인상이며, 세 결함은
§1 Delivery Rule대로 한 단위다.

commit은 아직 수행하지 않았다.

## 10. Tracking

- 상위: 로드맵 §10-j · 정본 `SAGE - 장수 브랜치 다중 사이클 결속·선언 risk 설계` J-6 · J-8 · J-9
- repo backlog: `plan_docs/enhancement-backlog.md` EH-11
- 후속 사이클: 선언 risk 포착 정밀도, 결속 검증, 거버넌스 자산 자기 위험도
