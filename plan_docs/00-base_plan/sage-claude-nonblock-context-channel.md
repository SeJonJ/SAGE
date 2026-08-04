# [Base Plan] SAGE EH-12 claude 비차단 게이트 메시지의 컨텍스트 채널

Cycle-Stem: `sage-claude-nonblock-context-channel`
Risk Level: L2
Status: IMPLEMENTED (2026-08-04, 미커밋 · 독립 리뷰 PASS)

## 1. Context

§10-j-1(hook 런타임 IO 계약 정합)의 Phase 05 독립 리뷰에서 나왔다. 그 사이클은 **차단 사유**가
claude 에서 stdout 으로 나가 유실되던 것을 stderr 로 옮겨 닫았는데, 같은 확인 과정에서 **반대
방향의 비대칭**이 드러났다.

Claude Code 는 exit 0 hook 의 평문 stdout 을 디버그 로그에만 쓴다. 컨텍스트로 승격되는 이벤트는
`UserPromptSubmit`·`UserPromptExpansion`·`SessionStart` 셋뿐이고 **PreToolUse 는 아니다**(공식 문서
확인). 따라서 `io_claude` 의 비차단 렌더 출력은 사용자에게도 모델에게도 닿지 않는다.

codex 는 같은 상황에서 `hookSpecificOutput.additionalContext` 를 쓰므로 보인다. PreToolUse 도
`additionalContext` 를 지원하며 `permissionDecision` 없이 단독 반환이 가능하다 — 즉 이것은 host
제약이 아니라 **SAGE 가 지원되는 통로를 쓰지 않고 있는 것**이다.

### 1.1 왜 지금인가

§10-j 의 **J-2(OK 줄에 판정 stem 과 출처를 항상 표기)가 이 위에 선다.** J-2 의 목적은 "낡은 선언으로
조용히 통과하는 상태가 보이게" 하는 것인데, claude 에서 OK 줄이 애초에 보이지 않으면 그 기능은
아무 효과가 없다. 결속 본체 사이클(10-j-3)을 시작하기 전에 닫아야 한다.

### 1.2 현재 상태

| 렌더러 | 이벤트 | 차단 | 비차단 |
|---|---|---|---|
| `render_gate` | PreToolUse | stderr ✅ | **평문 stdout — 미도달** |
| `render_phase4` | PreToolUse | stderr ✅ | **평문 stdout — 미도달** |
| `render_stop_result` | Stop | stderr ✅ | 평문 stdout — 미도달(§3 경계) |
| `render_declared_capture` | UserPromptSubmit | — | 평문 stdout ✅ 그대로 컨텍스트 |
| `render_declared_ambiguous` | UserPromptSubmit | — | 평문 stdout ✅ 그대로 컨텍스트 |
| `render_declared_clear` | UserPromptSubmit | — | 평문 stdout ✅ 그대로 컨텍스트 |

차단 경로와 `UserPromptSubmit` 계열은 이미 올바르다. 바꿀 것은 PreToolUse 비차단 둘이다.

## 2. Goal

- claude 에서 PreToolUse 게이트의 OK/WARN 메시지가 모델이 읽는 컨텍스트에 도달한다.
- 판정·문구·exit code 는 바뀌지 않는다. 바뀌는 것은 전달 형식뿐이다.
- 두 런타임의 비차단 채널이 같은 역할(host 가 컨텍스트로 읽는 통로)을 쓴다.

## 3. Non-Goals

- **차단 채널 변경 없음.** §10-j-1 에서 이미 stderr 로 닫았다.
- **문구 변경 없음.** `messages` 모듈이 문구 SSOT 이며 이번 범위가 아니다. claude 표기(이모지,
  `\n  → ` 힌트 구분자)도 그대로 둔다.
- `UserPromptSubmit` 계열 렌더러(`render_declared_*`). 그 이벤트는 평문 stdout 이 그대로
  컨텍스트가 되므로 현재 구현으로 이미 도달한다. `additionalContext` 도 지원되지만 도달 문제가
  없는 곳을 바꾸는 것은 이 사이클의 목적이 아니다.
- codex 렌더러. 이미 `hookSpecificOutput` 을 쓴다.
- `permissionDecision` 도입. 게이트 판정을 host 권한 흐름에 위임하는 것은 별개 설계이며,
  SAGE 는 exit code 로 판정을 표현하는 기존 계약을 유지한다.
- **`render_stop_result`(Stop).** 아래 경계 참조.

### 경계 — Stop 은 이번에 바꾸지 않는다

Stop 도 `additionalContext` 를 지원한다는 문서 서술이 있으나 이번 범위에서 제외한다.

