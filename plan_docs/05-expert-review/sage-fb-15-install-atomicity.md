# [Expert Review] SAGE-FB-15 install preflight-first와 실패 원자성

Cycle-Stem: `sage-fb-15-install-atomicity`
Status: APPROVED

## 1. Review Protocol

- Required: implementation completion followed by three independent review rounds.
- Preferred reviewer: Claude headless, no subagents.
- Fallback: Claude error or quota uses a fresh independent read-only headless session, never a subagent.
- Findings are accepted only after concrete failure-order reproduction and contract/regression triage.

## 2. Required Review Rounds

Claude fresh headless attempts were quota-limited and are not counted as review evidence. The user-authorized
fallback used a distinct ephemeral read-only Codex headless session for every required round.

| Round | Session | Result |
|---|---|---|
| 1 | `019f6dcb-c880-7ed3-a79c-4017c341e6b8` | 2 P0 + 4 P1 reproduced, accepted, fixed |
| 2 | `019f6de1-c15a-73b0-a8a2-ef7b7048d25a` | 3 P1 + 1 P2 reproduced, accepted, fixed |
| 3 | `019f6df7-6b78-7160-996c-8128fb365793` | 3 P1 + 4 P2 reproduced, accepted, fixed |

All three sessions were fresh, headless, read-only, non-resumed, and used no subagent.

## 3. Closure Reviews

| Session | Verdict | Resolution |
|---|---|---|
| `019f6e08-a167-7600-9e6b-5fd294f7f7ec` | P2 1건 | falsy YAML non-mapping의 빈 profile 축소를 수용하고 `None`-only 정규화와 regressions 추가 |
| `019f6e12-0bde-7452-a55b-ac37d331be05` | CLEAN | `CLEAN_FOR_FB15_CLOSURE`, P0-P2 none |

Claude closure attempt `c87bf21f-abee-4424-bffc-9602fc7fb0cb`도 HTTP 429로 종료되어 리뷰로 계산하지
않았다. Final closure의 read-only sandbox에서는 filesystem unittest를 시작할 writable temp가 없어 pure
in-memory transition을 검증했고, main writable session에서 focused 153건과 full 1,200건을 통과시켰다.

## 4. Acceptance

| Acceptance ID | Final Status | Evidence |
|---|:---:|---|
| FB15-AC1 | PASS | overlay/domain/profile/manifest/CORE trust preflight precedes general install mutation |
| FB15-AC2 | PASS | first-install preflight and injected failures restore an empty destination |
| FB15-AC3 | PASS | reinstall failures restore existing bytes/type/mode/manifest and remove owned new paths |
| FB15-AC4 | PASS | force failures restore replaced CORE objects and journaled legacy prune |
| FB15-AC5 | PASS | Codex global CORE skill changes share project rollback transaction |
| FB15-AC6 | PASS | canonical path/inode destination lock and contention regressions |
| FB15-AC7 | PASS | input/output/source/ancestor drift is detected before logical commit |
| FB15-AC8 | PASS | first/reinstall/force, both hosts, anchors, modes, symlink/hard-link regressions green |
| FB15-AC9 | PASS | exact FB-12 blocked-block cleanup preserves base and manifest |
| FB15-AC10 | PASS | three required rounds, finding triage, and final clean closure completed |

## 5. Verification

- Focused install/transaction/overlay suite: 153 passed.
- Full Python suite: 1,200 passed, 1 skipped.
- Official hook suite: `ALL HOOK TESTS PASS` under Homebrew Python with schema dependencies.
- `git diff --check`: PASS before Phase 05 authoring; final document check is required before report closure.

## 6. Residual Risk

- The in-memory journal does not provide recovery after SIGKILL, `os._exit`, kernel failure, or power loss.
- Same-permission non-cooperative processes can still race after a local check; SAGE locks serialize cooperative
  installers, while post-install validation and FB-08 attestation own broader authority.
- The default PATH Python 3.11 lacks `jsonschema`; official validation uses the Homebrew implementation environment
  or requires the schema extra.

## 7. Final Decision

FB15-AC1 through FB15-AC10 are satisfied. Install preflight, failure rollback, force/global mutation, and cooperative
concurrency boundaries are implemented with explicit residual limits and a final independent clean closure.

Final Status: APPROVED
