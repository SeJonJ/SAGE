# [Analyze] SAGE-FB-08 서버측 PR-diff 권위 게이트와 attestation

Cycle-Stem: `sage-fb-08-server-authority-attestation`
Status: ANALYZED_REVIEW_COMPLETE

## 1. Design to Implementation Gap

| Design Item | Implementation | Gap |
|---|---|---|
| pure deterministic API | `analyze` + `evaluate`, no subprocess/filesystem/environment | none |
| base/head full blob classification | adapter materializes both trees; modify/delete/rename old content included | non-blob changed objects block instead of content-inspection fallback |
| max(base policy, head policy) | both profiles schema-validated and independently classified | none |
| exact Phase 00~05 | basename + declaration exact selector on regular head-tree files, base/head glob union | none |
| L3 acceptance/review | required acceptance PASS or reasoned N/A; exact APPROVED Phase 05 | local waiver deliberately ignored |
| attestation anti-forgery | protected issuer의 canonical compact HMAC token, exact claims, one-hour max TTL | same-job verification은 독립 제3자 승인 또는 nonce replay store가 아님 |
| protected workflow | inactive pull_request_target example with read-only permission and SHA placeholders | active pin/source/ruleset deferred to FB-09 |
| no head execution | only protected engine and git object plumbing commands execute | tests prove malicious head Python is not run |

## 2. Acceptance Evidence

| ID | Status | Evidence |
|---|:---:|---|
| FB08-AC1 | PASS | real-git delete and R100 rename tests bind base/head full blobs and both paths |
| FB08-AC2 | PASS | base L3/head L1 fixture remains authoritative L3 |
| FB08-AC3 | PASS | pure request ignores injected local override/waiver and unresolved acceptance still blocks |
| FB08-AC4 | PASS | signed claims cover issuer/repository/base/head/diff/cycle/risk/reviewer/verdict/nonce/time |
| FB08-AC5 | PASS | signature tamper, expected binding mismatch, expiry, short/missing secret, symlink token block |
| FB08-AC6 | PASS | missing exact phase, custom unresolved status, failed Phase 05 block; full set passes |
| FB08-AC7 | PASS | malicious head module fixture leaves execution marker absent; adapter uses no shell/import |
| FB08-AC8 | PASS | inactive installed example uses pull_request_target, contents:read, protected secret, pin placeholders |
| FB08-AC9 | PASS | Three fresh Claude rounds plus closure review completed with findings triaged. |

## 3. Self-found Findings and Resolution

| Finding | Resolution |
|---|---|
| incomplete phase set prevented existing L3 declaration from escalating risk | parse declarations from every exact selected phase before applying L2/L3 phase errors |
| authority called nonexistent `_review_final_status` helper | use canonical core `_final_status`; L3 path regression executes it |
| modify inspected only head content | add base-version classification so removed L3 keyword cannot bypass |
| normal CLI schema fallback could be WARN-only | authority explicitly requires `jsonschema` and workflow installs schema extra |
| malformed pure structured diff could be signed | enforce operation, canonical path, object-id, and per-operation base/head semantics |
| Git symlink Phase 05 was accepted because `ls-tree` also labels mode `120000` as blob | require mode `100644`/`100755` for profile and Phase evidence; real-Git symlink regression added |

## 4. Residual Boundary

HMAC secret custody, action/SAGE SHA selection, protected environment access, required-check expected source, and branch
protection are external deployment controls. The example stays non-active until FB-09 supplies and proves them. A fork without
the protected secret is intentionally blocked, not downgraded. The current example issues and verifies inside one protected job:
the signature proves protected-key issuance and exact claim integrity, not independent third-party approval. `nonce` is a signed
issuance correlation value; without an external consumed-nonce store it is not replay prevention. Replay remains bounded to the
same repository/base/head/diff/cycle/risk tuple and one-hour TTL. Phase 00~05 files are PR-authored structural evidence; this
gate validates their exact form and consistency but does not authenticate which external model or person produced Phase 05.
A separately protected reviewer issuer and identity claim are a follow-up architecture item, not supplied by FB-09 branch
protection alone. The three independent Claude review rounds are complete.

## 5. Broad External Review Round 1 Triage

Claude session `7103906f-8bd3-484c-bb8c-937e92496f5a`의 branch-derived stem P2는 기각했다. FB01/11의 accepted
design이 non-phase write에서 exact branch final segment fallback을 명시하며, 과거 결함인 숫자 token membership은
사용하지 않는다. Self-issued attestation과 nonce 지적은 권한 상승 결함은 아니지만 과대 해석 가능성이 있어
Residual Boundary와 implementation 설명을 보강했다.

## 6. Broad External Review Round 2 Triage

Claude session `637f2d5c-1597-4b9a-a373-8e0b6bc1ebe1`이 protected authority와 local gate의 risk declaration
parser drift를 재현했다. 강조된 canonical 선언이 BLOCK되고 `Risk Level 결정: L3`는 누락되는 비대칭이므로
타당한 P1/P2로 수용했다. 정본 parser helper를 core에 두어 양 경로가 공유하고, unknown declaration은 삭제하거나
즉시 영구 BLOCK하지 않고 L3 수준의 Phase 05/acceptance 증거를 요구하도록 통일했다.

## 7. Broad External Review Round 3 Triage

Claude session `a01c9b7a-ee27-483b-9650-bd836aa264ca`의 self-approval P2는 현재 pure diff authority를 우회하는
코드 결함은 아니지만, SD-9의 reviewer issuer 미해결 항목을 실제로 드러낸 아키텍처 한계다. PR author가 Phase 05
문서를 공급한다는 사실과 별도 protected reviewer attestation 필요성을 Residual Boundary와 운영 문서에 명시했다.
GitHub approval을 즉시 reviewer로 간주하는 제안은 SAGE의 cross-model review 계약과 동등하지 않아 자동 구현하지
않았다. Generic module loader P3는 현재 collision이 없어 후속 hardening으로 분리한다.

## 8. External Review Closure

Fresh closure session `ead09722-14af-4538-b8b0-155761c95973` marked FB08 CLEAN. It also noted that an
absent local risk declaration and authority classification may produce different provenance: local handling escalates
an unknown declaration to L3, while authority classifies the protected base/head diff directly and only uses a
declaration to escalate. This is an intentional trust-model difference, not a downgrade, because authority never lowers
the diff-derived risk. Protected reviewer identity remains a separate follow-up beyond PR-authored structural evidence.
