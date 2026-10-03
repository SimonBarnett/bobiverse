<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mode3-dumb-ops.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Mode 3 DUMB operator guide (exec ergonomics)

**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/2  
**Feature request:** `docs/feature-request-mode3-dumb-exec-ergonomics-2026-09-19.md`  
**Protocol reference:** `scripts/dumb_agent.py` (Python); `src/dumb_dotnet/airc-dumb.exe` (net45 adapter)

Thin jail hosts run a DUMB v1 connector with `--allow-path` (Mode 3 default often `C:\airc\jail`). Operators on `--operators` send sealed jobs on the channel. On join and every 10 minutes the connector announces **CAPA**, for example:

`CAPA v1 dumb nick=… verbs=ping,sysinfo,exec,get,put psk=… agpk=0 jail=C:\airc\jail`

This document lists exec policy and recipes so long HTTPS installs do not fight argv rules.

## Allowlisted binaries (argv0)

Default allowlist (case-insensitive basename of argv[0]):

| Binary |
|--------|
| `cmd.exe` |
| `powershell.exe` |
| `hostname.exe` / `hostname` |
| `ipconfig.exe` / `ipconfig` |
| `whoami.exe` / `whoami` |

Extra names: connector flag `--allow-bin` (comma-separated). CAPA does not enumerate bins; treat this table as canonical.

## Meta characters in exec argv

These characters anywhere in the joined argv string are rejected on **`airc-moot-thin.exe`** (Mode 3 C thin has no `--allow-meta` flag):

`&` `|` `>` `<` `^`

**Result error:** `meta` (not `bin`).

On **`scripts/dumb_agent.py`** and **`airc-dumb.exe` (net45)** only, you may start the connector with **`--allow-meta`** to permit those characters in argv. Mode 3 field thins do not expose that escape hatch; use **`put`** + **`Start-Process`** in a jail script instead of `&` on the exec line.

**Recipe without `&`:** `put` a small `.ps1` into the jail, then exec:

`powershell.exe -File .\launcher.ps1`

Put HTTPS URLs, pipes, and `Start-Process` in the **file body**, not in exec argv.

## Path jail (including the `//` trap)

Exec rejects argv or `cwd` when the joined argv contains:

- `..`
- `\\` (UNC)
- `//` (forward-slash UNC or **any** double slash)

**Result error:** `jail`.

**Important:** A literal `https://…` URL in exec argv contains `//`, so it is rejected as **`jail`**, not as a separate URL policy. Do not pass download URLs on the exec command line.

`get` / `put` paths also reject leading `\\` or `//` and must resolve under `--allow-path`. Secret filenames (`identity.json`, `connector.key`, `peers.json`) are always denied.

## Exec timeout

`timeout_s` on exec jobs is clamped to **1–60** seconds. Long installs will hit **`timeout`** if you run the installer synchronously in one exec.

**Pattern: put → spawn → poll**

1. **`put`** installer script(s) into the jail (prefer `put` over IRC `echo >>` chunking).
2. **`exec`** a short launcher, e.g. `powershell.exe -File .\spawn.ps1`, where the script uses `Start-Process` (or similar) to detach the real work and writes a log under the jail.
3. **`get`** the log file (or **`exec`** `type log.txt` via `cmd.exe /c` with a **relative** jail path) until the log shows success or failure.

Repeat **`get`** on the same path; no need for another long exec if output is in a file.

Large stdout/stderr from a single exec may be truncated (`truncated: true`); full output spills to `%AGENTIC_IRC_HOME%\dumb\results\<job-id>.txt` on the thin.

## Operator-facing exec errors

| `error` | Meaning |
|---------|---------|
| `empty_argv` | Exec job had no argv |
| `bin` | argv[0] not on the allowlist |
| `meta` | Disallowed shell metacharacter in joined argv (C thin always; Python/net45 unless `--allow-meta`) |
| `jail` | Path escape, UNC, `//` in argv, bad `cwd`, or blocked file name |
| `busy` | Another exec is in flight |
| `timeout` | Subprocess exceeded `timeout_s` |
| `operator` | Sender not in `--operators` |

## Cookbook: HTTPS payload on an elder thin (flamingo-scale)

Goal: run a vendor silent installer fetched over HTTPS without putting the URL in exec argv.

1. **`put`** `fetch-and-run.ps1` into the jail. Example structure (edit URLs/paths for your payload):

```powershell
$log = Join-Path $PSScriptRoot 'install.log'
$url = 'https://example.com/vendor/setup.exe'
$dest = Join-Path $PSScriptRoot 'setup.exe'
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
  Start-Process -FilePath $dest -ArgumentList '/S' -Wait -RedirectStandardOutput $log -RedirectStandardError $log
  'exit=' + $LASTEXITCODE | Out-File -Append $log
} catch {
  $_ | Out-File -Append $log
  exit 1
}
```

2. **`exec`** `powershell.exe -File .\fetch-and-run.ps1` with `timeout_s` at most 60. If the script only **starts** detached work and returns, use a shorter inner script that only `Start-Process`s without `-Wait`, then poll the log.

3. **`get`** `install.log` (path relative to jail) until lines show completion.

For Grok Bot–style silent `/S` installs, same pattern: URL and `/S` live only in the put file.

## `put` size and assembly

- Prefer **`put`** (base64 in the sealed job) over pasting script bytes through IRC exec.
- **`get`** returns base64 for files up to **12 KiB** inline; larger files return sha256 only (use spill paths or split artifacts).
- Multi-part payloads: multiple **`put`** calls to distinct jail-relative names, then one exec script that joins or runs them.

## Non-goals (unchanged)

- No weakening UNC / `..` / path escape rules.
- No `connector.key` or live PINs in chat or git.
- No claim that Win95-era hosts gain modern TLS from this doc alone.

## Related

- Mode 3 thin UX: `docs/mode3-zero-config-2026-09-19.md`
- Build plan: `docs/build-and-test-plan-mode3-dumb-exec-ergonomics-2026-09-19.md`
