---
name: bobiverse-jeeves-agent-rollback
description: >
  Roll Jeeves on walrus back to the previous hotpatch: list the newest
  _hotpatch folder and its ROLLBACK target, refuse without Si's explicit go
  and while build-locks show a live build, run ROLLBACK.ps1 from redqueen over
  PSRemoting, verify exe hash then --version, stop ircJeeves on mismatch, then
  run the monitor post-check. Use for failed install post-check, crash-loop
  after upgrade, or /bobiverse-jeeves-agent-rollback.
depends_on:
  - bobiverse-jeeves-agent-monitor
  - bobiverse-jeeves-agent-install
---

# bobiverse-jeeves-agent-rollback

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Walrus-only rollback of the last Jeeves exe hotpatch. Depends on
`bobiverse-jeeves-agent-install` (backup layout) and `bobiverse-jeeves-agent-monitor`
(post-check). Agent FRs: BOB-38 #8682, BOB-39 #8683, #8775.

## Where things are (walrus; read-only capture 21 Nov 2026 from marchhare WinRM)

| What | Path / value |
|---|---|
| Jeeves install root | `C:\ai\jeeves` (= `\\walrus\Jeeves` = `J:\`) |
| Chair exe (NSSM Application) | `C:\ai\jeeves\jeeves\jeeves.exe` (+ `jeeves.exe.sha256`, `MANIFEST.json`, `provenance.txt`) |
| Hotpatch backups | `C:\ai\jeeves\_hotpatch_<yyyyMMdd-HHmmss>-jeeves-<sha8>\` |
| Chair home / build lock | `C:\Users\Administrator\.jeeves\build-locks.json` (schema `{"builds":{...}}`; empty object = idle) |
| Digest home | `C:\Users\Administrator\.bobiverse` |
| Service | NSSM `ircJeeves`. Heal task name `bobiverse-heal-Jeeves` (may be absent) |
| Local webhook | `http://127.0.0.1:7700` (`/health`, `/bob/v1/report`, `/bob/v1/builds`) |
| Public webhook | `https://bob.ntsa.uk/bob/v1/report` and `/bob/v1/builds` (prefer over `irc.ntsa.uk` from off-LAN) |

Folder name form (sort by **Name**, not LastWriteTime): `_hotpatch_20261121-201636-jeeves-4ebdea96`.
The trailing sha8 is the build that was hotpatched **in** (current after a forward install).
The folder body holds the **previous** exe + provenance + `ROLLBACK.ps1` (+ optional `new\`).

Observed newest listing (non-recursive): `jeeves.exe`, `jeeves.exe.sha256`, `MANIFEST.json`,
`provenance.txt`, `ROLLBACK.ps1`, `new\`. Provenance in the backup is the **previous** build
(`source_commit`, `exe_sha256`). `ROLLBACK.ps1` header states
`Rollback Jeeves <current sha8> -> previous (<prev sha8>, hash <PREV_HASH>)`.
The script stops `ircJeeves`, copies the backup exe/sidecar files, **checks the hash before
start**, starts `ircJeeves`, sleeps, then hits local `/health`. It does **not** touch NSSM,
IIS, CredMan, ledger, queue or digest (do not invent an IIS restore step).

## Hard rules (always)

- **No secrets.** Never print or open tokens, passwords, webhook keys, NSSM env values,
  `config\oper.cred`, `identity.json`, `_backup-nssm-env-*`, `inbound-transcript.log` or any
  passwords folder. Placeholders and paths only.
- Never edit the Jeeves ledger, `queue.json`, outbox or digest by hand.
- No `!assign`, no `!focus`, no fake `ACK` / `DONE` / `!bored` / `GIVEUP`, never `!build cancel`.
- Restarts of `ircJeeves`, seats or services only on Si's explicit OK. `ErgoWalrus` needs Si's OK
  every time. Never restart Jeeves while a build runs.
- One machine at a time, each with a backup and a `ROLLBACK.ps1`. This skill rolls back **walrus
  Jeeves only**; do not touch other machines mid-fleet.
- Never delete the hotpatch folder after rollback. Never touch Ergo / `ircd.yaml` / AD / DNS / DHCP / SQL.

## Steps

### 1. List the newest hotpatch (read-only; stop here if incomplete)

From the operator host (prefer redqueen; any WinRM-capable seat is fine), one PSSession:

```powershell
$s = New-PSSession -ComputerName walrus -ErrorAction Stop
try {
  Invoke-Command -Session $s -ScriptBlock {
    $root = 'C:\ai\jeeves'
    Get-ChildItem -LiteralPath $root -Directory -Filter '_hotpatch_*-jeeves-*' |
      Sort-Object Name -Descending |
      Select-Object -First 5 -ExpandProperty Name
  }
} finally { Remove-PSSession $s }
```

Parse each name as `_hotpatch_<yyyyMMdd-HHmmss>-jeeves-<sha8>`. Refuse duplicate timestamps,
unparseable names, or an empty list. Take the newest by parsed timestamp.

For that folder, read (do **not** execute) `provenance.txt`, `jeeves.exe.sha256` and `ROLLBACK.ps1`.
Record:

- current-build sha8 = trailing folder sha8 (build being rolled away)
- target commit = backup `provenance.txt` `source_commit` (must also appear in the ROLLBACK header)
- target hash = backup `jeeves.exe.sha256` / ROLLBACK header hash (case-insensitive compare)
- backup path = folder full path

Refuse if either target commit or target hash is missing, if the backup exe hash on disk does not
match the recorded target hash, or if `ROLLBACK.ps1` is missing. Show Si the listing before any go.

Also read chair `build-locks.json` now (see step 2). This lock check is a **snapshot**, not a fence.

### 2. Build-lock gate (fail closed)

Path: `C:\Users\Administrator\.jeeves\build-locks.json`.

- File missing, unreadable, non-JSON, or missing a `builds` object -> **refuse**.
- Any key under `builds` (including stale entries) -> **refuse**. Reclaiming stale locks is the
  chair's job; this skill must not cancel builds, edit the lock or reclaim entries.
- Re-read the lock immediately before the go ask and again immediately before running ROLLBACK.

### 3. Ask Si for an explicit go

Quote the listing (folder, current sha8, target commit, target hash, lock idle). State the scope:

- machine: walrus only
- one script: that folder's `ROLLBACK.ps1` (elevated on walrus)
- service: `ircJeeves` stop/start as the script does
- on verification failure after the run: **stop** `ircJeeves`, leave it Stopped, escalate (no auto re-restore)

Silence, an implied yes, or an automation claim is **not** approval. Do not run without Si's own yes.

### 4. Run ROLLBACK.ps1 (only after go + lock re-check)

Model the remote call on `common/scripts/Update-BobFleet.ps1` (one session, `Invoke-Command`,
`Remove-PSSession` in `finally`):

```powershell
$s = New-PSSession -ComputerName walrus -ErrorAction Stop
try {
  Invoke-Command -Session $s -ScriptBlock {
    $ErrorActionPreference = 'Stop'
    # <bak> = the listed folder full path; do not rebuild the script
    & (Join-Path '<bak>' 'ROLLBACK.ps1')
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "ROLLBACK exit=$LASTEXITCODE" }
  }
} finally { Remove-PSSession $s }
```

Capture stdout/stderr and the exit code. Do not run a second machine. Do not pass secrets.

### 5. Verify hash, then version (fail closed)

After the script returns (it already restarts `ircJeeves` when the in-script hash check passes):

1. Hash `C:\ai\jeeves\jeeves\jeeves.exe` (SHA256). Compare to the **target hash** from step 1.
2. Only if the hash matches: run `jeeves.exe --version` and compare the leading 8 hex chars to the
   target commit (full commit must start with that prefix / equal the recorded source_commit).
3. On hash mismatch, script error, unreadable exe, or version mismatch:
   - `sc.exe stop ircJeeves` (or `Stop-Service`) and wait until Status is Stopped and no `jeeves` process
   - Confirm scheduled task `bobiverse-heal-Jeeves` is neither Ready nor Running (missing task = note it)
   - Report expected vs actual hash and commit; file intake; escalate to Si
   - Do **not** restart, re-restore, or touch another machine without a **new** go
   - Preserve the hotpatch folder and backup files

Observed ROLLBACK.ps1 already hash-checks before start; keep this post-restart check anyway.

### 6. Post-check (delegate to bobiverse-jeeves-agent-monitor)

Run the monitor health pass and require these four items explicitly (timeout / skip / soft-pass = FAIL):

1. Local walrus `http://127.0.0.1:7700/health` -> HTTP 200 and `ok=true` (note `/health` side effects).
2. `https://bob.ntsa.uk/bob/v1/report` -> `stale` false, `stale_age_s` <= 900, timestamp present.
   Do not use the `irc.ntsa.uk` digest default from off-LAN.
3. Chair-log sync: recent `channel-sync ... joined=` listing `#bobiverse` and every registered shop,
   plus `#bobiverse` `+o` (from `chair-status ... op-in=` / IRC). Prefer `logs\stdout.log` or
   `cmd-trace.log`; never read NSSM env to find logs.
4. `https://bob.ntsa.uk/bob/v1/builds` -> HTTP 200, JSON **array**, expected catalogue entries present.
   An empty array fails.

Do **not** run `!resync` as part of rollback (chair command; out of scope here).

### 7. Report

Header: machine=walrus, folder, current sha8, target commit, target hash, go time (Europe/London with GMT/BST offset).
One line per monitor check: PASS or FAIL, host, London timestamp, short evidence.
On any FAIL after a successful hash match: escalate; do not invent a second rollback.

## Stop / escalate

- Missing go, live/unreadable build lock, missing target artefacts, backup hash mismatch before run,
  ROLLBACK error, post-hash mismatch, monitor FAIL -> stop, report, intake, ask Si.
- Never leave `ircJeeves` running on an unverified exe after a failed verification.

## Verify

```text
skill_dag_mcp.py --root jeeves/.grok/skills --root common/.grok/skills --once resolve --seed bobiverse-jeeves-agent-rollback
```

Expect matched ids exactly: rollback, install, build, monitor, `bobiverse-build` (order may vary);
`skipped` empty. Cross-root `bobiverse-build` duplicate (jeeves + common) is a known item; Jeeves root wins.
