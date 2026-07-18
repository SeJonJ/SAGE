# [Expert Review] SAGE-FB-12 framework overlay 게이트 완화 hard-fail

Cycle-Stem: `sage-fb-12-framework-overlay-hard-fail`
Status: APPROVED_WITH_RESIDUAL_RISK

## 1. Review Protocol

- Required: development completion before three independent review rounds.
- Preferred reviewer: Claude headless, no subagents.
- Fallback: Claude error/quota 시 사용자 지시에 따라 매 회 새로운 ephemeral read-only headless session을 사용한다.
- Findings are triaged against reproduction and acceptance criteria before code changes.

## 2. Claude Availability

Claude CLI가 매 시도 `You've hit your session limit - resets 7:30am (Asia/Seoul)`로 종료됐다. Claude review를
완료했다고 주장하지 않으며, 사용자 지정 fallback으로 distinct Codex headless sessions를 사용했다.

## 3. Required Review Rounds

| Round | Session | Accepted findings |
|---|---|---|
| 1 | `019f6c7a-aa7e-7291-a50c-88a584f6575a` | write-guard blocked target 안내, mixed-case noncanonical id |
| 2 | `019f6c81-a481-7aa1-a987-0e03a2baa1f4` | `.MD` bypass, legacy blocked block, scanner wording, reference/guidance drift |
| 3 | `019f6c8d-9273-7340-a969-f3a3f253ef7c` | approval-skip wording, skew-before-cleanup, malformed sibling cleanup, SessionStart exit, authoring/output drift |

All findings were accepted after source-level reproduction and fixed with focused regression tests.

## 4. Closure Reviews

| Session | Verdict | Decision and resolution |
|---|---|---|
| `019f6c9a-e768-7be0-9341-0189c10fe23c` | NOT CLEAN | install cleanup gap, natural wording bypass, doctor order, PDCA inventory accepted and fixed |
| `019f6ca6-7698-7302-8a8d-c73605c5c742` | NOT CLEAN | profile parse/runtime early return before cleanup accepted; cleanup moved ahead of both checks |
| `019f6cac-0102-7191-b7fb-48cac27e3358` | CLEAN | no P0-P2 finding in the final delta |

All fallback sessions were fresh, read-only, non-resumed headless sessions without subagents. Read-only sandbox가
temporary-directory tests를 막은 경우 main writable session에서 동일 focused tests와 full suite를 실행했다.

## 5. Acceptance

| Acceptance ID | Final Status | Evidence |
|---|:---:|---|
| FB12-AC1 | PASS | framework 4종은 oracle 등록 없이는 blocked |
| FB12-AC2 | PASS | relaxation hit는 plans/receipts 없이 preflight hard error |
| FB12-AC3 | PASS | `validate --strict` exits 1 with stable check id |
| FB12-AC4 | PASS | default validate remains advisory WARN |
| FB12-AC5 | PASS | preflight and validate share `overlay_lint.scan_text` |
| FB12-AC6 | PASS | exact legacy blocked blocks clean independently; manifest is not re-stamped on failure |
| FB12-AC7 | PASS | shipped authoring/write-guard guidance matches executable eligibility |
| FB12-AC8 | PASS | three required reviews plus three closure reviews; final CLEAN |

## 6. Verification

- Combined relevant Python suites: 399 passed, 1 optional-dependency skip.
- Install module: 89 passed.
- Generated write guard shell suite: 66 passed.
- `git diff --check`: pass.

## 7. Final Decision

APPROVED_WITH_RESIDUAL_RISK. Gate-bearing framework overlays no longer compose without an independent executable
oracle, and obvious gate-relaxation wording is hard-failed by preflight and strict validation. The text scanner remains
heuristic and is not treated as a semantic oracle; risk is bounded because gate-bearing assets are blocked by eligibility.
Full install transaction ordering and concurrent mutation isolation remain SAGE-FB-15 scope.
