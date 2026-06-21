---
name: sage-review
description: "Run SAGE Phase-05 independent review — invokes the reviewer agent in clean-context or cross-model mode (as resolved by the project profile) and produces a structured review report. Invoke after implementation and QA complete, before any L3 merge or release tag. Also use when the user says /sage-review, phase-05, 독립 검토, Phase-05 리뷰, or cross-model review."
---

# sage-review — SAGE Phase-05 Independent Review

## Read these first (mandatory, in order)

1. `docs/sage_harness/skills/sage-review.md` — authoritative spec: procedure, drift_checks
2. `docs/agent/review-protocol.md` — the reviewer output format
3. `sage/project-profile.yaml` — `options.cross_model`, `cross_model.invocation`

## Resolve review mode

From `sage/project-profile.yaml`:
- If `options.cross_model: true` AND `cross_model.invocation` path is reachable
  → **opposite-runtime review** (cross-model, removes model bias)
- Otherwise → **clean-context same-runtime review** (fresh context, same model)

State the resolved mode before invoking the reviewer.

## Gather the review inputs

Before invoking the reviewer, collect:
1. Plan doc path(s) for the current PDCA cycle (from `paths.plan_docs`)
2. List of changed files and unit test results (from implementers)
3. QA findings summary (from qa agent)

If any input is missing, block and request it from the relevant agent.

## Invoke the reviewer

Hand off to the `reviewer` agent with:
- Review mode: [resolved above]
- Plan doc: [path]
- Implementation summary: [changed files + test status]
- QA summary: [qa findings]

Instruct the reviewer to produce a report per `docs/agent/review-protocol.md`.
Do not filter or summarize the reviewer's findings — present them verbatim.

## Handle reviewer decisions

- **CLEAR**: record in the plan doc under `## Phase-05 Review` and proceed
- **BLOCK on L3 change**: record the block in the plan doc, STOP — do not
  release or merge until the reviewer explicitly clears it
- **ADVISORY**: present to the leader and let the leader decide whether to
  address before release

## Record the outcome

Add a `## Phase-05 Review` section to the plan doc:
```markdown
## Phase-05 Review

Mode: [clean-context same-runtime | opposite-runtime cross-model]
Reviewer verdict: [CLEAR | BLOCK]
L3 blocks: [count, or "none"]
Date: [YYYY-MM-DD]
```

---

> This skill is a **CORE framework bootstrap asset**: hand-shipped by `sage install`,
> NOT a manifest-tracked skill (no claims file, no render hash, not gated by
> `sage validate`/`sage review`). Its reference spec lives at
> `docs/sage_harness/skills/sage-review.md`. To change it, edit the framework
> template, not via `sage generate`. Deploy location is runtime-specific: Claude
> reads it from the repo (`.claude/skills/sage-review/`); Codex reads it from the
> user-global skills dir (`$CODEX_HOME/skills/sage-review/`).
