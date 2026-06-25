---
name: sage-team
description: "Orchestrate a full SAGE PDCA cycle after the plan exists — drives implementation, deterministic verification, QA, the Phase-05 review (via /sage-review), and completion, with file-ownership boundaries. Resumable. Invoke when the user says /sage-team (Claude) or $sage-team (Codex), 팀 개발, 팀 오케스트레이션, run the team, or after /sage-pdca-start hands back an ownership map."
---

# sage-team — SAGE PDCA Team Orchestration

Invoke as `/sage-team` (Claude) or `$sage-team` (Codex).

This skill takes the plan + ownership map that `/sage-pdca-start` produced and drives
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
the user to `/sage-pdca-start` (do NOT silently author the plan here — that is a
different skill's job).

## Resolve the cycle + resume point (presence ≠ completion)

Identify the **single cycle** by its plan-doc stem (the feature name `/sage-pdca-start`
used). Match every phase doc and audit run to that one stem — ignore stale docs from
other cycles. Then find the first incomplete stage using **evidence anchors**, not bare
file existence:

- **03 complete** = implementation files exist for the owned components AND
  `verify-changes` evidence (build/test results) is recorded in the 03 doc.
- **04 complete** = gap + qa coverage context recorded in the 04 doc.
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

Dispatch implementers by ownership from `profile.components` / `team.core`. Each
implementer edits ONLY its component's paths (file-ownership boundary; the integration
point is stated in the plan doc).

- **Claude host**: spawn implementers as **parallel subagents** (one per component).
- **Codex host**: **sequential** delegation (no parallel-subagent model) — same ownership
  boundaries, one implementer at a time. This is a throughput difference only; the
  procedure, artifacts, and boundaries are identical. State "sequentialized execution,
  semantics preserved."

Each implementer records its files, checklist, and **unit tests** into the 03 doc.

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
not covered / intentionally excluded; recommended additional scenarios). Record in the
04 doc. **No verdict here** — that belongs to Phase 05.

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
- The verdict maps to the 05 doc's Final Status (`APPROVED | FAIL | BLOCKED`). On BLOCKED,
  STOP — no completion until cleared.
- Ensure the 05 doc carries a `Loop-Run: <run_id>` line (sage-review writes it). The 06←05
  audit gate (`pdca.review_loop.report_gate_enforce`) binds the report to that closed
  APPROVED run; without it, Step 5 is blocked (enforce) or warned (advisory).

## Step 5 — Completion (Phase 06)

Only when the cycle is `05_approved` (see resume state machine), the `leader` writes the
06 completion report. The existing 06←05 gate enforces this deterministically — never
bypass it.

## Done

The cycle is complete when 06 exists and reflects an APPROVED Phase 05 with a clean,
closed loop-audit run for this cycle. Report the per-phase outcome + the recorded
`run_id` to the user.

---

> This skill is a **CORE framework bootstrap asset**: hand-shipped by `sage install`,
> NOT a manifest-tracked skill (no claims file, no render hash, not gated by
> `sage validate`/`sage review`). Its reference spec lives at
> `docs/sage_harness/skills/sage-team.md`. To change it, edit the framework template,
> not via `sage generate`. Deploy location is runtime-specific: Claude reads it from the
> repo (`.claude/skills/sage-team/`); Codex reads it from the user-global skills dir
> (`$CODEX_HOME/skills/sage-team/`).
