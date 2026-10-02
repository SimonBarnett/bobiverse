# Airc remote control (protocol sketch)

See **[feature-request-airc-remote-control-2026-10-01.md](./feature-request-airc-remote-control-2026-10-01.md)** for LOCKED success metrics.
Ops: **[airc-ops.md](./airc-ops.md)**. Helper: **`scripts/Invoke-AircRemote.ps1`** (FR #76).

## Shipped verbs

| Verb | Level | Purpose |
|------|-------|---------|
| plain / `cmd:` / `psb64:` | shell (FR #75) | Oneshot PowerShell/COMSPEC; `DONE id= exit=` |
| `STATUS` | read | `STATUS machine=… airc=Running|Stopped bob=… airc_ver=… jeeves=…` |
| `PUT` / `CHUNK` / `PUTEND` | write | Sandboxed file write under `<ConsoleHome>/drop` + durable job under `jobs/<id>/` |
| `RUN` | exec | Execute ready PUT path; emit `out`/`err`/`DONE` |
| `GET` | read | Job or file metadata (+ short head) |
| `JOB` | read | `JOB id=… state=… exit=…` |
| `CANCEL` | exec | Cancel receiving/ready/running job |

### Authorization matrix (FR #78)

All verbs require base console auth (`bob-*` / operators / accounts). Additionally:

| Level | Verbs | Default |
|-------|-------|---------|
| read | STATUS, GET, JOB | any authenticated nick |
| write | PUT, CHUNK, PUTEND | any authenticated nick (optional allowlist via `VerbAuthPolicy.write_nicks`) |
| exec | RUN, CANCEL | any authenticated nick (optional `exec_nicks`) |

Do not treat shell access as automatic PUT/RUN permission when allowlists are configured.

### Limits / durability

- Max PUT size 256 KiB; chunk raw ≤ 300 bytes; retain ≤ 64 jobs; age retention 7 days.
- Jobs survive Airc restart; `running` at restart → `failed` (`interrupted by restart`).
- Reject `..`, absolute escape, and secret names (`*.password`, `identity.json`, …).

## Helper

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-AircRemote.ps1 -SelfTest
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-AircRemote.ps1 `
  -MachineId <id> -Action Put -LocalFile .\x.ps1 -Path scripts\x.ps1 -Outbox <ear-outbox>
```

## CAST IRON

- Detached `Update-BobiverseService.ps1` for MSI (FR #77); never inline msiexec over live airc.
- ConsoleHome never `C:\Users\Default\.airc`.
