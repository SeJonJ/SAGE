---
id: sage-profile-modify
kind: skill
# CORE skill (neutral). Project specifics come from profile, not this spec.
# CORE framework bootstrap asset: hand-shipped by `sage install`, NOT manifest-tracked.
# The manifest/claims/validate loop is reserved for project-authored skills
# (spec + claims + render hash) created via the generate/extract flow.
---
## intent
Modify an already-bootstrapped sage/project-profile.yaml through conversation: read the
current value, propose a diff, WARN about governance-gate consequences, edit the YAML
directly (profile is hand-authored SSOT); then compile its generated runtime JSON
and re-validate. Generation does not author the YAML. The profile-editing counterpart to /sage-init (first authoring) and
/sage-asset (assets).

## when_to_use
- After bootstrap, to change profile values: risk tiers, verification commands, the
  Phase-05 review loop (review_loop), vault outputs, components, options
- When tuning review_loop or pdca.fast_cycle rounds/lenses, or toggling vault outputs
- When the user says "/sage-profile-modify", "change the profile", "루프 설정 바꿔",
  "리뷰 루프 수정", "risk 글롭 수정", "profile 수정"

## procedure
0. Resolve the conversation language once: an explicit `--lang ko|en` on this skill's
   invocation, then `interface.language` in `sage/project-profile.local.yaml`, then `ko`.
   Every question, proposal, progress note, warning and summary uses it; machine values
   and Phase 00–06 `Document-Language:` prose do not. Document prose includes section headings
   and list labels, except `## 5. Done Criteria` and `## 6. Done Criteria Revision Log`, which a
   parser reads by their exact string. See `docs/agent/language-policy.md`.
1. Read context: profile (if not bootstrapped — project.name empty OR risk globs and
   components both unset, the same predicate sage generate enforces → route to /sage-init,
   do not bootstrap here), AGENT_GUIDE, bootstrap-authoring (incl. shared Review loop +
   vault interview set).
2. Identify the target section (project/components including `runtime_models`/
   verification/risk/pdca.base_plan/pdca.review_loop/pdca.fast_cycle/options/knowledge_capture/file_type_map/compliance/
   `governance_docs`/`cross_model.reviewer`). For model edits, run `sage models --host <host>`
   and preserve its verification label; `cross_model.reviewer.host` scopes which peer the model
   was chosen for (the reviewer itself is resolved at run time) and must be an installed host
   other than a pinned `runtime.active_host`.
   `governance_docs` renders into the AGENT_GUIDE routing block (path + label only, never
   classification triggers).
3. For pdca.base_plan, pdca.review_loop, pdca.fast_cycle, and vault outputs, drive the SAME shared interview set as
   /sage-init (bootstrap-authoring.md) — single source, no drift. Vault turn only when
   the matching feature is on AND an effective vault path is set. Fast keeps
   reason_required=true and engine floors of one round and two lenses.
4. Propose before→after diff and **state the gate consequence** in plain terms
   (loosen/tighten); get explicit approval. (Consequence warnings are mandatory.)
5. Edit profile.yaml in place — change only approved values, never add/remove schema keys.
6. After saving shared YAML, hand off to a terminal outside the guarded AI session,
   in this project root: `sage generate --kind hook --write --target <claude|codex|both>`
   using the already installed host target (both for cross-model projects). This compiles
   runtime JSON; never edit JSON directly. Then, if `governance_docs` or `risk.domains`
   changed, run `sage sync-overlays` there to refresh routing. Run
   `sage validate --schema --kind all` and `sage doctor`; never bypass a FAIL.
   The next session boundary must validate the repaired state before guarded work resumes.
   A rejected in-session Bash call cannot perform this external recovery.
   components[] changes may also need `sage generate --kind roster` — an asset step.

## advisory_scope
- role_boundary: edits YAML (SSOT) directly; generate only compiles derived runtime artifacts;
  does not add/remove schema keys; does not bypass a validate FAIL; does not bootstrap
  (routes to /sage-init when unbootstrapped)
- uses: sage sync-overlays (routing-block source edits) / sage validate / sage doctor,
  bootstrap-authoring.md (shared interview set)
- convention_doc: AGENT_GUIDE.md
- self_overlay: unsupported; this gate-bearing CORE skill is not in `COMPOSE_ALLOWED`

## runtime_bindings
- claude: .claude/skills/sage-profile-modify/SKILL.md (repo — Claude Code auto-discovers)
- codex:  $CODEX_HOME/skills/sage-profile-modify/SKILL.md or .codex/skills/sage-profile-modify/SKILL.md (explicit global or project-local install scope)

## drift_checks
- conformance: procedure step 4 (consequence warning + approval) and step 6 (sage validate re-run) must be present
