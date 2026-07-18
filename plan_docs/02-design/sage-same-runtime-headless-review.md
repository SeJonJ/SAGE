# [Design] Phase 05 same-runtime headless 리뷰 결정론 실행

Cycle-Stem: `sage-same-runtime-headless-review`

## 1. Policy Resolution

```text
required
  local false -> BLOCKED
  peer available -> cross-model
  peer unavailable/invocation failure -> BLOCKED
recommended
  local true/default -> cross-model when available, failure is degraded/BLOCKED by strict caller
  local false -> active-host same-runtime headless
off
  -> active-host same-runtime headless
legacy(no policy)
  -> existing options.cross_model boolean behavior
```

## 2. Active Host

동시에 두 host가 active인 상태는 만들지 않는다. `sage review --host claude|codex`를 명시적 정본으로 사용하고,
CORE skill은 자신이 실행 중인 runtime 값을 전달한다. 환경에서 확실히 판정 가능한 경우만 기본값으로 허용하고
모호하면 profile의 legacy host를 조용히 신뢰하지 않고 실행 전 오류를 낸다.

## 3. Invocation

기존 `_peer_command`, UTF-8 stdin, timeout, JSON parser를 runtime-neutral headless helper로 일반화한다.
same-runtime은 active host를, cross-model은 opposite host를 넘긴다. model은 host reviewer 설정이 있으면 명시하고
없으면 CLI default를 사용하되 evidence에 `cli-default`로 기록한다.

성공 stdout:

```text
===== CODEX SAME-RUNTIME REVIEW =====
<review body>
===== END CODEX REVIEW =====
REVIEWER_PROCESS: codex exec
REVIEWER_HOST: codex
REVIEWER_MODEL: <id|cli-default>
REVIEWER_ACTUAL: same_runtime
REVIEWER_STATUS: COMPLETE
```

## 4. Tests

- 양 host argv/stdin/parser/timeout
- explicit host 누락·충돌
- required/recommended/off/legacy 결정표
- local false와 peer availability 조합
- instruction-only false success 제거
- output evidence와 nonzero BLOCKED sentinel
