# [Plan] SAGE-FB-06 Context Snapshot/Restore

Cycle-Stem: `sage-fb-06-context-snapshot-restore`

## Requirements

| ID | Requirement | Required |
|---|---|:---:|
| FB06-AC1 | `sage context snapshot` writes a structured packet for one exact `Cycle-Stem` and completed phase. | Yes |
| FB06-AC2 | The packet binds profile, manifest when present, and exact phase documents by SHA-256. | Yes |
| FB06-AC3 | `sage context restore` verifies envelope integrity and every source binding before writing a briefing. | Yes |
| FB06-AC4 | Manual host handoff may change only the active-host alias while other profile semantics remain bound. | Yes |
| FB06-AC5 | Snapshot/restore never launches a peer host or mutates phase documents/profile. | Yes |
| FB06-AC6 | `compaction.enabled` and `preserve` are validated and consumed by the engine; disabled means no snapshot creation. | Yes |
| FB06-AC7 | Paths, symlinks, file sizes, duplicate cycle documents, and malformed packets fail closed. | Yes |
| FB06-AC8 | Restored briefings are written under `.sage/context/restored/` and CORE cycle skills require reading them on resume. | Yes |
| FB06-AC9 | The retro session-start baseline remains unchanged and separately named. | Yes |
| FB06-AC10 | Three independent Claude review rounds accept the implementation or findings are triaged and reworked. | Yes |

## User Workflow

```text
sage context snapshot --cycle-stem <stem> --phase 02
# user changes runtime.active_host and opens the other installed host
sage context restore --snapshot .sage/context/snapshots/<stem>/<packet>.json
# resumed SAGE skill reads the printed briefing path before continuing
```

The commands operate on durable repository files. They make no claim to restore hidden LLM memory.

