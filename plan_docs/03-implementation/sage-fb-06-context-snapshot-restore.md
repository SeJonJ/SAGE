# [Implementation] SAGE-FB-06 Context Snapshot/Restore

Cycle-Stem: `sage-fb-06-context-snapshot-restore`

## Ownership

| Owner | Files |
|---|---|
| SAGE implementation | `sage/context_packet.py`, `sage/commands/context.py`, `sage/cli.py` |
| Profile contract | `schema/profile.schema.json`, `sage/profile_validate.py`, `templates/project-profile.yaml` |
| Host workflow | `templates/core/skills/sage-{cycle,plan,team}.md`, Claude CORE mirrors, framework docs |
| QA | `scripts/sage_harness/hooks/tests/test_context.py`, `test_profile_validate.py`, `run-all.sh` |

## Checklist

- [x] Write failing CLI/packet/profile tests.
- [x] Implement structured snapshot and integrity-bound restore.
- [x] Enforce exact cycle, path, symlink, root-fd/openat ancestor, secure-open inode, size, profile, manifest, and phase bindings.
- [x] Require every declared phase document through the completed boundary before snapshotting.
- [x] Recompute the completed phase sequence, globs, cycle stem, and next phase during restore.
- [x] Consume compaction preservation settings in the restored briefing.
- [x] Wire CLI, schema, template profile, docs, and resumable CORE skills.
- [x] Run focused tests and the official hook suite.
- [x] Record acceptance evidence in Phase 04.
- [x] Complete three fresh Claude review rounds before Phase 05 approval.

## Verification Plan

- Focused unittest module for happy path, same-host restore, active-host handoff, tamper/drift, disabled config,
  malformed profile, unsafe/symlink path, duplicate cycle document, and size budget.
- Profile schema/semantic tests for closed keys and value types.
- Official `scripts/sage_harness/hooks/tests/run-all.sh` regression.

## Implementation Evidence

- Added `sage/context_packet.py` and `sage/commands/context.py`; registered `sage context` in `sage/cli.py`.
- Closed and validated `context_management.compaction` in both JSON Schema and schemaless semantic validation.
- Updated template profile, README/artifact map, framework guide, context guide, and both CORE skill source forms.
- TDD RED evidence: missing module; malformed cycle/runtime parser traceback; colliding Markdown fence; malformed
  project/runtime profile; non-JSON-native YAML scalar traceback; source replacement between metadata check and open;
  ancestor replacement with an out-of-root symlink between path validation and open; missing Phase 01 at a declared
  Phase 02 completion boundary; rehashed packet removal of Phase 01 and rehashed `next_phase` tampering.
  Each was reproduced before the corresponding implementation.
- Focused: `15 tests`, all pass.
- Context + profile validation aggregate: `132 tests`, all pass.
- Official hook suite: `ALL HOOK TESTS PASS` including section 49.
- `python -m py_compile`: pass. `python -m json.tool schema/profile.schema.json`: pass.

## Broad External Review Round 3

- Reviewer: Claude headless session `a01c9b7a-ee27-483b-9650-bd836aa264ca`.
- 수용(문서 P3): packet SHA는 손상 감지이며 단독 위조 방지 서명이 아니다. Snapshot docstring을
  corruption detection과 restore 시 live repository source binding 재검증으로 정확히 표현했다.
- Context focused `15 tests`가 PASS했고 동작 계약은 변경하지 않았다.
