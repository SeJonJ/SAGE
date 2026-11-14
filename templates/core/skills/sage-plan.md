---
id: sage-plan
kind: skill
# CORE skill (neutral). Project specifics come from profile, not this spec.
# CORE framework bootstrap asset: hand-shipped by `sage install`, NOT manifest-tracked.
# The manifest/claims/validate loop is reserved for project-authored skills
# (spec + claims + render hash) created via the generate/extract flow.
---

## Overlay catalog selector (mandatory)

If the current boundary supplies `SAGE_OVERLAY_UNAVAILABLE_V1` for this root/role, it invalidates all earlier overlay bodies. Pause this SAGE workflow, explain the input problem, and allow diagnosis/user-directed source repair under the existing independent gates. Never shorten, split, migrate, or omit invalid overlay content automatically. Resume only after the next boundary supplies a valid current catalog.

Current overlay target: `sage-plan`. Before acting, use the current boundary's supplied
schema-version-2 catalog for the actual checkout `root` and `role: root`, with a definite
`generation`. Use only `targets["sage-plan"]` references into `sources`; each source has
`path`, `sha256`, and the exact delivered `content`. The applicable source order is:
`skills/sage-plan/shared` → `skills/sage-plan/personal`. Include only present sources; an absent slot adds no guidance.

Mandatory CORE, project policy, and independent gates take precedence over shared additions,
which take precedence over personal additions. Later entries do not automatically override
earlier ones. Other targets' bodies may be visible in the same context; do not apply them.
Catalog presence is never a skill invocation, Fast selection/conversion, or user approval.
Use the delivered content without a separate root-skill `overlay-local` fetch. Do not embed
personal bodies in shared/global renders, manifests, or permanent caches.

The current boundary's catalog, including an empty `sources`/`targets` catalog, replaces prior
catalog guidance. Do not revive historical content, infer freshness from hashes/mtime, or use
another checkout's sources. If the current root, role, generation/boundary, or active target is
missing or ambiguous, stop and request a context/input fix instead of guessing a recent target.
After compaction, manual skill reselection is not successful automatic recovery. Repeated
copies of the same generation/source are the same guidance, not instructions to repeat steps.

On nested plan/team/review invocation, use that child's own fixed target view rather than
merging the parent's sources; on return, resume this parent's view. This contract adds no
target stack database. Keep actual delivery path/hash references from this boundary for handoff;
a catalog supply list does not prove that every listed target was applied or complied with.

## intent
Own the planning half of a PDCA cycle (Phases 00–02): verify gate conditions,
invoke the leader to author plan docs, and distribute file ownership before any
L2/L3 code is written. Hands back an ownership map; `/sage-team` drives 03–06.

## when_to_use
- At the beginning of a new feature or change cycle, to produce the plan + ownership map
- When the leader needs to bootstrap plan docs (00–02) for a task
- When the user says "/sage-plan" (Claude), "$sage-plan" (Codex), "plan a feature",
  "기획", "설계 시작", "계획 세워", or asks to scope/plan a change before implementation
- Invoked by `/sage-cycle` as the 00–02 half of the full-cycle umbrella

## procedure
0. Resolve the conversation language once: an explicit `--lang ko|en` on this skill's
   invocation, then `interface.language` in `sage/project-profile.local.yaml`, then `ko`.
   Every question, proposal, progress note, warning and summary uses it; machine values
   and Phase 00–06 `Document-Language:` prose do not. Document prose includes section headings
   and list labels, except `## 5. Done Criteria` and `## 6. Done Criteria Revision Log`, which a
   parser reads by their exact string. See `docs/agent/language-policy.md`.
1. Read `sage/project-profile.yaml` — confirm the project is bootstrapped
   (`project.name` non-empty, `risk` and `components` set). If not, block and
   direct to `/sage-init`.
2. Read `AGENT_GUIDE.md` — identify the required PDCA phases (00–06) and the
   phase-first rule for L2/L3 files.
3. Determine the task scope: one-sentence description, then run the **planning interview**
   (`docs/agent/plan-interview.md` — core questions platform/features/data·API/constraints/
   done-criteria + adaptive, anchored to Phase 00/01). Record Q&A to `.sage/plan_interview.md`;
   the leader authors 00/01 from it. Skip/shorten if the user already gave rich detail.
   On a resumed session with a user-supplied packet, first run
   `sage context restore --snapshot <path>` and read the generated briefing. A restore
   failure is a hard stop; never fall back to an unverified packet.
   Settle the cycle's document language in the same pass: Phase 00's `Document-Language:`
   line if that document exists, else `document_language` in `.sage/cycle.json`, else ask
   the user and record it with `sage cycle set <stem> --document-language <ko|en>`. Every
   phase document carries that one line outside any code fence and is written in that
   language, fixed for the whole cycle. It is independent of the conversation language —
   see `docs/agent/language-policy.md`.