- 전달 대상이 "리포트가 어디 저장됐다"는 **정보성 한 줄**이라 가치가 낮다.
- Stop 은 wire 가 PreToolUse 와 다르고 codex 쪽은 같은 필드를 **거부**한다(`io_codex`
  `render_stop_result` 주석: Stop 은 `additionalContext` 를 허용하지 않아 단독·결합 모두 hook
  failure). 런타임별로 반대인 계약이라 확인 비용이 높다.
- 잘못 내보내면 **모든 세션 종료마다** hook failure 가 보인다. 얻는 것에 비해 실패 비용이 크다.
- 차단 사유는 이미 stderr 로 나가므로 안전에 영향이 없다.

## 4. Global Invariants

### G1. 판정 불변

`decision["status"]`, `decision["exit_code"]`, `messages.gate_text()`가 만든 문자열이 바뀌지 않는다.
같은 입력에 대해 exit code 가 같고, 전달되는 **메시지 텍스트**가 같아야 한다. 바뀌는 것은 그
텍스트를 감싸는 형식뿐이다.

### G2. 차단 경로 불변

`status == "block"` 이면 여전히 stderr 평문이고 JSON 을 내보내지 않는다. exit 2 에서 host 는 stdout
을 무시하므로 JSON 을 얹으면 무의미하고, 형식 오류 시 진단만 흐려진다.

### G3. 이벤트별 채널 정확성

렌더러가 쓰는 채널은 그 hook 의 **바인딩된 이벤트**가 실제로 읽는 채널이어야 한다. 이벤트마다
평문 stdout 의 취급이 다르다 — `UserPromptSubmit`·`UserPromptExpansion`·`SessionStart` 는 평문이
그대로 컨텍스트가 되고, 그 밖의 이벤트는 디버그 로그로만 간다.

### G4. 무출력 시 무출력

렌더할 메시지가 없으면(`gate_text` 가 빈 문자열) 아무것도 출력하지 않는다. 빈 `additionalContext` 를
가진 JSON 봉투를 내보내지 않는다.

## 5. Architecture

### 5.1 비차단 렌더

```text
status == block        stderr 평문                       (현행 유지)
status != block, m     stdout JSON hookSpecificOutput    (변경)
m 없음                 무출력                             (현행 유지)
```

