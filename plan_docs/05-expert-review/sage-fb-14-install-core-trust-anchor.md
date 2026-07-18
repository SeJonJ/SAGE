# [Expert Review] SAGE-FB-14 최초 install CORE base 신뢰 앵커 검증

Cycle-Stem: `sage-fb-14-install-core-trust-anchor`
Status: APPROVED_WITH_RESIDUAL_RISK

## 1. Review Protocol

- Required: development completion before three independent clean-context review rounds.
- Preferred reviewer: Claude headless, no subagents.
- Fallback: Claude error/quota 시 사용자 지시에 따라 매 회 새로운 ephemeral read-only headless 세션을 사용한다.
- Findings are not auto-accepted. Reproduction, acceptance contract, regression risk를 검토한 뒤 수용 또는 보류한다.

## 2. Claude Availability

Claude CLI가 `You've hit your session limit - resets 7:30am (Asia/Seoul)`로 종료됐다. Claude review를
완료했다고 주장하지 않으며, 사용자 지정 fallback으로 distinct Codex headless 세션을 사용했다.

## 3. Required Review Rounds

### Round 1

- Session: `019f6c48-be99-7572-af0e-f85e59bd7e04`.
- Findings: ancestor symlink, non-regular target, non-UTF-8/malformed marker test gap, AC4 evidence overclaim.
- Decision: all ACCEPT.
- Resolution: all-mode ancestor symlink block, `lstat` resource checks, exact bytes/hash inventory tests.

### Round 2

- Session: `019f6c4f-741d-71d3-9424-ff115bf307cc`.
- Findings: preflight/materialize snapshot gap, force hard-link truncation, multi-conflict/global-write evidence gap.
- Decision: all ACCEPT.
- Resolution: materialization receipt-to-bundle binding, atomic replace, exact no-write inventory regression.

### Round 3

- Session: `019f6c57-238b-7110-8781-5319f8d79d40`.
- Accepted: shared guide other-host receipt skew, malformed manifest fail-open, materialized mode loss.
- Deferred: same-permission concurrent ancestor replacement and plan/apply mutation.
- Rationale: full prevention requires directory-FD/CAS transaction across install; tracked as FB-15 residual.
- Current mitigation: arbitrary base receipt is blocked and post-snapshot drift mismatches the expected anchor.

## 4. Closure Reviews

| Session | Finding | Decision | Resolution |
|---|---|---|---|
| `019f6c5e-0c54-70a3-804f-7c35e49092f3` | mapping-shaped manifest damage normalized silently | ACCEPT | dependency-free structural fail-closed validation |
| `019f6c64-22ce-7ce2-83a1-385512f4a8c9` | invalid entries/host history/shared receipt recovery gaps | ACCEPT | force sanitization and primary/shared receipt convergence |
| `019f6c69-81f7-7910-b6f7-fb6f8ee5aebc` | shallow validators preserve schema-invalid nested entries | ACCEPT | schema-equivalent asset/receipt validators and tests |
| `019f6c6d-a347-7900-a4a4-445408807a8a` | none | CLEAN | no further change |

All sessions were fresh, read-only, non-resumed headless sessions without subagents. Read-only sandbox가
`TemporaryDirectory` 실행을 막은 closure에서는 pure validator transition을 재현했고, main session의 writable
환경에서 install 85개와 overlay 15개 테스트를 별도로 통과시켰다.

## 5. Acceptance

| Acceptance ID | Final Status | Evidence |
|---|:---:|---|
| FB14-AC1 | PASS | unanchored mismatch exits before project/global write |
| FB14-AC2 | PASS | exact bundled base receives a new receipt |
| FB14-AC3 | PASS | drifted/forged/old anchor cannot be re-blessed non-force |
| FB14-AC4 | PASS | exact sorted inventory includes key/path/reason/hashes/action |
| FB14-AC5 | PASS | blocked paths preserve destination and manifest bytes |
| FB14-AC6 | PASS | force atomically replaces leaf render and records bundle receipt |
| FB14-AC7 | PASS | Claude/Codex/profile render target contracts covered |
| FB14-AC8 | PASS | three required reviews plus four closure reviews, final CLEAN |

## 6. Final Decision

APPROVED_WITH_RESIDUAL_RISK. FB-14의 pre-existing CORE trust-anchor 우회는 차단됐다. 같은 권한의 다른
프로세스가 install 도중 ancestor 또는 snapshot을 교체하는 adversarial concurrency는 FB-15의 전체
preflight/transaction 범위에서 해결한다. 이 잔여 위험은 현재 완료 기준을 위반하지 않는다.

