---
id: sage-team
kind: skill
# CORE skill (neutral). Project specifics come from profile, not this spec.
# CORE framework bootstrap asset: hand-shipped by `sage install`, NOT manifest-tracked.
# The manifest/claims/validate loop is reserved for project-authored skills
# (spec + claims + render hash) created via the generate/extract flow.
---
## intent
Orchestrate a full PDCA cycle after the plan exists: drive implementation, deterministic
verification, QA, the Phase-05 review (via sage-review), and completion, honoring file
ownership. SAGE owns the deterministic gates; this skill only ensures they are invoked.

## when_to_use
- After `sage-plan` (or `/sage-cycle`) produced a plan + ownership map, to run the cycle to completion
- When the user says "/sage-team" (Claude), "$sage-team" (Codex), "팀 개발",
  "팀 오케스트레이션", "run the team", or asks to drive the team through implementation→review

## procedure
1. Read `sage/project-profile.yaml` — confirm bootstrapped; confirm a plan doc (Phases
   00–02) for this cycle exists. If not bootstrapped → direct to `/sage-init`; if no plan
   → direct to `/sage-plan` (do not author the plan here).
2. Resolve the cycle by its plan-doc stem and find the resume point by evidence anchors,
   not file presence: 03 complete = pre-code checklist + impl + recorded verify evidence;
   04 complete = gap + qa coverage + acceptance evidence context; 05 state ∈ {started (open run), closed-nonapproved, approved
   (APPROVED marker + matching closed APPROVED run, audit integrity clean)}. Only
   `05_approved` permits Phase 06. Start at the first stage whose anchor is absent.
3. Implementation (03): before source edits, open/update the 03 doc with ownership,
   checklist, and Phase-01 acceptance IDs. Root scaffolding/config/glue (build files,
   `local.properties`, `.gitignore`, `settings.*`) are source edits too — classified by
   `profile.risk`, not component ownership; no "scaffolding is exempt" shortcut. For L2/L3
   this is a hard gate (`pre_implementation_required` includes `03`): a source edit before
   03 exists is BLOCKED. Then dispatch implementers by ownership (Claude = parallel
   subagents, Codex = sequential, semantics preserved). Each edits only its component paths
   and records files, checklist, acceptance trace, and unit tests into 03.
4. Verification: invoke `scripts/verify-changes.sh` per `profile.verification` at the risk
   gate. SAGE owns policy/gates/result format; this skill only triggers the run
   (pre-implementation-gate is not the executor). Record results in 03; stop if red.
5. QA (04): invoke the qa agent for design↔implementation gap + test coverage +
   acceptance evidence (`PASS`/`FAIL`/`NOT TESTED`/`N/A`). No verdict.
6. Review (05): hand off to `/sage-review` (never hand-write 05). It records the loop to
   `.sage/loop_audit.jsonl`, resolves cross-model, and blocks APPROVED when required
   acceptance evidence is `FAIL` or `NOT TESTED`. On BLOCKED, stop.
7. Completion (06): only when `05_approved`, the leader writes 06. The 06←05 gate enforces
   this deterministically.
