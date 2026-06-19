# Bootstrap Authoring Protocol (Conversational)

Use this when a project is first set up, or when a new component/asset must be
introduced. It defines **how an agent turns user intent into SAGE-conformant
assets through conversation** — the user supplies intent, the agent authors to
the spec, and a deterministic backend registers and verifies. The user does not
hand-write profile values or specs; the agent does, under the user's approval.
Some assets (agent/skill renders) still need an interpretive runtime render step
after scaffolding — this protocol marks where.

This document is runtime-neutral. Stack specifics (languages, frameworks,
high-risk domains, component names) come from the conversation and land in
`sage/project-profile.yaml` — never in this file.

---

## Principle

| Layer | Who | Determinism |
|:---|:---|:---|
| Intent | user (conversation) | — |
| Authoring (profile values, specs, plan docs) | agent, to the spec | interpretive |
| Registration (`sage generate`) + verification (`sage validate`) | deterministic | deterministic |
| Agent/skill render from scaffold | runtime AI | interpretive |

The agent renders; the backend checks. `sage validate` is the gate — it catches
schema and profile-semantic errors. Note the schema's strict unknown-key check
covers the top-level keys and selected sections (`risk`, `pdca`,
`output_contract`); most other nested sections are validated as loose objects,
and `--schema` (manifest JSON Schema) needs the optional `jsonschema` package.
So validate is a strong guardrail, not a total type-checker — author carefully.

The user stays **in the loop**: the agent authors per the rules and the user
approves. This is not a turnkey generator — intent's owner is the human.

---

## Stages

### 1. Install
`sage install --host {claude|codex} --dest <project>` places the harness, the
neutral docs (this file included), and an **empty** `sage/project-profile.yaml`
(schema keys fixed, values blank). Nothing is governed yet.

### 2. Interview → profile authoring
The agent interviews the user for intent, then fills `project-profile.yaml`
**values** (never adds/removes schema keys — determinism constraint). Surface the
decisions that genuinely need user intent; author the rest from them:

- `project.name` / `project.prefix`
- `components[]` — component boundaries (id + path globs + model). Filling this
  enables `sage generate --kind roster` to scaffold `implementer-<id>` specs.
- `risk.*` — derived from the stack and the high-risk domains the user names
  (e.g. secrets, auth, payments → `l3_*`). For L3 to be reviewable rather than
  hard-blocked, also set `risk.l3_review_strategy` (e.g. `claude_grep_first` |
  `codex_feature_signal`) — the review protocol blocks L3 until one is selected.
- `verification.commands` — the deterministic build/test/lint commands for the stack.
- `options.cross_model` — when true, Phase 05 review is opposite-runtime **only
  when reachable**; `sage doctor` resolves it from `options.cross_model` +
  `cross_model.invocation` + `capabilities` (e.g. gstack), and falls back to
  clean-context same-runtime when the invocation path or capability is
  unavailable. It is **not** resolved from `runtime.external_reviewer` (which
  records the intended preference only).

Present the filled profile (or the consequential choices) for user approval.

### 3. Handoff to the deterministic backend
On approval, hand off — do not keep authoring registration artifacts by hand:

```
# hook registration + manifest stamp. Default --target claude.
sage generate --kind hook --write --target claude     # or: --target both (claude + codex)
# component implementer SCAFFOLDS (only if components[] is set):
sage generate --kind roster --write
# verification (default --kind hook; use --kind all to also check agent/skill):
sage validate --check --schema --kind all
```

Notes that matter:
- `sage generate --kind hook` writes registration for `--target` (default
  `claude`). For a cross-model project that runs both runtimes, use
  `--target both`; `hooks.register` in the profile is documentation, not a
  generate input.
- `sage generate --kind roster` only **scaffolds** `docs/sage_harness/agents/
  implementer-<id>.md`. Those specs still need a runtime AI render and
  `extract_agent --register` (the existing interpretive agent pipeline) before
  they are manifest-registered — roster alone does not complete them.
- `sage validate` defaults to `--kind hook`; pass `--kind all` to also validate
  agent/skill renders (only meaningful once they are registered).

A `validate` FAIL is the guardrail working — fix the value/spec the message
points to and re-run; never bypass.

### 4. Phase-first authoring (before any code)
The `pre-implementation-gate` blocks L2/L3 code edits until the phases required by
`profile.pdca.pre_implementation_required` exist. Author the plan docs first,
through the same conversation:

- `00-base_plan` — CONTEXT (why / what / impact / risk)
- `01-plan` — CONTENT (requirements / data schema / API contract)
- `02-design` — architecture / sequence / error codes
- For L2/L3 work scoped to one component, also author `{component}/plan_docs/`
  (code-level design) before root `03-implementation` — see `pdca-templates.md`
  "Writing order for L2/L3 changes".

Templates and the 00↔01 / 02↔03 boundaries are in `pdca-templates.md`. Only after
the required phases exist does the gate admit implementation; the cycle then
continues 03 → 04 → 05 (review, cross-model when enabled) → 06.

### 5. Asset additions later
The same loop applies to introducing a new hook/agent/skill after bootstrap:
interview → author the spec under `docs/sage_harness/` → register. Hooks register
deterministically via `sage generate`; agent/skill specs need an interpretive
runtime render plus extraction/registration (they are not a pure deterministic
render). Never edit a generated artifact directly (see AGENT_GUIDE safety
boundaries).

---

## Signals of incorrect bootstrap
- Profile authored with a new top-level key → schema violation. Keys are fixed,
  fill values. (Nested unknown keys are strictly blocked only in `risk` / `pdca`
  / `output_contract`; other sections are looser — still do not invent keys.)
- Registration artifacts (`{host}/settings.json`, shims, agent renders) edited by
  hand → regenerate / re-render from spec instead.
- Cross-model project registered with `--target claude` only → codex side missing;
  use `--target both`.
- Code edited before the required phases exist for an L2/L3 change → the gate will
  block; author the phases first.
- `validate` FAIL bypassed to "move on" → the guardrail was right; fix the value.

## Related rules
- `AGENT_GUIDE.md` — Risk & Workflow Gate, safety boundaries
- `docs/agent/pdca-templates.md` — phase templates + separation + component-level order
- `docs/agent/review-protocol.md` — reviewer resolution (`sage doctor`), L3 review
- `docs/agent/risk-classification.md` — how `profile.risk` maps to levels
- `sage/project-profile.yaml` — the single mutable SSOT this protocol fills
