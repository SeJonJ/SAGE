# [Analyze] SAGE-FB-04 Host Model Discovery and Routing

Cycle-Stem: `sage-fb-04-host-model-routing`
Risk Level: L3

## 1. Design to Implementation Gap

- Implemented the planned read-only `sage models` command, bounded Codex cache reader, and non-entitlement Claude
  alias catalog.
- Implemented host-specific component selections without changing the legacy work-intensity tier.
- Closed component identity/path validation and made roster generation consume the same semantic validator before
  writing. A crafted `components[].id` had reproduced an out-of-root write when an intermediate directory existed;
  newline/parent component globs could also inject generated ownership Markdown and are now rejected. Component item
  keys are closed so a misspelled `runtime_models` cannot silently fall back to a host default, and the legacy model
  tier is constrained before it enters generated Markdown.
- Implemented explicit reviewer host/model validation and peer CLI model arguments. Legacy profiles still use the
  opposite runtime's CLI default, but validate/doctor now warn that no interview selection was recorded.
- Model selection for component delegation remains host-capability dependent; the skill must report
  `MODEL_SELECTION_DEGRADED` when the host cannot pin a model. It may not claim the configured value ran.
- No paid probe, network request, credential read, or historical session metadata scrape was added.

## 2. Acceptance Evidence

| ID | Status | Evidence |
|---|---|---|
| FB04-AC1 | PASS | `sage models` text/JSON tests and live CLI output. |
| FB04-AC2 | PASS | regular non-symlink, inode-stable, size-bounded Codex cache tests; hidden entries excluded. |
| FB04-AC3 | PASS | Claude catalog is labeled syntax-only/account-unverified in code, tests, and docs. |
| FB04-AC4 | PASS | `components[].runtime_models` tests preserve legacy `model`. |
| FB04-AC5 | PASS | configured `cross_model.reviewer.{host,model}` requires an explicit opposite host; cross-model profiles without it emit a visible CLI-default WARN. |
| FB04-AC6 | PASS | argv tests and cross-check invocation test cover Codex `-m` and Claude `--model`. |
| FB04-AC7 | PASS | malformed routing/component/path, key typo, parent glob, Markdown injection fail-closed tests plus doctor catalog status tests. |
| FB04-AC8 | PASS | roster scaffold records active host and runtime model separately from tier. |
| FB04-AC9 | PASS | profile template, bootstrap, review, team, AGENT_GUIDE, and README updated. |
| FB04-AC10 | PASS | Three fresh Claude rounds plus closure review completed with findings triaged. |

## 3. Verification

- Focused aggregate: 197 tests PASS.
- Official harness: `ALL HOOK TESTS PASS`.
- Full unittest discovery: 1310 tests PASS, 1 skipped.
- `git diff --check` and Python compileall: PASS.
- Component/roster safety module pair: 19 tests PASS.

## 4. Broad External Review Round 3 Triage

Claude session `a01c9b7a-ee27-483b-9650-bd836aa264ca`의 account entitlement 표기 P3를 수용했다. Codex의
로컬 cache는 후보와 fetch provenance를 확인할 뿐 현재 계정 권한을 증명하지 않으므로 `account_verified`는
false다. `verification=cache-confirmed`, stale 시각, candidates는 유지해 사용자 선택 기능은 변하지 않는다.

## 5. External Review Closure

Fresh closure session `ead09722-14af-4538-b8b0-155761c95973` marked FB04 CLEAN. The three required
review rounds used sessions `7103906f-8bd3-484c-bb8c-937e92496f5a`,
`637f2d5c-1597-4b9a-a373-8e0b6bc1ebe1`, and `a01c9b7a-ee27-483b-9650-bd836aa264ca`.