8. Knowledge write-back: if `knowledge_capture.update_after_dev: true` and
   `knowledge_capture.vault_path` is set, write the final cycle summary to
   `.sage/knowledge_writeback_summary.md` — a durable cross-project distillation
   (synthesize, do not transcribe). Lead with a required 2–3 sentence `## Summary` (never
   blank), then cover architecture & module boundaries, key decisions/trade-offs, Loop A
   findings + reasoning, L3 security posture, reusable lessons, and `[[vault links]]`. First
   check the vault root for an authoring guide (`CLAUDE.md`/`AGENTS.md`/`GEMINI.md`/`AGENT_GUIDE.md`,
   first found) and follow its note conventions — choose tags/prefix and body format per it —
   then run `python -m sage knowledge write-back --title "<cycle-stem>" --prefix <PREFIX> --tags "<t1,t2,…>" --summary-file .sage/knowledge_writeback_summary.md --append-log` (omit --tags/--prefix for defaults when no guide).
   Record the output or skipped reason in the completion report. This is an explicit
   host step, not hidden automatic mutation. **One allowed hand-edit only:** if the vault's
   guide keeps a history *table* in `log.md`/index, add that row by hand (CLI appends a line,
   not a row) — limited to that existing hub table; never hand-create notes and never write
   outside the vault-resolved path. If `.sage/plan_interview.md` exists (a planning interview
   ran) and vault is enabled, also capture it as a **separate** note via the same path (same
   guide-derived prefix/tags apply): `python -m sage knowledge write-back --title "<cycle-stem> 기획 인터뷰" --prefix <PREFIX> --tags "<t1,t2,…>" --summary-file .sage/plan_interview.md --append-log`.
9. Retro (Loop C, advisory): run `python -m sage retro --run-id <RUN_ID> --feature <cycle-stem>`
   — always pass `--feature` (the plan-doc stem) so the note title names the cycle instead of
   being derived from the sole 05 doc or falling back to the run_id. A vault human-gate note is
   written only when the vault is enabled (`vault_path` + `retro_note`, both off by default);
   if no note path is printed, record `retro note skipped: vault disabled` and stop. When a note
   is written it is **empty on purpose**: the CLI gathers evidence deterministically and leaves
   distillation to you. So open the note, run the printed distiller prompt over the evidence, and
   fill `## 요약` (1–2 human-readable lines) and `## 제안` (the JSON proposal array). Verify with
   `python -m sage retro --check <note path> --run-id <RUN_ID>`; it exits non-zero while the note
   is still the blank template, a proposal lacks a valid `target`/`proposed_change`, or the note
   belongs to another run. Never leave the note unfilled and never set `approved: true` yourself.
   Record that retro ran, or why it was skipped, in the completion report — a required completion
   axis, not optional.
10. Final user report: include the per-phase outcome, review `run_id`, generated artifact
   inventory (plan docs, code/config files, vault notes, loop-audit dashboard, retro note),
   verification commands/results, and any human action still required. Summarize the retro
   proposals inline (pattern → target → proposed change) so the user can judge them without
   opening the note. If a retro human-gate note was created, explicitly ask the user to review
   it and approve `approved: true` before `sage absorb --from-retro`; do not imply the proposal
   has been applied.

## advisory_scope
- role_boundary: does not implement code; orchestrates leader/implementers/qa/reviewer
- uses: leader, implementer agents, qa agent, sage-review skill, verify-changes, project-profile.yaml
- convention_doc: AGENT_GUIDE.md, docs/agent/pdca-templates.md
- overlay: optional `sage/asset_overrides/skills/sage-team.md` has project-local
  priority over CORE guidance and is not shipped by `sage install`; it must not relax AGENT_GUIDE, phase, review, or verification gates

## enforcement
- SOFT-ENFORCED: the loop/verification are non-skippable only when this skill is followed.
  It does not close the deterministic bypass (a hand-written 05 + APPROVED still passes
  06←05). True enforcement (gate checks loop-audit + test evidence) is a separate step.

## runtime_bindings
- claude: .claude/skills/sage-team/SKILL.md (repo — Claude Code auto-discovers)
- codex:  $CODEX_HOME/skills/sage-team/SKILL.md (global — codex does not auto-discover repo-scoped skills)

## drift_checks
- conformance: procedure step 6 (Phase-05 via sage-review, not hand-written), step 7
  (06 only when 05_approved), step 8 (knowledge write-back when enabled), and step 9
  (retro run with `--feature`; when a note was written, it is filled and `retro --check
  --run-id` is clean — otherwise a recorded skip) must be present. The final report must name
  created artifacts, summarize the retro proposals, and state any pending retro human-gate review.
