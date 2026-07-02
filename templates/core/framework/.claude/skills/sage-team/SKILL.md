---
name: sage-team
description: "Drive the implementation half of a SAGE PDCA cycle (Phases 03–06) after the plan exists — implementation, deterministic verification, QA, the Phase-05 review (via /sage-review), and completion, with file-ownership boundaries. Resumable. Invoke when the user says /sage-team (Claude) or $sage-team (Codex), 팀 개발, 팀 오케스트레이션, run the team, or after /sage-plan (or /sage-cycle) hands back an ownership map."
---

# sage-team — SAGE PDCA Team Orchestration

Invoke as `/sage-team` (Claude) or `$sage-team` (Codex).

This skill takes the plan + ownership map that `/sage-plan` produced and drives
the cycle to completion: implementation → deterministic verification → QA → Phase-05
review → completion report. It is the host-side orchestrator; SAGE still owns every
deterministic gate (`pre-implementation-gate`, `verify-changes`, `sage review-loop`
audit, the 06←05 report←approve backstop). This skill never reimplements a gate — it
makes sure the existing ones are actually invoked.

> **SOFT-ENFORCED, not a gate.** Following `/sage-team` makes the review loop and
> verification non-skippable *within this procedure*. It does NOT close the deterministic
> bypass: a host that skips `/sage-team` and hand-writes a Phase-05 doc with `APPROVED`
> still passes the 06←05 gate. True enforcement (the gate also checking loop-audit +
> test evidence) is a separate hardening step. State this limit if asked.

## Read these first (mandatory, in order)

1. `docs/sage_harness/skills/sage-team.md` — authoritative spec: procedure, drift_checks
2. `AGENT_GUIDE.md` — PDCA phases, risk gate, phase-first rule
3. `docs/agent/pdca-templates.md` — phase roles (03 impl+tests, 04 gap+coverage, 05 verdict)
4. `sage/project-profile.yaml` — `components`, `team.core`, `verification`, `pdca.review_loop`

## Gate check

Confirm the profile is bootstrapped (`project.name` non-empty, `risk`/`components` set).
If not → stop: "Profile is not bootstrapped. Run `/sage-init` first."

A plan doc (Phases 00–02) for this cycle must already exist. If none → stop and direct
the user to `/sage-plan` (do NOT silently author the plan here — that is a
different skill's job).

## Resolve the cycle + resume point (presence ≠ completion)

Identify the **single cycle** by its plan-doc stem (the feature name `/sage-plan`
used). Match every phase doc and audit run to that one stem — ignore stale docs from
other cycles. Then find the first incomplete stage using **evidence anchors**, not bare
file existence:

- **03 complete** = pre-code ownership/checklist exists, implementation files exist for
  the owned components, acceptance trace is recorded, AND `verify-changes` evidence
  (build/test results) is recorded in the 03 doc.
- **04 complete** = gap + qa coverage + acceptance evidence context recorded in the 04 doc.
- **05 state machine** (resolve from the 05 doc + `sage review-loop` audit for this cycle):
  - `05_started` — 05 doc records a `run_id` and `.sage/loop_audit.jsonl` has that run
    **open (not closed)** → resume by re-entering the review loop (do not restart it).
  - `05_closed_nonapproved` — the matching run is **closed with result ≠ APPROVED**
    (e.g. BLOCKED), or the 05 doc verdict is REJECTED/BLOCKED → resume by reworking
    (back to step 3) or stay blocked. **Do not enter 06.**
  - `05_approved` — the 05 doc has the `APPROVED` marker AND the matching `run_id` is a
    **closed run with result APPROVED** (audit `integrity_issues` clean: no orphan/dup)
    → the only state that allows 06.

Start at the first stage whose anchor is absent. A doc that merely exists without its
anchor is treated as incomplete (conservative).

## Step 1 — Implementation (Phase 03)

Before source edits, open/update the 03 doc with file ownership, implementation
checklist, verification plan, and Phase-01 acceptance IDs. Then dispatch implementers by
ownership from `profile.components` / `team.core`. Each implementer edits ONLY its
component's paths (file-ownership boundary; the integration point is stated in the plan
doc).

- **Claude host**: spawn implementers as **parallel subagents** (one per component).
- **Codex host**: **sequential** delegation (no parallel-subagent model) — same ownership
  boundaries, one implementer at a time. This is a throughput difference only; the
  procedure, artifacts, and boundaries are identical. State "sequentialized execution,
  semantics preserved."

Each implementer records its files, checklist, acceptance trace, and **unit tests** into
the 03 doc.

## Step 2 — Deterministic verification

Invoke verification per `profile.verification` for the change's risk level:
```
scripts/verify-changes.sh        # build / test / lint at the risk gate
```
SAGE owns the policy, gate levels, and result format (`verification-protocol.md`); this
skill only triggers the run. (`pre-implementation-gate` is the edit/phase hook — it is
**not** the verification executor; do not conflate them.) Record results in the 03 doc.
If the gate is red, STOP — do not advance to review on a failing build/test/lint.

## Step 3 — QA (Phase 04)

