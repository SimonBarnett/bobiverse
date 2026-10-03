<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/job-audit-line.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Job audit line

One append-only file per bridge home: `{BOB_BRIDGE_HOME}\job-audit.jsonl`.

Each line is JSON with:

| Field | Meaning |
|---|---|
| `jobId` | Fleet job id or `loop-<issue>` for build-loop PASS-nits |
| `machine` | Registry id |
| `fuel` | `cursor-models`, `grok-build`, … |
| `model` | Resolved worker model when set |
| `kind` | `build`, `mrb`, `mrb-pass`, … |
| `prUrl` | Open PR when known |
| `mrbIssue` | MRB GitHub issue URL when known |
| `sha` | PR head or merge SHA when known |
| `status` | Outbox completion status or `pass-nits` |
| `time` | UTC ISO timestamp |

Written when a fleet job lands in **outbox** (`Write-BobJobAuditFromPacket`) and when `Start-BobBuildLoop.ps1` sees MRB **PASS-nits**. Tray hover and IRC POINT scraps are not the audit source of truth.
