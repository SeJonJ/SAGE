# [Analyze] SAGE-FB-06 Context Snapshot/Restore

Cycle-Stem: `sage-fb-06-context-snapshot-restore`

## Design to Implementation Gap

- The implementation follows the separate packet-engine design and leaves the retro `session-start-snapshot`
  unchanged.
- Active-host-only profile drift is accepted only when installed-host intent remains equal; all other profile
  semantics, manifest bytes, and exact phase documents remain hash-bound.
- The packet is a local corruption/staleness detector, not a signature, remote attestation, full source checkpoint,
  or hidden model-memory restore. This boundary is explicit in the installed context guide and briefing.
- Snapshot/restore are explicit skill steps. Automatic host launch, concurrent ownership, and phase switching remain
  out of scope.

## QA Coverage

| Area | Evidence | Result |
|---|---|---|
| Exact cycle/phase selection | every phase through completed boundary, duplicate, filename/declaration binding paths | Covered |
| Packet integrity | payload tamper, rehashed malformed structures, phase-sequence and next-phase recomputation | Covered |
| Parser totality | non-JSON-native YAML scalar fails as controlled `ContextError` | Covered |
| Source staleness | profile semantic, manifest, and phase hash drift | Covered |
| Manual handoff | Claude snapshot -> active Codex restore | Covered |
| Filesystem safety | managed-root confinement, source symlink, root-fd/openat ancestor pinning, secure-open inode/race, output ancestor checks | Covered |
| Bounded input/output | source/packet/briefing byte budget | Covered |
| Compaction consumption | disabled refusal + preserve-index materialization | Covered |
| Markdown materialization | source fence collision | Covered |
| Packaging/regression | official install/generate/validate/hook suite | Covered |
| Independent external review | fresh Claude headless rounds | Covered |

## Acceptance Evidence

| ID | Status | Evidence |
|---|---|---|
| FB06-AC1 | PASS | `sage context snapshot` requires every declared phase through the boundary and writes one exact-stem/phase JSON packet. |
| FB06-AC2 | PASS | packet binds profile, optional manifest, and phase path/hash/size. |
| FB06-AC3 | PASS | restore validates envelope and recomputed profile phase sequence/glob/stem/next-phase bindings before creating output. |
| FB06-AC4 | PASS | active-host-only semantic normalization test passes; other profile drift fails. |
| FB06-AC5 | PASS | implementation has no host subprocess or profile/phase write path. |
| FB06-AC6 | PASS | profile contract is closed and `enabled`/`preserve` drive commands/rendering. |
| FB06-AC7 | PASS | malformed, duplicate, symlink, out-of-root, tamper, and size tests pass. |
| FB06-AC8 | PASS | briefing path plus resume/snapshot rules are wired into CORE cycle skills. |
| FB06-AC9 | PASS | no `session_start_snapshot_core.py` or its hook spec change. |
| FB06-AC10 | PASS | Three fresh Claude rounds plus closure review completed with findings triaged. |

## Verification

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD /opt/homebrew/bin/python3 scripts/sage_harness/hooks/tests/test_context.py`:
  15 passed.
- Context + `test_profile_validate`: 132 passed.
- `PATH=/opt/homebrew/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD bash scripts/sage_harness/hooks/tests/run-all.sh`:
  `ALL HOOK TESTS PASS`.
- `git diff --check`: pass.

No Phase-05 verdict is issued here.

## Broad External Review Round 3 Triage

Claude session `a01c9b7a-ee27-483b-9650-bd836aa264ca`의 integrity 용어 지적은 기존 Gap Analysis 경계와
일치한다. Unkeyed SHA는 packet corruption을 탐지하고, 재해시된 변조를 거부하는 근거는 restore가 current
profile/manifest/phase sequence와 hashes를 다시 계산하는 데 있다. Docstring만 이 신뢰 경계에 맞게 교정했다.

## External Review Closure

Fresh closure session `ead09722-14af-4538-b8b0-155761c95973` marked FB06 CLEAN. The packet remains a
local corruption/staleness detector whose trust comes from rebinding current profile, manifest, and phase sources;
it is not represented as a remote attestation.