JSON 형태는 codex 와 같은 구조를 쓰되 `hookEventName` 은 claude 의 바인딩 이벤트다.

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "<gate_text>"}}
```

`additionalContext` 값은 `messages.gate_text(decision, profile, "claude")`가 만든 문자열 **그대로**다.
runtime 인자를 codex 로 바꾸지 않는다 — 문구 표기는 런타임 소유이고 이번 범위가 아니다.

### 5.2 공통 헬퍼

`io_claude` 에 봉투를 만드는 사적 헬퍼 하나를 둔다. 두 렌더러가 같은 형태를 쓰고, 이후 이벤트가
늘어도 형태가 갈라지지 않는다.

```python
def _context_json(text):
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "additionalContext": text}}, ensure_ascii=False)
```

`ensure_ascii=False` 는 codex 쪽과 동일하다 — 한글 메시지가 이스케이프되면 사람이 디버그 로그에서
읽을 수 없다.

## 6. Failure Matrix and Required Regression Teeth

### 6.1 채널

- claude 게이트 OK/WARN 을 실제 adapter subprocess 로 실행해 stdout 이 **유효 JSON** 이고
  `hookSpecificOutput.additionalContext` 에 게이트 문구가 담기는지 단언한다.
- 같은 실행에서 stderr 가 비어 있고 exit code 가 0 인지 단언한다.
- BLOCK 은 여전히 stderr 평문이고 stdout 이 비어 있는지 단언한다(회귀 보존).
- `pre-implementation-gate` 와 `pre-phase4-checklist-gate` 양쪽에 같은 단언을 적용한다.
- 메시지가 없는 경우 stdout 이 완전히 비어 있는지 단언한다.

### 6.2 동등성

- 전달되는 텍스트가 변경 전 stdout 평문과 **동일**한지 대조한다(G1). JSON 을 파싱해 얻은
  `additionalContext` 가 이전 평문과 같아야 한다.
- codex 동작이 회귀하지 않는지 함께 단언한다.
- `UserPromptSubmit` 계열 렌더러가 평문을 유지하는지 단언한다 — 이벤트를 구분하지 않고 일괄
  변환하는 것은 이 사이클의 범위 밖 동작 변경이다.

### 6.3 Mutation requirements

되돌리면 최소 한 테스트가 **정확한 사유로** 실패해야 한다.

- `render_gate` 의 JSON 봉투
- `render_phase4` 의 JSON 봉투
- BLOCK 분기(JSON 으로 잘못 통합)
- `UserPromptSubmit` 렌더러를 JSON 으로 바꾸는 변이
- 빈 메시지에 봉투를 씌우는 변이

## 7. Acceptance

- claude 에서 게이트 OK/WARN 이 `additionalContext` 로 전달된다.
- 전달 텍스트가 변경 전과 동일하다.
- BLOCK 경로와 `UserPromptSubmit` 계열이 불변이다.
- codex 동작이 불변이다.
- none/Claude/Codex 공식 hook suite, `sage validate --kind all --check --schema`, wheel smoke,
  `git diff --check` 가 모두 통과한다.
- L2 이므로 독립 리뷰는 필수가 아니나, host wire 계약을 다루므로 1회 받는다.

## 8. Verification Commands

```bash
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_hook_runtime.py
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_pre_implementation_gate.py
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_pre_phase4_checklist_gate.py
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_capture_declared_risk.py
PYTHONPATH=. python3 scripts/sage_harness/hooks/tests/test_messages.py
bash scripts/sage_harness/hooks/tests/run-all.sh
PYTHONPATH=. python3 -m sage validate --kind all --check --schema
bash scripts/ci/wheel_smoke.sh
git diff --check
```

## 9. Implementation Result (2026-08-04)

`io_claude` 의 PreToolUse 비차단 렌더 둘을 `hookSpecificOutput.additionalContext` 로 바꿨다.
차단(stderr 평문)·`UserPromptSubmit` 계열(평문 stdout)·무출력은 그대로다.

G1 은 HEAD 대비 실측했다. HEAD 의 `io_claude` 를 임시 로드해 6케이스(OK 2·WARN 2·BLOCK·무메시지)를
대조했고, JSON 을 파싱해 얻은 `additionalContext` 가 이전 평문과 정확히 같으며 exit code 도 동일했다.

**기존 테스트가 채널을 구분하지 못했다.** `assertIn("[GATE", stdout)` 과
`assertNotEqual(stdout.strip(), "")` 은 평문이든 JSON 이든 통과한다 — 변경 후 전부 그린이라
오히려 신호였다. `json.loads` 로 봉투를 파싱하고 `hookEventName` 까지 확인하는 단언으로 바꿨다.

변이 6종(봉투 제거 2, BLOCK 통합, `UserPromptSubmit` 오변환, 빈 봉투, `hookEventName` 오기입)이
모두 의도한 테스트에서 죽었다.

### 독립 리뷰 (PASS · MINOR 1건 수용)

리뷰어가 host wire 전제 둘을 공식 문서로 확인했고, `io_claude` 만 되돌리는 변이로 새 단언이
`JSONDecodeError` 로 정확히 죽는 것을 재현했다.

MINOR 지적은 **내 근거 서술이 틀렸다는 것**이었다 — "`UserPromptSubmit` 을 JSON 으로 바꾸면 봉투
문자열이 노출된다"고 썼는데, 문서를 다시 확인하니 그 이벤트도 유효 JSON 이면 파싱된다. 결론(평문
유지)은 유효하지만 이유가 다르므로 코드 주석과 이 문서의 해당 서술을 정정했다. 실제 이유는
**그 경로에 도달 문제가 없어 이 사이클의 목적 밖**이라는 것이다.

### 검증 방식의 결함을 찾았다

전체 스위트 실행에서 install 계열 테스트가 실패했다. 사유는
`InstallDriftError: SAGE source resources changed during install` 이었고, §10-j-2 에서도 같은
모양이 1회 있었다.

**원인은 제품이 아니라 내 검증 방식이었다.** 변이 스위트와 독립 리뷰어(`git stash`)가
`scripts/sage_harness/hooks/**` 파일을 제자리에서 고쳤다 되돌리는데, 그 경로는
`build_identity._inventory()` 의 `hooks` 루트다. 전체 스위트를 그것들과 **동시에** 돌렸으니
install 이 설치 도중 엔진 소스가 바뀐 것을 정당하게 잡은 것이다 — 검사는 설계대로 동작했다.

배제에 시간을 쓴 이유는 진단이 "소스가 바뀌었다"까지만 말하고 **어느 파일인지** 알려주지 않기
때문이다. 그 진단 개선을 **EH-13** 으로 등록했다(검사 완화가 아니라 정보량만). 부수로
`test_doctor` 에 `install.run()` rc 단언을 추가했다(`test_install` 에는 이전 사이클에서 추가) —
없으면 실패가 `FileNotFoundError` 로만 나타나 사유가 가려진다.

운영 규칙으로 남긴다: **변이·리뷰를 전체 스위트와 동시에 실행하지 않는다.**

## 10. Tracking

- repo backlog: `plan_docs/enhancement-backlog.md` EH-12
- 상위: 로드맵 §10-j · 정본 `SAGE - 장수 브랜치 다중 사이클 결속·선언 risk 설계` J-2 선행
- 선행 사이클: `sage-hook-runtime-io-contract`(차단 채널, `v0.9.78`)
