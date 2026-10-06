---
name: bobiverse-airc
description: >
  Maintain the Airc console service ({machine}_console). Architecture, paths, shop vs lobby, config, logs, install/upgrade/hotpatch. Use in <ai root>\airc or for Airc MSI, remote PRIVMSG shell, AircConsole leftovers, or /bobiverse-airc.
---

# bobiverse-airc

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

Foundation: `bobiverse-fleet-ops` (shared ops/hotpatch/health) and `harvest` -> https://github.com/SimonBarnett/bobiverse

## Architecture

Service **`Airc`** (NSSM, tree `<ai root>\airc`) runs the Airc console: IRC nick **`<MachineId>_console`**.
**MachineId** is the canonical lowercase fleet id (`-MachineId` / `BOB_MACHINE_ID`).

| Piece | Where |
|---|---|
| Install root | `<ai root>\airc` (`scripts\`, `config\`, `logs\`, `assets\`, `.grok\skills\`, `VERSION`) |
| ConsoleHome | `%USERPROFILE%\.airc`; LocalSystem: `C:\Users\Administrator\.airc` or `<ai root>\airc\home` — **never** `C:\Users\Default\.airc` |
| NickServ GUID | `<ConsoleHome>\console.password` (minted; not the Ergo PASS) |
| Ergo PASS | `<ai root>\airc\config\ergo.password` (Install copies; never invent) |
| Logs | `<ai root>\airc\logs\*.log`, `<ConsoleHome>\*.log` |
| IRC | SASL on by default for reserved `<MachineId>_console` |

**Airc vs AircConsole:** bobiverse `Airc` (`<ai root>\airc`) ≠ agentic_irc `AircConsole` (`<ai root>\airc-console`). One console per box: `Install-Airc` removes leftover `AircConsole` from SCM.

## Remote control

- Shell ergonomics: FR #75 (PowerShell default, `cmd:`, `psb64:`, `DONE id= exit=`).
- **Command StdOut Unicode (FR #2580):** every PowerShell `-EncodedCommand` is prefixed so `$OutputEncoding` / `[Console]::OutputEncoding` are UTF-8 (no BOM); `cmd:` gets `chcp 65001`. Redirected powershell.exe otherwise defaults `$OutputEncoding` to ASCII and best-fits Greek/CJK (α→a, U+FFFD/`?`) before airc UTF-8-decodes capture.
- **Command StdErr CLIXML progress (FR #2641):** the same EncodedCommand preamble sets `$ProgressPreference = 'SilentlyContinue'` so redirected powershell.exe does not emit `#< CLIXML` / `Preparing modules for first use` on stderr for plain `Write-Output` (extra IRC flood + false StdErr). Real `Write-Error` / native stderr still reach `err` lines. Frozen `airc.exe` needs rebuild/redeploy for the fix.
- Driving-box helper: `scripts\Invoke-AircRemote.ps1` (FR #76) — `-SelfTest`, `-Outbox`, PUT chunking client-side.
- **ReplyFile wait (FR #1546 / PR #1560):** `Invoke-AircRemote -ReplyFile` prefixes `id=<8hex>` on Command/Cmd/Psb64, then polls `<bob home>\airc-replies.jsonl` until matching `DONE` (timeout exit 2). The bob ear appends `*_console` Query `out`/`err`/`DONE` PMs to that jsonl (see `bobiverse-bob-commands`). Never rely on a pre-written reply file alone. Overlapping remotes that reuse the same id can collide.
- **Long Command output / reconnect (FR #2612):** console Query replies go through an outbound queue that survives in-process `force_reconnect` and drains after handshake; graceful stop flushes `DONE exit=1` for in-flight shell ids. Hard process kill mid-emit can still drop the queue — prefer not to Restart-Service Airc during a live ReplyFile Wait; raise `-TimeoutSec` for 80+ line floods (~0.35s FLOOD_S per line).
- **Concurrent shells / busy (FR #2632):** `ShellJobRunner` queues one in-flight shell per Query nick plus up to `SHELL_PENDING_MAX` (8) waiting commands so two overlapping `Invoke-AircRemote -Action Command` calls both get a real DONE. Only a full pending queue fail-closes with `err … busy: prior shell still emitting` + `DONE exit=1` (no hang / no lost DONE). `Invoke-AircRemote` also treats that busy DONE as retryable within `-MaxRetries`/`-TimeoutSec` (compat with older airc builds that always busy-failed).
- **Stop flush before socket close (FR #2640):** prepare_stop / stop interrupt paths enqueue DONE for in-flight **and** pending shell ids, drain the outbound queue, then close the socket. While _stopping, _on_console_out enqueues only (no sendall) so NSSM stop cannot WinError 10038-spam and drop the DONE.
- **STATUS + Heard: strip (FR #2570 / #2575):** Status pins `id=<8hex> STATUS`; the console emits `out id=… seq=1 STATUS machine=…` then `DONE id=… exit=0` (same framing as shell so Invoke-AircRemote StdOut fills). Console `sanitize_console_operator_text` strips Halloy/bobtalk `@nick … Heard:` wrappers before verb/shell routing (avoids PowerShell splat on `@machine_console`). **Footgun:** `-ReplyFile` ending in `.jsonl` that is **not** the ear’s `home\airc-replies.jsonl` makes Wait poll an empty file — always use the ear path (or omit and let Resolve-AircRepliesJsonl pick it).
- Console NSSM logging (FR #1546): AppStdout/AppStderr under `<ai root>\airc\logs\airc-console.log` with rotate; DisplayName/Description expanded with the machine id (no literal `#{machine}`); service `info()` lines are ISO-UTC; keepalive PING logged at most once per hour via `info_keepalive`.
- Protocol sketch: `docs/airc-remote-control.md`. Ops: `docs/airc-ops.md`.

## Install, upgrade, rollback, hotpatch

See `bobiverse-fleet-ops`. Airc specifics: after MSI ensure `config\ergo.password`; re-run `Install-Airc.cmd -MachineId <id>` if NSSM is stale.
Self-update on start uses **`Update-BobiverseService.ps1`** (detached Apply — never inline msiexec in the live service). Opt out `BOBIVERSE_NO_UPDATE=1`. Hotpatch = back up `<ai root>\airc`, copy changed scripts, `Restart-Service Airc` ONLY.
**Fleet wrapper (FR #1545 / PR #1561):** legacy NSSM entry `Start-AircConsole-Fleet.ps1` must delegate to `Start-AircConsole.ps1 -ServiceMode` so sync + self-update run (same opt-outs). Always pass `-ServiceMode` under NSSM. Use `$launchArgs` for the splat — never automatic `$args` (PR #1588).
**Upgrade AppParameters (FR #1552 / harvest #1583):** MSI upgrade/reinstall must read the **live** NSSM/service `AppParameters` first, then `airc-install.json` fallback, **before** any profile default. Never invent a new `ConsoleHome` when an identity already exists (keeps NickServ GUID / shop nick). Merged PR #1570 + docs #1575.
**Uninstall (FR #1566):** MSI `/x` runs `Uninstall-Airc.cmd` before RemoveFiles (`REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE`) to stop/remove service `Airc`; ConsoleHome secrets stay. Manual: `scripts\Uninstall-Airc.cmd`.

## Do not

- Run `Airc` and `AircConsole` together; invent an Ergo PASS; stamp UAT; put secrets on IRC; call retired `Check-BobiverseUpdate.ps1` for fleet ops.
