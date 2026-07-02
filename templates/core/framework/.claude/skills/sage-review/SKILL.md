---
name: sage-review
description: "Run SAGE Phase-05 independent review. Single-pass clean-context/cross-model review by default; runs the adversarial review-rework loop (find→refute→triage→rework→terminate) when pdca.review_loop.enabled. Invoke after implementation and QA complete, before any L3 merge or release tag. Also use when the user says /sage-review, phase-05, 독립 검토, Phase-05 리뷰, or cross-model review."
---

# sage-review — SAGE Phase-05 Independent Review

## Read these first (mandatory, in order)

1. `docs/sage_harness/skills/sage-review.md` — authoritative spec: procedure, drift_checks
2. `docs/agent/review-protocol.md` — the reviewer output format + loop contract
3. `sage/project-profile.yaml` — `options.cross_model`, `cross_model.invocation`,
   and **`pdca.review_loop`** (lenses, refuters, max_iterations, dry_rounds, budget_tokens)

## Resolve review mode

`sage doctor` resolves it from `options.cross_model` + peer CLI availability (no gstack):
- `options.cross_model: true` AND the peer runtime CLI is available
  (claude-host→`codex`, codex-host→`claude`) → **opposite-runtime review** (cross-model, removes model bias).
  SAGE invokes the peer directly — claude-host runs `codex exec`, codex-host runs `claude -p`
  (both are non-interactive subcommands; do NOT claim codex is "interactive-only").
- Otherwise (cross off, or peer CLI unavailable) → **clean-context same-runtime review**.

Do not invoke the peer ad-hoc. Use the deterministic commands so the fallback is never silent:
- cross_model **true** → `sage cross-check` (invokes the peer, prints its review, emits `REVIEWER_ACTUAL`)
- cross_model **false** → `sage review` (same-runtime, emits `REVIEWER_ACTUAL: same_runtime`)

If `sage cross-check` cannot reach the peer it prints `REVIEWER_ACTUAL: same_runtime` (not silent) — pass
that to `sage review-loop close --reviewer-actual` so the gate flags the degraded cross-model run. State the
resolved mode before reviewing.

## Choose pass vs loop

- If `pdca.review_loop.enabled` is **false/absent**, OR the change risk is **L0/L1**
  → run the **single-pass review** (next section).
- If `pdca.review_loop.enabled: true` AND risk ∈ **{L2, L3}**
  → run the **adversarial review-rework loop** ("Loop A" section below).

The loop body (find/refute/rework) is judgement and runs here in the host runtime.
SAGE owns only the deterministic gates: the loop counters/budget are recorded via
`sage review-loop`, and the hard backstop is the existing **report←approve** hook
(Phase 06 is blocked until Phase 05 records `APPROVED`). This skill never bypasses
that gate.

---

## Single-pass review (default)

### Gather inputs
1. Plan doc path(s) for the current PDCA cycle (from `paths.plan_docs`)
2. Changed files + unit test results (from implementers)
3. QA findings summary (from qa agent)
4. Phase 01 acceptance matrix + Phase 04 acceptance evidence table

If any input is missing, block and request it.

### Invoke the reviewer
Hand off to the `reviewer` agent with: review mode, plan doc path, implementation
summary (changed files + test status), QA summary, and acceptance evidence. Instruct it
to produce a report per `docs/agent/review-protocol.md`. Present findings verbatim — do
not filter.

### Handle the verdict
The reviewer's verdict maps to the **Final Status marker the gate reads** (the report←approve
hook looks for the literal `APPROVED`; `Final Status: CLEAR` would be rejected). Always record
one of `APPROVED | FAIL | BLOCKED`:
- Required acceptance items marked `FAIL` or `NOT TESTED` in Phase 04 block `APPROVED`.
  Use `N/A` only with explicit out-of-scope/deferred/user-approved reasoning.
- **CLEAR** → record `Final Status: APPROVED` (reason note: `CLEAR`), proceed
- **BLOCK on L3** → record `Final Status: BLOCKED` (reason: `BLOCK`), STOP (no release/merge until cleared)
- **ADVISORY** → present to the leader; if they accept the result, record `Final Status: APPROVED`
  (reason: `ADVISORY`), otherwise `BLOCKED`

---

## Loop A — adversarial review-rework (when `review_loop.enabled` + L2/L3)

Load `cfg = pdca.review_loop`. Open the audit trail and capture the run id, recording the
**intended** reviewer mode (`cross_model` if `options.cross_model: true`, else `same_runtime`):

```
REQ=$( [ cross_model true ] && echo cross_model || echo same_runtime )
RUN_ID=$(sage review-loop open --risk <L2|L3> --reviewer-requested $REQ)
```

