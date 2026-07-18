# [Implementation] SAGE-FB-04 Host Model Discovery and Routing

Cycle-Stem: `sage-fb-04-host-model-routing`
Risk Level: L3

## 1. Ownership

- Model catalog and routing: `sage/model_catalog.py`, `sage/model_routing.py`, `sage/commands/models.py`
- Runtime consumers: `sage/commands/review.py`, `sage/commands/doctor.py`, `sage/commands/generate.py`, `sage/cli.py`
- Contract/docs: `schema/profile.schema.json`, `templates/project-profile.yaml`, framework/bootstrap/review docs, README
- Verification: focused model routing/discovery/review/doctor/roster tests and official/full harness suites

## 2. Checklist

- [x] Add failing discovery and routing tests.
- [x] Implement bounded provenance-aware catalogs.
- [x] Implement profile semantic validation and doctor diagnostics.
- [x] Wire reviewer model into peer argv.
- [x] Warn when cross-model review falls back to an unselected peer CLI default model.
- [x] Wire component active-host model into roster scaffold.
- [x] Fail before roster writes for unsafe/duplicate component IDs, injected/escaping component globs, malformed paths,
  or invalid runtime models.
- [x] Close component item keys so `runtime_modles`-style typos cannot silently select the host default, and validate
  the legacy work-intensity model before rendering it into Markdown.
- [x] Update profile interview and runtime docs.
- [x] Run focused and full deterministic verification.
- [x] Complete three independent Claude reviews and triage findings.

## 3. Acceptance Trace

FB04-AC1 through FB04-AC10 are tracked in the matching Phase 04 analysis document after implementation.

## 4. Verification Evidence

- Focused model catalog/routing/review/doctor/roster aggregate: 197 tests PASS.
- Official harness: `ALL HOOK TESTS PASS` including section 48.
- Full discovery: 1310 tests PASS, 1 skipped.
- Live read-only CLI: Codex visible cache candidates reported `cache-confirmed`; Claude aliases reported
  `syntax-only/account-unverified`.
- Component/roster safety regression: `19 tests` PASS, including a reproduced out-of-root write attempt,
  Markdown path/model injection, runtime-model key typo, and explicit warning coverage for an unselected cross-review host/model.

## 5. Broad External Review Round 3

- Reviewer: Claude headless session `a01c9b7a-ee27-483b-9650-bd836aa264ca`.
- 수용(P3): Codex cache가 존재한다는 이유만으로 JSON `account_verified=true`를 반환해 현재 계정 entitlement를
  검증한 것처럼 보였다. Local catalog provenance는 `cache-confirmed`로 유지하되 entitlement flag는 false로
  고정했다. Model catalog/CLI `5 tests`가 PASS했다.
