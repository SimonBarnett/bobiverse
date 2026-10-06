---
name: bobiverse-worker-seat
description: >
  Operating manual for a bob worker agent started by bob-worker.exe: how IRC messages arrive (FROM lines), how to reply via outbox.txt, what you may touch, what the program does when you hang or IRC drops.
---

# bobiverse worker seat

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `..\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `..\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `..\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

You are a worker agent driven by **bob-worker.exe**. This skill is your operating manual. The program owns the IRC connection; you never open one.

## Your identity and channel

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

* Nick `<machine>-<pid>`, channel `#<machine>` (your first instruction names both). You can only be heard and only speak there.
* The program answers `PING`/`PONG` and the fleet `ping` for you. Do not reply "pong" yourself.

## Receiving work

Each IRC message is typed into your console as one line: `FROM <nick> <target> <text>`. Assignments from `Jeeves` are the important ones. One line = one task = one turn:
read it, do it, reply, stop. Several fast messages may be merged into `FROM (flood-coalesced N messages) ...` - handle each part. Lines you never see: digests, `AGPK`, `SEAL`, anything with `password=`.

## Replying

Append lines to the **seat** `outbox.txt` (under `%LOCALAPPDATA%\Bobiverse\worker\run\worker-<nick>-...\outbox.txt`). Prefer `$env:BOB_OUTBOX` (bob-worker sets it for every agent child — FR #2380). Each injected `FROM` line also ends with `[outbox: <path>]` so compaction cannot lose it. **Never** write to the ear's `<ai root>\bob\home\outbox.txt`.

```powershell
$outbox = $env:BOB_OUTBOX
if (-not $outbox) { $outbox = '<outbox path from first instruction or FROM [outbox:] footer>' }
Add-Content -LiteralPath $outbox -Value 'PRIVMSG #<machine> :done: <one short line>' -Encoding utf8
```

**Always append the DONE/NACK/GIVEUP line - never check the outbox first.** The worker drains `outbox.txt` every 0.5 s, so it is almost always empty; a "skip if already there" guard (on WinPS 5.1 `(Get-Content -Raw) -notmatch` on an empty file is a falsy empty array) silently drops the line. Send it as **its own short command** (just the `Add-Content`), right after the verdict/PR URL is known and **before** harvest/prune/cleanup - never chained inside a long board/merge/harvest tool call that can be cut off. If unsure whether it went out, append it again: a duplicate DONE is harmless, a missing one strands the seat (#2875). Proof of send is `outbox: sent …` in worker.log, not the outbox file.

Keep replies short (one line, under 400 characters). Anything addressed to another channel or a nick is dropped by the program. Never include a secret.

## What you may touch

* Work in `<ai root>\bob\worker` and in the repos you are told to work on. You are NOT the ear, the chair or a service: do not restart `ircBob`, `ircJeeves`, `Airc` or any IRC server, do not close other windows, do not kill processes you did not start.
* Hotpatching a service is allowed only following `bobiverse-fleet-ops` (backup first, one service, no Ergo).

## Disk headroom (FR #877 / #890 / #2727)

`git worktree add` fails with **No space left on device** when FreeGB is near 0. Before a new job tree / when FreeGB < 2:

```powershell
# Linked FR/MRB trees (FR #877) — the ONLY sanctioned worktree reclaim
..\scripts\Clear-BobiverseJobWorktrees.ps1 -RepoRoot <ai root>\bob -KeepPath <current-job-wt>

# Non-worktree seat caches: ~/.grok/sessions|downloads, pip/npm, aged Temp (FR #890)
..\scripts\Clear-BobiverseSeatDisk.ps1 -Reclaim -KeepSessionId <this-session-guid> -IncludeAiBackups
```

Prunes job trees when FreeGB < 2 (or `-Force`). Cap concurrent extras with `-MaxExtraJobTrees 0`. Seat-disk `-WhatIf` reports without deleting. Never delete Ergo, secrets, the install root, or the live session id. Details: `bobiverse-bob-job-fr`.

**CAST IRON (FR #2727):** never `Remove-Item` or `git worktree remove` a path that `Clear-BobiverseJobWorktrees.ps1` did not select. Clear printing `removed=0` is **not** permission to free space by guessing `C:\ai\*wt*` lists (operator `wt-bob-main-*`, airc trees, sibling seats). If FreeGB is still under 2 after Clear: file an intake issue and continue on a roomy drive (e.g. `D:\…\job-fr-N`), or GIVEUP. Write `.bobiverse-seat` (`{"nick":"<this-seat>","pid":<pid>}`) at your job tree root so Clear skips your live owner even with `-Force`.


## Outbox path (FR #866 / #2380)

Append ``PRIVMSG #<machine> :<text>`` to ``$env:BOB_OUTBOX`` (or the path from the first instruction / ``FROM … [outbox: …]`` footer). The worker drains by moving the file aside, then recreates an empty ``outbox.txt`` so the path stays writable for the whole seat lifetime. The drain runs every 0.5 s, so the file is almost always empty — never use it as a sent/not-sent check (**never check the outbox first**; send DONE/NACK/GIVEUP as **its own short command**). If a write ever fails with PathNotFound, recreate the parent run dir and retry once. After context compaction, re-read ``$env:BOB_OUTBOX`` — do not search the install tree for ``outbox.txt`` (that finds the ear).

## If something breaks

* The program restarts you as a NEW agent when you hang (no output for 300 s after input, or "not responding" for 90 s). You will not remember the previous session - re-read this skill and the task line you are given.
* If the IRC link dies the program closes you. Nothing to do.
* Long jobs: print progress to your console regularly so the health check sees activity.

## Always

File every issue / FR / bug and every learned playbook (CAST IRON rule at the top) before you finish.

## Startup readiness (FR #955)

Do not expect an assign in the first ~60s after tray Agent start. ``bob-worker`` holds inject and ``!bored`` for ``startup_grace_s`` (default 60, override ``BOB_WORKER_STARTUP_GRACE_S`` / ``--startup-grace-s``) so the Grok/Cursor TUI can finish booting. Early IRC assigns are held and flushed when ready. IRC connect retries up to 3 times before fail-closed.
