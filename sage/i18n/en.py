"""CLI English catalog.

Key set and named placeholders must match `ko.py` exactly; `validation.py` enforces that at
build time. A key present in one catalog and absent in the other is a build failure rather than
a runtime fallback, because a fallback would ship the gap to users instead of surfacing it.
"""

MESSAGES = {
    "cli.root.description": (
        "SAGE installs and verifies rule files, hooks and agent specs in a Claude or Codex project."
    ),
    "cli.root.epilog": (
        "Typical order:\n"
        "  1. sage install --host codex --skill-scope project-local\n"
        "                                     # or --skill-scope global\n"
        "  2. sage generate --kind hook --write\n"
        "  3. sage validate\n"
        "\n"
        "Options for a single command:\n"
        "  sage <command> --help\n"
    ),
    "cli.root.help_option": "show this help message and exit",
    "cli.root.version_option": "show the installed SAGE version",
    "cli.root.lang_option": "choose the output language (default: ko)",
    "cli.root.positionals_title": "commands",
    "cli.root.optionals_title": "options",
    "cli.root.switch_hint": "한국어 도움말: sage --help",

    "cli.lang.unsupported": "Unsupported language: {value}. Available: {supported}",
    "cli.lang.missing_value": "--lang needs a value. Available: {supported}",
    "cli.lang.duplicated": "--lang may be given only once",
    "cli.lang.local_invalid": (
        "The local profile's interface.language could not be read, so output stays in Korean — "
        "check {path}"
    ),

    # EH-13 drift 진단. 라벨만 번역하고 논리 경로·건수·구분자는 언어와 무관하게 같다 —
    # 값이 달라지면 같은 drift 가 언어마다 다른 증거로 보인다.
    "cli.drift.changed": "changed",
    "cli.drift.added": "added",
    "cli.drift.removed": "removed",
    "cli.drift.more": " and {count} more",
    "cli.drift.part": "{label} {count}: {shown}{more}",

    # 각 명령의 argparse help/description. `--lang en --help` 가 실제로 영어를
    # 내려면 루트 help 만으로는 부족하다 — 사용자가 보는 화면은 하위 명령 쪽이다.

    "cli.absorb.absorb": "Turn hand-edited generated files back into proposed spec changes",
    "cli.absorb.from_blocked_diff": "Convert a diff blocked by the write guard straight into a patch candidate, without re-entering it",
    "cli.absorb.from_retro": "Read approved (approved:true) retro human-gate notes and turn the proposals into asset patch candidates (Loop C)",
    "cli.absorb.claude": "(agent/skill) path to the modified .claude artifact",
    "cli.absorb.codex": "(agent/skill) path to the modified .codex artifact",
    "cli.absorb.guide": "(agent/skill) AGENT_GUIDE path",

    "cli.acceptance_waiver.acceptance_waiver": "Explicitly record a deferral of operational verification for one L3 acceptance",
    "cli.acceptance_waiver.grant": "Issue a waiver for an exact cycle and required acceptance ID",
    "cli.acceptance_waiver.confirm_user": "The user who approved this explicitly (a local self-asserted audit record, not proof of remote identity)",
    "cli.acceptance_waiver.ttl": "Validity period, at most 24h (default 24h)",
    "cli.acceptance_waiver.list": "Show the waiver audit and the currently active grants",
    "cli.acceptance_waiver.revoke": "Explicitly revoke an active waiver",

    "cli.asset_check.asset_check": "Split framework assets into those that can pass automatically and those needing human review (formerly sage review)",
    "cli.asset_check.batch": "Summarize the auto bucket in one line",
    "cli.asset_check.gate": "Exit 1 if the review bucket is non-empty (CI gate)",

    "cli.authority.authority": "Verify base/head policy and exact PDCA evidence in protected CI",
    "cli.authority.inspect": "Read the base/head git objects and compute the authority decision",
    "cli.authority.attest": "HMAC-sign the claims of a protected CI decision",
    "cli.authority.gate": "Verify the authority decision and its binding to the protected attestation",
    "cli.authority.root": "A git repository containing the base/head objects",
    "cli.authority.issuer": "For gate, the expected attestation issuer",

    "cli.change.change": "Suggest which SAGE command handles the change you want to make",
    "cli.change.intent": "e.g. \"fix the capture-declared-risk hook\"",

    "cli.context.context": "Save a context packet at a phase boundary and restore it with verification",
    "cli.context.snapshot": "Save a structured context packet for a completed phase",
    "cli.context.phase": "A completed phase id declared in the profile's pdca.phases",
    "cli.context.restore": "Verify the packet/source binding, then produce a resume briefing",
    "cli.context.snapshot_2": "Path to the managed snapshot JSON",

    "cli.cycle.cycle": "Tell the gates which cycle you are working on",
    "cli.cycle.stem": "The Cycle-Stem to set",
    "cli.cycle.create": "Create a Phase 00 skeleton, then declare the stem",
    "cli.cycle.risk": "Risk level for the Phase 00 created by --create",
    "cli.cycle.path": "Directory, relative to the project root, to create Phase 00 in",
    "cli.cycle.root": "Target project root (default: the nearest SAGE installation above cwd)",
    "cli.cycle.document_language": "Language this cycle's 00-06 documents are written in (default: the display language)",

    "cli.doctor.doctor": "Check the tools and review settings SAGE needs to run",
    "cli.doctor.profile": "Path to project-profile.yaml (falls back to the templates default)",

    "cli.fast_cycle.fast_cycle": "Start, verify and close a shortened PDCA Fast Cycle audit",
    "cli.fast_cycle.open": "Bind a composite Fast Plan to an audit run",
    "cli.fast_cycle.review": "Bind an APPROVED Loop Audit to a Fast run",
    "cli.fast_cycle.close": "Verify the approval and report evidence, then close the Fast run",
    "cli.fast_cycle.abort": "Abort the active Fast run, recording a reason",
    "cli.fast_cycle.show": "Show a summary of the Fast Cycle audit",

    "cli.feedback.feedback": "Scan for sage-feedback markers and show them",
    "cli.feedback.root": "Project root (default: the closest parent directory holding a profile)",
    "cli.feedback.blocking_only": "Show only blocking (!sage-feedback) markers",
    "cli.feedback.exit_code": "Exit 2 when unresolved blocking markers exist (for scripts and CI)",
    "cli.feedback.release_gate": "Exit 2 on unresolved blocking markers only when feedback.block_release is true (release CI always calls this; the profile decides)",
    "cli.feedback.record": "Record the outcome for one marker (requires --path/--line/--verdict/--note)",
    "cli.feedback.path": "--record: repository-relative path the marker was on",
    "cli.feedback.line": "--record: line number of the marker",
    "cli.feedback.verdict": "--record: one of three verdicts (fixed | intentional = not a mismatch | undetermined = cannot decide, marker kept)",
    "cli.feedback.note": "--record: one line of reasoning (which part of the plan document this refers to)",
    "cli.feedback.cycle_stem": "--record: stem of the cycle that produced the code (the vault note unit)",
    "cli.feedback.vault": "--record: vault path override (defaults to the profile's vault_path)",

    "cli.generate.generate": "Read spec files and generate configuration files for Claude and Codex",
    "cli.generate.id": "A single asset (omit for the whole kind; roster is derived from profile.components)",
    "cli.generate.write": "Write files (omit for a dry-run preview)",
    "cli.generate.target": "Runtime to register for (both requires cross_model on)",
    "cli.generate.dest": "Root to write registration artifacts into (default: cwd)",
    "cli.generate.root": "SAGE root (used to locate the manifest)",
    "cli.generate.from_existing": "(--kind roster) Seed a new implementer-<component> identity from an existing implementer's render plus project overlay (create-only). Example: implementer-a",
    "cli.generate.deploy_codex": "(--kind skill) Deploy the canonical repo .codex/skills to the global $CODEX_HOME/skills under a prefix namespace. Codex does not auto-discover repo-scoped skills, so a global deploy is required to invoke them. Explicit opt-in, to keep environment side effects separate.",

    "cli.install.install": "Install the SAGE base files into the current project",
    "cli.install.help": "show this help message and exit",
    "cli.install.host": "The AI tool to install SAGE for: claude or codex (required)",
    "cli.install.prefix": "Asset naming prefix (optional, default: sage)",
    "cli.install.dest": "Target project root to install into (optional, default: the current directory)",
    "cli.install.force": "Overwrite existing files (default: skip)",
    "cli.install.skill_scope": "codex host: explicitly choose where CORE skills are installed (required: global or project-local)",
    "cli.install.no_global_skill": "DEPRECATED codex CI/sandbox compatibility: skip CORE skill installation entirely",

    "cli.knowledge.knowledge": "Look up an Obsidian vault before development and update it afterwards",
    "cli.knowledge.scan": "Look up related vault notes before development and refresh .sage/knowledge_scan.md",
    "cli.knowledge.query": "Description of the task or feature to look up",
    "cli.knowledge.query_file": "File to read the query from (avoids injecting free text as a shell argument)",
    "cli.knowledge.profile": "Path to project-profile.yaml",
    "cli.knowledge.vault": "Vault path override. Without a path, profile.knowledge_capture.vault_path is used",
    "cli.knowledge.limit": "Maximum number of results (default 8)",
    "cli.knowledge.root": "Project root override",
    "cli.knowledge.write_back": "Update the vault note and wiki/log.md after development is finished",
    "cli.knowledge.title": "Title of the note to write",
    "cli.knowledge.summary": "Summary body",
    "cli.knowledge.summary_file": "File to read the summary body from (avoids injecting free text as a shell argument)",
    "cli.knowledge.profile_2": "Path to project-profile.yaml",
    "cli.knowledge.vault_2": "Vault path override. Without a path, profile.knowledge_capture.vault_path is used",
    "cli.knowledge.prefix": "Note prefix (default TECH)",
    "cli.knowledge.tags": "Comma-separated tags, supplied by the host per the vault authoring guide (default tech,sage,knowledge-capture)",
    "cli.knowledge.append_log": "Append a wikilink line to wiki/log.md",
    "cli.knowledge.skip_structure_check": "Turn off the advisory required_structure skeleton check, for notes that are not deep-skeleton material (minor L1 notes, planning interviews). The host judges the risk tier and note kind; the CLI only reflects that decision deterministically (the SAGE boundary)",
    "cli.knowledge.root_2": "Project root override",

    "cli.models.models": "Show the host model candidates and where they were verified from",
    "cli.models.codex_home": "Codex cache root (default: CODEX_HOME or ~/.codex)",

    "cli.override.override": "Temporarily allow blocked work, recording a reason and a time limit",
    "cli.override.reason": "Reason for the override (required for grant, and audited)",
    "cli.override.ttl": "Validity period: 30m | 2h | 1d | 90s | 1800 (seconds)",
    "cli.override.list": "Active overrides plus a recent audit summary",
    "cli.override.revoke": "Revoke an active grant before it expires (the id from --list)",
    "cli.override.root": "Target project root (default: cwd)",

    "cli.retro.retro": "Turn review-cycle learning into proposed asset improvements (Loop C; nothing is applied automatically)",
    "cli.retro.run_id": "Target loop_audit run_id (default: the latest)",
    "cli.retro.feature": "Cycle stem, used to filter 05 document paths and to title the human-gate note. Example: loop-engineering",
    "cli.retro.vault": "Write a human-gate note (approved:false) to the Obsidian vault. Without a path, profile.knowledge_capture.vault_path is used",
    "cli.retro.no_vault": "Skip the vault note for this run only, even when the retro_note flag is on. Takes precedence over --vault",
    "cli.retro.check": "Deterministically check that the retro note was actually filled in (non-zero for an empty template or invalid proposals). With --run-id, also check the note belongs to that run",

    "cli.review.review": "Phase 05 same-runtime review (the cross_model=false path)",
    "cli.review.packet_file": "Review packet (phase documents plus changed files), passed to the active host over headless stdin",
    "cli.review.host": "The currently active host. Execution is blocked if this conflicts with the profile value",
    "cli.review.cross_check": "Phase 05 cross-model review, calling the opposite runtime's CLI directly",
    "cli.review.packet_file_2": "Review packet file (change diff plus 05 context) — the prompt handed to the peer",
    "cli.review.host_2": "The host currently running. Required when environment detection is ambiguous, such as nested execution",
    "cli.review.strict": "Backward-compatibility flag. A reviewer failure is BLOCKED/non-zero regardless of configuration",

    "cli.review_loop.review_loop": "Record and inspect the round audit for Loop A (Phase 05 adversarial review)",
    "cli.review_loop.open": "Record the start of a loop and print the run_id",
    "cli.review_loop.risk": "Risk tier (the loop covers L2/L3 only)",
    "cli.review_loop.run_id": "Explicit run_id (default: issued automatically)",
    "cli.review_loop.reviewer_requested": "The intended reviewer mode (e.g. cross_model|same_runtime). Compared against close's --reviewer-actual to detect degradation",
    "cli.review_loop.cycle_stem": "Exact cycle stem, for Fast Cycle binding",
    "cli.review_loop.lenses": "Comma-separated lens list, for Fast Cycle binding",
    "cli.review_loop.round": "Record one round (find/refute/rework counts)",
    "cli.review_loop.found": "Number of FIND results",
    "cli.review_loop.survived": "Number that survived REFUTE",
    "cli.review_loop.accepted": "Number accepted for REWORK",
    "cli.review_loop.arch": "Number of architecture escalations",
    "cli.review_loop.tokens": "Cumulative tokens",
    "cli.review_loop.lens_receipts": "Comma-separated receipts for the lenses actually completed this round",
    "cli.review_loop.close": "Record the end of a loop (result/reason/iterations)",
    "cli.review_loop.reviewer_actual": "The reviewer mode actually used (e.g. cross_model|same_runtime). Differing from open's --reviewer-requested marks the loop degraded",
    "cli.review_loop.show": "Loop audit summary plus an integrity check. With --vault, also write an Obsidian dashboard note",
    "cli.review_loop.run_id_2": "A specific run_id (omit for the overall summary)",
    "cli.review_loop.vault": "Write an Obsidian vault dashboard. Without a path, profile.knowledge_capture.vault_path is used",
    "cli.review_loop.next": "Deterministic continue/stop recommendation from the recorded rounds and the profile config (not audited)",

    "cli.sync_overlays.sync_overlays": "Re-materialize the managed blocks of CORE renders after an overlay edit",
    "cli.sync_overlays.root": "SAGE repository root (default: discovered from cwd)",

    "cli.validate.validate": "Check whether specs and generated files have drifted apart",
    "cli.validate.check": "Staleness only (skips regression; for fast CI and hooks)",
    "cli.validate.schema": "Structurally validate the manifest against its JSON Schema (jsonschema is an optional dependency; WARN and skip if absent)",
    "cli.validate.strict": "Promote WARN to FAIL for check-ids on the safe allowlist (for CI asset integrity)",
    "cli.validate.id": "Check a single asset",
    "cli.validate.root": "SAGE repository root (default: discovered from cwd)",

    # 정적 추출이 놓친 자리 — f-string 과 파서 속성 직접 대입.
    "cli.override.gate": "Target gate ({gates}). Default: all",
    "cli.install.optionals_title": "options",
    "cli.review.timeout": "Headless call timeout in seconds (default {default})",
    "cli.review.timeout_peer": "Peer call timeout in seconds (default {default})",
}
