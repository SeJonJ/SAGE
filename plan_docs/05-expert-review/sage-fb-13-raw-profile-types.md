# [Expert Review] SAGE-FB-13 raw profile 위험 필드 타입 선검증

Cycle-Stem: `sage-fb-13-raw-profile-types`
Status: APPROVED

## 1. Review Protocol

- Required: independent clean-context review 3 rounds before completion.
- Preferred reviewer: Claude headless, no subagents.
- Fallback: Claude CLI session limit/error 시 새 Codex headless 세션을 매 회 생성하며 resume/subagent를 사용하지 않는다.
- Findings are advisory input: acceptance contract와 재현 근거를 검토한 뒤 수용/기각한다.

## 2. Claude Availability

Round 1 시작 전 Claude CLI가 `session limit`(07:30 KST reset)로 종료됐다. 따라서 사용자 지정 fallback을
발동했으며 이후 리뷰는 매 회 `codex exec --ephemeral -s read-only` 새 세션으로 수행한다.

## 3. Round 1

- Reviewer: fresh Codex headless session `019f6c2b-0eb5-7273-a5f0-ccea42c6d8dd`.
- Isolation: read-only, no file edit, no subagent, no session resume.
- Verdict: `CHANGES_REQUIRED`.
- Findings: P0 0 / P1 1 / P2 2.

| Severity | Finding | Decision | Resolution |
|---|---|---|---|
| P1 | missing domain trigger를 강제해 written compatibility 위반 | ACCEPT | present-only validation + schema required 축소 |
| P2 | schema가 whitespace/empty domain item 허용 | ACCEPT | `minLength` + non-whitespace pattern을 top/domain에 적용 |
| P2 | validate가 같은 YAML/JSON raw issue를 중복 출력 | ACCEPT | emitted issue dedupe + exact-count test |

Round 1 이후 dependency-complete Python으로 5개 스위트 186 tests(1 skipped)가 모두 통과했다.

## 4. Round 2

- Reviewer: fresh Codex headless session `019f6c35-9aa2-7ea1-91f7-807269a6f565`.
- Isolation: read-only, no file edit, no subagent, no session resume, no review skill invocation.
- Verdict: `CHANGES_REQUIRED`.
- Findings: P0 0 / P1 0 / P2 2.

| Severity | Finding | Decision | Resolution |
|---|---|---|---|
| P2 | semantic validator가 non-mapping `risk` FAIL을 두 번 발행 | ACCEPT | materialization primitive 단일 소유 + exact-count test |
| P2 | optional domain fields의 positive schema test 누락 | ACCEPT | schema-level omission acceptance test 추가 |

## 5. Round 3

- Reviewer: fresh Codex headless session `019f6c39-df8e-7782-908f-0f4ccb46b452`.
- Isolation: read-only, no file edit, no subagent, no session resume, no review skill invocation.
- Verdict: `CLEAN`.
- Findings: P0 0 / P1 0 / P2 0.
- Evidence: governed-field malformed matrix 0 mismatch, compiler 6/6, dependency-complete validator 110/110,
  generate no-write probe, all three gate-hook controlled blocks, syntax/schema parse, `git diff --check`.

## 6. Acceptance

| Acceptance ID | Final Status | Evidence |
|---|:---:|---|
| FB13-AC1 | PASS | all six top fields reject scalar/null/bad/blank items |
| FB13-AC2 | PASS | optional domain fields validate when present and remain compatible when absent |
| FB13-AC3 | PASS | deterministic aggregated `ProfileCompileError` |
| FB13-AC4 | PASS | generate returns fail before mkdir/JSON/registration write |
| FB13-AC5 | PASS | validate rc1 and three gate hooks controlled block |
| FB13-AC6 | PASS | dependency-free semantic validation plus schema defense |
| FB13-AC7 | PASS | merge/dedupe/order/source immutability regression coverage |
| FB13-AC8 | PASS | three distinct fallback headless reviews with triage; final round CLEAN |

## 7. Final Decision

APPROVED. Claude CLI availability failure is explicitly recorded rather than represented as a Claude review. The
user-authorized fallback was executed as three distinct ephemeral read-only headless sessions without subagents.
Rounds 1 and 2 findings were all accepted after reproduction; Round 3 was clean and required no closure rework.

## 8. Completion Checklist

- [x] Round 2 fresh headless review and triage.
- [x] Round 3 fresh headless review and triage.
- [x] Extra closure review not applicable because Round 3 caused no changes.
- [x] Final acceptance table and verdict.