`sage review-loop` auto-discovers the project root (the dir holding `sage/project-profile.yaml`),
so it records to the one canonical `.sage/loop_audit.jsonl` regardless of the current working
directory — open/round/close stay on the same trail. Pass the captured `$RUN_ID` to every
subsequent `round`/`close`.

Then repeat each round until a termination rule fires (max `cfg.max_iterations[risk]`):

### 1. FIND (parallel lenses + cross-model peer)
Run one reviewer per lens in `cfg.lenses` (parallel, divergent). For the cross-model peer,
**do not invoke the peer by hand** — write the review packet (diff + 05 context) to a file and run
`sage cross-check --packet-file <f>`; it invokes the peer (`codex exec`/`claude -p`) and prints the
peer's findings. Capture its last line `REVIEWER_ACTUAL: <mode>` as `ACTUAL` (it is `same_runtime`
if the peer was unreachable — fold those findings into the host's same-runtime review). Use the
**FIND prompt** (§ skeletons) for host lenses. Collect findings. **Dedup**: drop any finding whose key `(norm(file), line_bucket, lens, sha(norm(claim)))`
is already in `seen` (prevents tail/resurfacing churn).

### 2. REFUTE (adversarial false-positive filter)
For each fresh finding, run `cfg.refuters` refuters with the **REFUTE prompt**. A finding
**survives** only if refuting votes `< ⌈refuters/2⌉` (majority). Refuters bias toward
"refuted=true when uncertain" — this conservatively drops weak findings; the backstop for
a wrongly-dropped real issue is the human BLOCKED path. Add survivors to `seen`.

### 3. TRIAGE (human-escalation boundary)
For each survivor, run the **TRIAGE prompt**. If `scope == architecture_change` AND
`classify_risk(file)` is L3 → **stop the loop, escalate to a human**:
```
sage review-loop close --run-id $RUN_ID --result BLOCKED --reason BLOCKED_ARCH --iterations <n> --reviewer-actual $ACTUAL
```
Record the block in the Phase-05 doc and STOP. Architecture changes are not auto-reworked.

### 4. TERMINATION (evaluate in this fixed order)
- survivors == 0 → **APPROVED** (reason `CONVERGED`)
- `cfg.dry_rounds` consecutive rounds with 0 new findings → **APPROVED** (reason `DRY`)
- iteration ≥ `cfg.max_iterations[risk]` (still unconverged) → **BLOCKED** (reason `BUDGET_ITER`)
- cumulative tokens ≥ `cfg.budget_tokens[risk]` → **BLOCKED** (reason `BUDGET_TOK`)

On any terminal state, record the round then close (pass the **actual** reviewer mode so the gate
can flag a degraded cross-model run — `$ACTUAL` from `sage cross-check`, or `same_runtime`):
```
sage review-loop close --run-id $RUN_ID --result <APPROVED|BLOCKED> --reason <REASON> --iterations <n> --reviewer-actual $ACTUAL
```

**Record the run id in the Phase-05 doc** — add a line `Loop-Run: $RUN_ID` to this cycle's
Phase-05 document. The 06←05 audit gate (`pdca.review_loop.report_gate_enforce`) binds the
report to this exact run: it reads `Loop-Run` + the `APPROVED` marker from the *same* 05 doc
and confirms the run closed APPROVED. Without this line the gate cannot bind the report to a
loop and (in advisory) warns or (in enforce) blocks.

### 5. REWORK + re-validate (only `within_design` survivors)
Hand the accepted findings to the relevant implementer with the **REWORK prompt** (do not
exceed the approved design in `02-design`). Then **re-validate** before the next round:
`scripts/verify-changes.sh` (build/test/lint at the risk gate) and `sage validate` must
PASS; if either fails, retry the round (within the iteration cap). If the rework changes
acceptance coverage, update Phase 03 and Phase 04 before the next review pass.

### Record the round (every iteration)
```
sage review-loop round --run-id $RUN_ID --iteration <n> \
  --found <N> --survived <N> --accepted <N> --arch <N> --tokens <cumulative>
```

### After close — Obsidian dashboard (optional)
If `knowledge_capture.loop_audit_dashboard` is true and `knowledge_capture.vault_path` is set,
`sage review-loop close` automatically refreshes the per-project vault dashboard
(filename derived from `note_convention` + `project.name`):
```
<vault>/<folder>/TECH - <project.name> loop audit.md
```
You may still run `sage review-loop show --vault` to inspect/regenerate it manually. The
dashboard is a side artifact, never a gate; a vault write failure is reported as a warning
without invalidating the audit close.