4. If `knowledge_capture.scan_before_dev: true` and `knowledge_capture.vault_path`
   is set, write the task scope to `.sage/knowledge_query.txt` and run
   `python -m sage knowledge scan --query-file .sage/knowledge_query.txt`. The
   command always refreshes `.sage/knowledge_scan.md` with `status: ran|n/a|error`;
   pass that file to the leader and treat non-`ran` status as "no usable prior
   vault context", not as a blocker.
5. Invoke the `leader` agent to:
   a. Author a plan doc under `paths.plan_docs` that covers the task scope.
      Use one markdown basename as the cycle identity and put the exact same
      `Cycle-Stem: <basename>` declaration once near the top of every 00–02 doc.
   b. Record a filled `Risk Level: Lx` line in the 00 base plan (L1/L2/L3 — the higher
      of the user-declared level and the glob-implied risk; later gates and write-back
      use it as the durable cycle tier). Record exactly one declaration outside code
      fences and never leave the `<L1|L2|L3>` placeholder.
   c. Record `Done-Criteria-Revision: 1` and one exact `## 5. Done Criteria`
      section. Convert the confirmed user outcomes into concrete `[ ]` items; do not
      mark implementation results complete during planning and do not leave TODO.
   d. Distribute file ownership to implementer-a / implementer-b by component.
   e. State the integration point where the two implementers connect.
6. Verify the plan doc exists before handing off:
   check that the file under `paths.plan_docs` is non-empty and references
   the feature scope, and that 00 carries exactly one filled `Risk Level: L[123]`
   line outside code fences (not the `<L1|L2|L3>` placeholder), that the Done Criteria
   contract is valid with revision 1 and at least one concrete `[ ]` item, and that every file basename equals its
   single `Cycle-Stem` declaration — if missing/unfilled/mismatched, block and have the
   leader set it.
7. Report the ownership map to the user and confirm they are ready to proceed
   to implementation via `/sage-team` (or the `/sage-cycle` umbrella).
8. State the phase flow so the user does not misorder 03/04: 00–02 now (leader);
   03 is opened before source edits with file ownership, implementation checklist,
   and Phase-01 acceptance IDs, then completed after code with implementation,
   unit-test, and verification evidence; 04 = leader + qa judge the
   design↔implementation gap, test coverage, and acceptance evidence (no verdict);
   05 = independent reviewer verdict via `/sage-review`; 06 = report only after
   05 records APPROVED.
9. When `context_management.compaction.enabled: true`, after each completed 00, 01,
   and 02 boundary run `sage context snapshot --cycle-stem <stem> --phase <id>` and
   report the packet path. These packets are the only supported cross-session resume
   input; they do not launch or switch hosts.

## advisory_scope
- role_boundary: does not implement code; invokes leader only. Owns 00–02, not 03–06.
- uses: leader agent, project-profile.yaml, AGENT_GUIDE.md
- convention_doc: AGENT_GUIDE.md
- overlay: optional checkout-local shared/personal additions arrive through the current catalog; mandatory CORE/project policy and independent gates remain authoritative

## runtime_bindings
- claude: .claude/skills/sage-plan/SKILL.md (repo — Claude Code auto-discovers)
- codex:  $CODEX_HOME/skills/sage-plan/SKILL.md or .codex/skills/sage-plan/SKILL.md (explicit global or project-local install scope)

## drift_checks
- conformance: procedure step 1 (gate check) and step 5 (leader invocation) must be present

## Delegated worker overlays (separate role packet)

Do not forward the root catalog to workers. When delegating an eligible worker, query that
worker's own kind/id with `sage overlay-local --kind agent --id <worker-id> --root <project-root>`
and pass its validated content and actual target/path/sha256 references in the existing role
packet, alongside the role's shared guidance. Never read raw personal files after a loader error.
For `sage review` / `sage cross-check`, never preappend shared or personal reviewer additions:
the CLI loads them once and emits `SAGE_LOCAL_OVERLAY_REF`. This role-specific CLI path does
not replace automatic delivery of this root skill's shared/personal sources.
