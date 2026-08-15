---
id: sage-plan-fast
kind: skill
---
## intent
Collect all mandatory Fast inputs, author the composite 00 through 04 plan, and open a bound audited Fast run before source edits.
## when_to_use
- When an enabled Fast Cycle needs its mandatory inputs and composite Phase 00 before implementation.
## procedure
1. Collect Fast level, lens count, and one-line reason before any write; classify actual L2/L3 risk separately.
2. Author one composite Phase 00 with `Done-Criteria-Revision: 1`, a concrete
   `### Done Criteria` list of `[ ]` outcomes, exact embedded Phase 00 through 04
   sections, the separate Document Mapping checklist, and acceptance trace.
   Settle the cycle's document language in the same pass: Phase 00's `Document-Language:`
   line if that document exists, else `document_language` in `.sage/cycle.json`, else ask
   the user and record it with `sage cycle set <stem> --create --document-language <ko|en>`.
   The composite document carries that one line outside any code fence and is written in
   that language, fixed for the whole Fast run — see `docs/agent/language-policy.md`.
3. Declare the verified stem and run `sage fast-cycle open`; hand off only after its audit run is bound.
## advisory_scope
- self_overlay: unsupported; Fast state transitions are gate-bearing and have no independent overlay oracle.
## runtime_bindings
- claude: .claude/skills/sage-plan-fast/SKILL.md
- codex: $CODEX_HOME/skills/sage-plan-fast/SKILL.md or .codex/skills/sage-plan-fast/SKILL.md