Invoke the `qa` agent: assess design↔implementation gap + **test coverage** (covered /
not covered / intentionally excluded; recommended additional scenarios) + acceptance
evidence (`PASS`/`FAIL`/`NOT TESTED`/`N/A`). Record in the 04 doc. **No verdict here** —
that belongs to Phase 05.

## Step 4 — Review (Phase 05) — via /sage-review (mandatory)

Hand off to **`/sage-review`** (`$sage-review` on Codex). Do NOT hand-write a Phase-05
doc. `sage-review` resolves the review mode (cross-model opposite-runtime when reachable,
else clean-context) and, when `pdca.review_loop.enabled` + risk ∈ {L2, L3}, runs the
adversarial find→refute→triage→rework loop, recording every round to
`.sage/loop_audit.jsonl` via `sage review-loop`.

- If the loop's FIND lenses cannot run in parallel (Codex), run them **sequentially** —
  same lenses, same artifacts, same audit; mark "sequentialized execution, semantics
  preserved." Sequentialization must not change ownership, review independence, or the
  recorded outcome.
- The verdict maps to the 05 doc's Final Status (`APPROVED | FAIL | BLOCKED`). Required
  acceptance items marked `FAIL` or `NOT TESTED` block APPROVED. On BLOCKED, STOP — no
  completion until cleared.
- Ensure the 05 doc carries a `Loop-Run: <run_id>` line (sage-review writes it). The 06←05
  audit gate (`pdca.review_loop.report_gate_enforce`) binds the report to that closed
  APPROVED run; without it, Step 5 is blocked (enforce) or warned (advisory).

## Step 5 — Completion (Phase 06)

Only when the cycle is `05_approved` (see resume state machine), the `leader` writes the
06 completion report. The existing 06←05 gate enforces this deterministically, and
`verification.acceptance.report_gate_enforce` can warn/block if 04 acceptance evidence is
missing or unresolved — never bypass it.

After 06 is written, run the configured knowledge write-back when it is enabled:

1. If `knowledge_capture.update_after_dev: true` and `knowledge_capture.vault_path`
   is set, create `.sage/knowledge_writeback_summary.md`. This note is the durable,
   cross-project distillation that outlives the workspace — **not** a build log. Synthesize
   (do not transcribe) from PDCA 00~06; keep it short (a few sentences per axis) and cover:
   1. **Architecture & module boundaries** — the split, each module's responsibility, dependency direction, and *why* (from 02-design).
   2. **Key design decisions & trade-offs** — the alternatives considered and why this path (from 00/02).
   3. **Loop A findings & accepted rework + reasoning** — what adversarial review caught in the code and *why* it mattered (from 05), not just the counts.
   4. **L3 security / risk posture** — sensitive areas, chosen mitigations (from 00 risk + 05 security).
   5. **Reusable lessons** — what a future similar project should carry forward (from 06 lessons).
   6. **Links to related vault notes** — `[[...]]` to prior cycles / design notes (vault notes only; project-local `plan_docs` die with the workspace, so point to detail with one line, don't copy it).
2. Run:
   ```bash
   python -m sage knowledge write-back --title "[cycle stem]" --summary-file .sage/knowledge_writeback_summary.md --append-log
   ```
3. Record the command output in 06. If it reports `N/A` or fails, record the exact
   skipped/failed reason; do not claim vault capture completed.

> **Single write path (do NOT freelance).** The vault note, `wiki/log.md`, and any index
> are written ONLY by `sage knowledge write-back` (it resolves the vault path, note convention,
> tags style, and index from the profile). Never hand-write a vault note or use an obsidian
> MCP to create cycle notes — that produced the 6th-test misplaced `<project>/sage/*.md`.
> Likewise the loop audit (`.sage/loop_audit.jsonl`) is written ONLY by `sage review-loop`
> open/round/close — never append or edit it by hand (the gate validates record sequence and
> rejects hand-written rounds).

After write-back, capture the cycle's learning as an asset-improvement proposal (Loop C —
advisory, does not auto-apply; closes the 6th-test gap where loop findings never fed back
into framework assets):

```bash
python -m sage retro --run-id <RUN_ID>   # --vault if retro_note enabled
```

Record that retro ran (or why it was skipped) in 06. Applying any proposal is a separate
human-gated step.

## Done

The cycle is complete when 06 exists and reflects an APPROVED Phase 05 with a clean,
closed loop-audit run for this cycle, and **both** closing captures are accounted for in 06
(neither may be silently omitted):
- knowledge write-back has completed or 06 records a concrete skipped/failed reason;
- `sage retro` has run or 06 records why it was skipped.

Report the per-phase outcome + the recorded `run_id` to the user.

---

> This skill is a **CORE framework bootstrap asset**: hand-shipped by `sage install`,
> NOT a manifest-tracked skill (no claims file, no render hash, not gated by
> `sage validate`/`sage asset-check`). Its reference spec lives at
> `docs/sage_harness/skills/sage-team.md`. To change it, edit the framework template,
> not via `sage generate`. Deploy location is runtime-specific: Claude reads it from the
> repo (`.claude/skills/sage-team/`); Codex reads it from the user-global skills dir
> (`$CODEX_HOME/skills/sage-team/`).
