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
- After `sage-pdca-start` produced a plan + ownership map, to run the cycle to completion
- When the user says "/sage-team" (Claude), "$sage-team" (Codex), "팀 개발",
  "팀 오케스트레이션", "run the team", or asks to drive the team through implementation→review

## procedure
1. Read `sage/project-profile.yaml` — confirm bootstrapped; confirm a plan doc (Phases
   00–02) for this cycle exists. If not bootstrapped → direct to `/sage-init`; if no plan
   → direct to `/sage-pdca-start` (do not author the plan here).
2. Resolve the cycle by its plan-doc stem and find the resume point by evidence anchors,
   not file presence: 03 complete = pre-code checklist + impl + recorded verify evidence;
   04 complete = gap + qa coverage + acceptance evidence context; 05 state ∈ {started (open run), closed-nonapproved, approved
   (APPROVED marker + matching closed APPROVED run, audit integrity clean)}. Only
   `05_approved` permits Phase 06. Start at the first stage whose anchor is absent.
3. Implementation (03): before source edits, open/update the 03 doc with ownership,
   checklist, and Phase-01 acceptance IDs. Then dispatch implementers by ownership
   (Claude = parallel subagents, Codex = sequential, semantics preserved). Each edits
   only its component paths and records files, checklist, acceptance trace, and unit
   tests into 03.
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

## advisory_scope
- role_boundary: does not implement code; orchestrates leader/implementers/qa/reviewer
- uses: leader, implementer agents, qa agent, sage-review skill, verify-changes, project-profile.yaml
- convention_doc: AGENT_GUIDE.md, docs/agent/pdca-templates.md

## enforcement
- SOFT-ENFORCED: the loop/verification are non-skippable only when this skill is followed.
  It does not close the deterministic bypass (a hand-written 05 + APPROVED still passes
  06←05). True enforcement (gate checks loop-audit + test evidence) is a separate step.

## runtime_bindings
- claude: .claude/skills/sage-team/SKILL.md (repo — Claude Code auto-discovers)
- codex:  $CODEX_HOME/skills/sage-team/SKILL.md (global — codex does not auto-discover repo-scoped skills)

## drift_checks
- conformance: procedure step 6 (Phase-05 via sage-review, not hand-written) and step 7
  (06 only when 05_approved) must be present
