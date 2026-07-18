# [Implementation] SAGE-FB-08 서버측 PR-diff 권위 게이트와 attestation

Cycle-Stem: `sage-fb-08-server-authority-attestation`
Risk Level: L3
Status: IMPLEMENTED_REVIEW_COMPLETE

## 1. Delivered Files

| Area | File | Implementation |
|---|---|---|
| pure authority | `sage/ci_authority.py` | structured diff digest, base/head max-risk, exact Phase evidence, canonical acceptance, HMAC attestation |
| git adapter | `sage/commands/authority.py` | full-SHA `git diff/ls-tree/cat-file`, profile schema enforcement, inspect/attest/gate |
| CLI | `sage/cli.py` | `sage authority` command registration |
| operator docs | `docs/sage_harness/ci/server-authority.md` | trust boundary, commands, activation requirements |
| inactive workflow | `templates/core/framework/docs/agent/sage-authoritative-gate.yml.example` | pull_request_target, read-only permission, pinned-ref placeholders, secret-required gate |
| regression | `scripts/sage_harness/hooks/tests/test_ci_authority.py` | pure core, real Git object adapter, tamper/expiry/secret, rename/delete/non-execution |
| official suite | `scripts/sage_harness/hooks/tests/run-all.sh` | install transaction and CI authority suites registered |

## 2. Security Controls

- base와 head profile을 현재 protected engine schema로 각각 검증하고 두 분류 결과의 최고 위험도를 사용한다.
- add/modify/delete/rename마다 실제 base/head blob 존재와 canonical path를 검증한다.
- modify의 제거 content, delete의 base content, rename source와 destination을 모두 classifier input으로 확장한다.
- exact `Cycle-Stem` Phase 00~05를 head tree에서 고르고 L3는 canonical acceptance와 Phase 05 APPROVED를 요구한다.
- profile과 Phase 00~05 증거는 Git symlink(`120000`)가 아닌 정규 파일 mode(`100644`/`100755`)만 허용한다.
- pure API와 CLI request에는 local override/acceptance-waiver audit을 포함하지 않는다.
- attestation은 canonical JSON과 HMAC-SHA256을 사용하고 full SHA/diff/cycle/risk/verdict/nonce/TTL을 결속한다.
- HMAC은 protected CI key holder가 exact 판정 claims를 발행했다는 무결성 증거다. 현재 inactive example의
  same-job issue/verify는 독립 제3자 승인이나 nonce-consumption 기반 replay 방지로 주장하지 않는다.
- CLI는 head code를 import/source/execute하지 않고 git object data만 읽는다.
- authority mode는 `jsonschema` 부재를 WARN으로 낮추지 않고 BLOCK한다.

## 3. Verification

- authority focused: 17 passed.
- install + transaction + resources: passed.
- official `run-all.sh`: `ALL HOOK TESTS PASS` (authority 15 + transaction 20 포함).
- full discovery: 1,250 passed, 1 skipped.
- Python compile and scoped `git diff --check`: PASS.

## 4. Pending

- AC9 three fresh independent Claude headless review rounds and finding triage.
- protected SAGE revision publish, active ChatForYou workflow, required-check expected source, branch protection/ruleset proof는 FB-09.

## 5. Component Impact

- SAGE engine: authority API, CLI, docs, workflow example, tests added.
- ChatForYou Backend: N/A, application source unchanged.
- ChatForYou Frontend: N/A, application source unchanged.
- ChatForYou Desktop: N/A, application source unchanged.

## 6. Broad External Review Round 1

- Reviewer: Claude headless session `7103906f-8bd3-484c-bb8c-937e92496f5a`.
- 기각(P2): `HEAD_REF`의 final segment를 exact cycle stem으로 쓰는 것은 branch 숫자를 분해하지 않으며,
  FB01/11 design의 non-phase fallback 계약과 일치한다. Phase 문서가 같은 exact stem을 선언하지 않으면 BLOCK한다.
- 문서 보강: same protected job의 HMAC issue/verify는 protected issuer 증명이지 독립 reviewer 승인이 아니다.
  Nonce는 서명된 issuance correlation 값이며 현재 consumed-nonce 저장소에 의한 replay 방지를 제공하지 않는다.

## 7. Broad External Review Round 2

- Reviewer: Claude headless session `637f2d5c-1597-4b9a-a373-8e0b6bc1ebe1`.
- 수용(P1/P2): authority가 local gate의 risk declaration parser를 재구현해 Markdown 강조는 false BLOCK,
  prose/non-canonical risk-like line은 false BLOCK 또는 silent omission을 만들었다.
- 수정: gate core에 단일 `_parse_risk_declaration`을 두고 local cycle risk와 authority가 공유한다. Risk-like
  malformed/unsupported 선언은 `unknown`으로 통일하며 authority는 이를 L3 evidence 요구로 보수 승격한다.
  Emphasis/prose/non-canonical/L0 parity regressions와 authority/local gate `125 tests`가 PASS했다.

## 8. Broad External Review Round 3

- Reviewer: Claude headless session `a01c9b7a-ee27-483b-9650-bd836aa264ca`.
- 아키텍처 후속(P2): Phase 05는 head tree의 PR-authored structural evidence이므로 protected gate가 문서 형식과
  판정을 검증해도 실제 cross-model reviewer identity까지 인증하지 않는다. 별도 protected reviewer issuer가
  필요한 범위이며 현재 diff authority implementation에 임의로 결합하지 않았다.
- 문서 수정: server authority trust model과 residual boundary에 self-supplied evidence 한계를 명시했다.
- 보류(P3): trusted module import의 global `sys.path` mutation은 현재 collision 재현이 없고 resource packaging
  변경 범위가 커서 후속 loader hardening으로 분리한다.
