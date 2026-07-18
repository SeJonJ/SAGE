# [Analyze] SAGE-FB-05 Codex CORE Skill Installation Scope

Cycle-Stem: `sage-fb-05-codex-skill-scope`
Risk Level: L3

## 1. Design to Implementation Gap

- The planned explicit `global|project-local` Codex scope is enforced before lock acquisition. The deprecated
  `--no-global-skill` path remains available only as an explicit `disabled` receipt for CI/sandbox compatibility.
- Manifest `core_skill_receipts` records host, scope, and SAGE version. Legacy manifests are warned without guessing.
- Project-local CORE skills are included in overlay materialization and drift anchors when `.codex/skills` exists;
  global skills remain excluded from project overlay composition.
- validate checks the receipt and selected copy, while doctor inspects global, `.codex/skills`, and legacy
  `.agents/skills`. Duplicate precedence is reported as ambiguous and no opposite copy is auto-deleted.
- Generated onboarding guidance separates repository-contained prompts from the separately installed SAGE CLI/runtime.
- Project-local symlink ancestors fail before mutation, and late failures restore both CORE skills and project files.

## 2. Acceptance Evidence

| ID | Status | Evidence |
|---|---|---|
| FB05-AC1 | PASS | Codex install without scope exits 2 before destination mutation. |
| FB05-AC2 | PASS | Global and project-local installation regressions verify exact roots. |
| FB05-AC3 | PASS | Manifest receipt tests verify scope and SAGE version. |
| FB05-AC4 | PASS | Scope-switch test preserves the opposite copy and updates intent. |
| FB05-AC5 | PASS | validate tests cover missing selected copy, duplicate ambiguity, and content conflict. |
| FB05-AC6 | PASS | doctor test reports intended scope, all live paths, conflict, and manual cleanup. |
| FB05-AC7 | PASS | Generated scope-specific onboarding distinguishes prompt assets from CLI executables. |
| FB05-AC8 | PASS | Claude and deprecated CI opt-out regressions remain green. |
| FB05-AC9 | PASS | Symlink escape and project-local late-failure rollback tests pass. |
| FB05-AC10 | PASS | Three fresh Claude headless rounds plus closure review completed with findings triaged. |

## 3. Verification

- Focused install, doctor, validate, write-guard, and transaction regressions: PASS.
- Official harness: `ALL HOOK TESTS PASS`.

## 4. Residual Risk

- The manifest records intended scope; only host-side runtime evidence could prove which duplicate Codex actually
  loaded. SAGE therefore intentionally reports duplicate precedence as ambiguous.
- Global-scope validation is environment-dependent and advisory; doctor is the authoritative live-environment view.
- Runtime load precedence remains host-dependent; the receipt and doctor diagnostics make this ambiguity explicit.

## 5. Broad External Review Round 2 Triage

Claude session `637f2d5c-1597-4b9a-a373-8e0b6bc1ebe1`의 symlink marker P3를 실제 삭제로 재현해 수용했다.
Legacy rename 수렴은 SAGE가 설치한 정규 `SKILL.md`만 대상으로 해야 하므로 marker 또는 directory가 symlink면
사용자 자산으로 보존한다. 기존 정상 legacy 삭제와 foreign skill 보존 계약은 그대로 유지된다.

## 6. Broad External Review Round 3 Triage

Claude session `a01c9b7a-ee27-483b-9650-bd836aa264ca`의 cross-repository global install race P2를 수용했다.
각 repo lock이 달라도 write surface는 하나이므로 global scope에서 shared skills-root lock을 추가했다. Duplicate
winner 표기 제안은 runtime evidence 없이 precedence를 발명하지 않는 승인 설계와 충돌해 기각했으며, live
surface/version conflict와 수동 정리는 계속 doctor가 명시한다.

## 7. External Review Closure

Fresh closure session `ead09722-14af-4538-b8b0-155761c95973` marked FB05 CLEAN. All required review
evidence is complete, including the symlink-marker preservation and shared global lock rework.
