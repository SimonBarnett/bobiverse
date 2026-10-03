<!-- ARCHIVED COPY - source: SimonBarnett/gh-Jeeves @ 4ff29b5, path docs/feature-request-ack-done-busy-idle-fr161-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #161: ACK/DONE drive deterministic worker busy-idle digest state

## Shape

On **ACK**, each worker digest entry (top-level and `machines.<id>.workers[nick]`) carries:

| Field | Meaning |
|-------|---------|
| `state` | `busy` |
| `repo` | owner/name |
| `kind` | `FR` / `MRB` / `UAT` |
| `id` | `#n` |
| `ref` | `repo#n` |
| `title` | issue/PR title (from queue `line`/`title`) |
| `job` | legacy string `repo KIND #n` |

On **DONE**, the same entry returns to **idle** with task fields cleared (`job`/`repo`/`kind`/`id`/`ref`/`title` null). Idle holds until the next ACK — GET heal must not resurrect the prior task.

## Tests

`tests/test_ack_done_busy_idle_fr161.py`
