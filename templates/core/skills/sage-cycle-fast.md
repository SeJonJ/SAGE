---
id: sage-cycle-fast
kind: skill
---
## intent
Delegate a complete explicitly enabled Fast Cycle to sage-plan-fast and sage-team-fast without duplicating their state transitions.
## when_to_use
- When the user explicitly requests the profile-enabled Fast Cycle for an L2/L3 change.
## procedure
1. Confirm shared policy enables Fast Cycle and resolve the current cycle state.
2. Delegate composite planning and audit open to `sage-plan-fast`.
3. Delegate implementation, review, completion evidence, audit close, and cycle clear to `sage-team-fast`.
## advisory_scope
- self_overlay: unsupported; Fast state transitions are gate-bearing and have no independent overlay oracle.
## runtime_bindings
- claude: .claude/skills/sage-cycle-fast/SKILL.md
- codex: $CODEX_HOME/skills/sage-cycle-fast/SKILL.md or .codex/skills/sage-cycle-fast/SKILL.md
