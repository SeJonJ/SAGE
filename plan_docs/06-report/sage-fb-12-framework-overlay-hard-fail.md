# [Report] SAGE-FB-12 framework overlay 게이트 완화 hard-fail

Cycle-Stem: `sage-fb-12-framework-overlay-hard-fail`
Source-05: `plan_docs/05-expert-review/sage-fb-12-framework-overlay-hard-fail.md`
Status: COMPLETE

## 1. Completion Summary

독립 executable oracle이 없는 framework 및 gate-bearing CORE overlay를 fail-closed로 차단했다. Eligible
implementer overlay의 gate-relaxation 탐지는 합성 전 preflight에서 hard error이며, 같은 stable scanner
결과가 `sage validate --strict`에서 FAIL/exit 1로 승격된다.

## 2. Delivered Controls

| Control | Result |
|---|---|
| composition eligibility | non-gate/oracle-backed allowlist 외 CORE 자산 blocked |
| framework boundary | AGENT_GUIDE, CLAUDE, CODEX, AGENTS composition disabled |
| preflight | relaxation hit discards eligible plans and receipts before ordinary materialization |
| strict validation | `overlay-gate-relaxation` stable id with pattern details and exit 1 |
| migration cleanup | exact pre-FB12 blocked managed blocks removed before non-force install/sync early exits |
| session boundary | explicit blocked/malformed/relaxation errors return SessionStart exit 2 |
| guidance | authoring, write guard, doctor, absorb, retro aligned to executable eligibility |

## 3. Review and Verification

- Claude CLI attempts: session limit failure; no Claude review is claimed.
- User-authorized fallback: three required distinct read-only Codex headless reviews, no subagents.
- Closure: three additional fresh sessions; final `019f6cac-0102-7191-b7fb-48cac27e3358` CLEAN.
- Combined relevant Python suites: 399 passed, 1 optional-dependency skip.
- Install module: 89 passed.
- Generated write guard shell suite: 66 passed.
- `git diff --check`: pass.

## 4. Acceptance Result

FB12-AC1 through FB12-AC8 are PASS. Default validate remains advisory for heuristic scanner hits, while composition
preflight and strict validation enforce the boundary.

## 5. Residual Risk

자연어 완화 문구 탐지는 휴리스틱이므로 의미론적으로 완전하지 않다. 이 scanner를 독립 oracle로 간주하지
않고 gate-bearing asset 자체를 eligibility 단계에서 차단해 위험을 제한한다. 전체 install transaction 및
동시 변경 격리는 SAGE-FB-15에서 처리한다.

## 6. Final Status

COMPLETE. This cycle changes the SAGE engine only and does not modify ChatForYou application code.