### Advisory-first rollout
Until the loop is trusted on this project, run it in **advisory mode**: drive the rounds and
record the audit trail, but keep the report←approve sign-off manual (the human/leader confirms
the recorded `APPROVED` before Phase 06). The deterministic 06←05 backstop is unchanged; the
loop adds the audited find→refute→rework rounds in front of it.

---

## Prompt skeletons (Loop A)

### FIND — per-lens reviewer
```
[ROLE] You review ONLY through the "{lens}" lens. Ignore other lenses.
[INPUT] changed files; 00/01/02 design; 03 implementation; 04 analysis.
[TASK] Find defects/risks in the "{lens}" dimension ONLY.
  - No speculation: only issues with a code citation (file:line).
  - Exclude already-handled or design-intended items.
[SEVERITY] P0=data loss/security/legal · P1=functional bug · P2=latent bug · P3=quality/convention
[OUTPUT] JSON array (empty [] if none):
[{ "lens":"{lens}", "file":"...", "line":N, "severity":"P0|P1|P2|P3",
   "claim":"what is wrong and why, 1-2 sentences", "repro":"evidence (optional)", "fix":"suggestion (optional)" }]
```

### REFUTE — skeptical verifier
```
[ROLE] You are a skeptical verifier. Your job is to REFUTE this finding, not accept it.
[INPUT] finding: {finding_json}; relevant code: {file_context}; design docs.
[TASK] Actively try to disprove it: is there already a guard? is the premise wrong?
  is it non-reproducible? does the cited file:line not match reality?
[RULE] If you cannot clearly refute it, refuted=false. If uncertain, refuted=true (conservative — drop weak findings).
[OUTPUT] { "finding_id":"{id}", "refuted": true|false, "reason":"1-2 sentences (file:line)" }
```

### TRIAGE — scope classifier
```
[ROLE] You triage a surviving finding's fix scope.
[INPUT] finding: {finding_json}; approved design: 02-design.
[TASK] Is the fix (a) local within the approved design, or (b) changing the design/architecture?
  (b) signals: new component / interface or signature change / data-model change / new external dependency / state-machine transition change.
[OUTPUT] { "finding_id":"{id}", "scope":"within_design|architecture_change", "reason":"..." }
```

### REWORK — implementer
```
[ROLE] You are the "{component}" implementer.
[INPUT] accepted findings (within_design only): {accepted[]}; current code; 03-implementation; 04-analyze.
[TASK] Fix each finding in code. Do NOT exceed the approved design (02).
  If a fix truly needs to exceed scope, STOP and report it as "architecture_change suspected" (do not edit).
  Update 03 (file ownership/checklist) and 04 (gap).
[OUTPUT] diff + updated 03/04 + table: | finding_id | applied/deferred/rejected | reason |
```

## Record the outcome

Add a `## Phase-05 Review` section to the plan doc. For Loop A, include the iteration table:
```markdown
## Phase-05 Review

Mode: [clean-context same-runtime | opposite-runtime cross-model]
Loop: [enabled | disabled]
Final Status: [APPROVED | FAIL | BLOCKED]    # the gate reads the literal APPROVED marker
Reason: [CONVERGED | DRY | BUDGET_ITER | BUDGET_TOK | BLOCKED_ARCH | (single-pass: CLEAR | BLOCK | ADVISORY)]
Acceptance Gate: [PASS | FAIL | NOT TESTED items unresolved | N/A with reason]
Review Loop Iterations:
| iter | found | survived | accepted | arch | tokens |
|-----:|------:|---------:|---------:|-----:|-------:|
| 1    | 7     | 3        | 3        | 0    | 48000  |
| 2    | 1     | 0        | 0        | 0    | 60000  |
Audit: .sage/loop_audit.jsonl (run_id [rl-...])
Date: [YYYY-MM-DD]
```

If Final Status is BLOCKED, **do not write Phase 06** — the report←approve hook enforces this.

---

> This skill is a **CORE framework bootstrap asset**: hand-shipped by `sage install`,
> NOT a manifest-tracked skill (no claims file, no render hash, not gated by
> `sage validate`/`sage review`). Its reference spec lives at
> `docs/sage_harness/skills/sage-review.md`. To change it, edit the framework
> template, not via `sage generate`. Deploy location is runtime-specific: Claude
> reads it from the repo (`.claude/skills/sage-review/`); Codex reads it from the
> user-global skills dir (`$CODEX_HOME/skills/sage-review/`). The loop runs
> identically on both hosts — same skill body, same `sage review-loop` CLI.
