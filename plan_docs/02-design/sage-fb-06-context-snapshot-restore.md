# [Design] SAGE-FB-06 Context Snapshot/Restore

Cycle-Stem: `sage-fb-06-context-snapshot-restore`

## 1. Packet Envelope

The JSON envelope contains `schema_version`, `created_at`, `snapshot_id`, `payload`, and `integrity_sha256`.
The integrity hash covers the canonical JSON form of `schema_version + created_at + payload`; `snapshot_id` is
derived from that digest. The payload records project identity, cycle/phase, runtime hosts, profile hashes, optional
manifest hash, exact phase document paths/hashes/sizes, and the configured compaction preservation keys.

## 2. Exact Cycle Binding

The command loads only profile-declared PDCA phase globs and selects one document whose filename and exactly one
non-fenced `Cycle-Stem` declaration both equal the requested stem. The requested completed phase must exist. Ambiguous,
missing, unsafe, symlinked, or oversized sources fail closed.

## 3. Manual Host Handoff

Snapshot records both a full profile hash and a semantic profile hash that excludes only `runtime.active_host` and the
legacy `runtime.host` alias. Restore accepts an exact profile match or an active-host-only change. Installed-host intent,
all governance settings, phase documents, and the manifest remain bound. No host process is started and no profile is
rewritten.

## 4. Compaction Consumer

`context_management.compaction` is a closed contract:

```yaml
context_management:
  compaction:
    enabled: true
    preserve: [architectural_decisions, open_bugs, file_ownership, pending_verifications]
    max_snapshot_bytes: 1048576
```

Restore uses the preservation keys to select source phase documents for the briefing. It does not infer semantic facts:
each section carries the exact bound Markdown source and provenance.

| Preservation key | Source phases |
|---|---|
| `architectural_decisions` | 02 |
| `open_bugs` | 04, 05 |
| `file_ownership` | 03 |
| `pending_verifications` | 03, 04, 05 |

The completed phase is always included for continuity. `enabled:false` makes snapshot creation explicitly unavailable;
the setting is therefore no longer an inert advertised feature.

## 5. Storage and Safety

- Packet: `.sage/context/snapshots/<cycle-stem>/<phase>-<snapshot-id>.json`
- Briefing: `.sage/context/restored/<cycle-stem>-<snapshot-id>.md`
- All source/output paths are root-confined and reject symlink ancestors.
- The configured byte budget bounds source documents, packet input, and rendered briefing.
- Restore writes only after all checks pass, using an atomic replace inside the fixed output directory.

## 6. Skill Contract

CORE `sage-cycle`, `sage-plan`, and `sage-team` templates instruct the host to snapshot after a completed phase boundary.
On a resumed session they run restore for the user-supplied packet and read the generated briefing before resolving the
next stage. This is the explicit consumer; SAGE does not pretend compaction settings affect a host automatically.

