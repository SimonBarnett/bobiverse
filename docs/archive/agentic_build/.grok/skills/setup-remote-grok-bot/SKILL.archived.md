<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/setup-remote-grok-bot/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: setup-remote-grok-bot
description: >
  Stand up Grok Build CLI and/or Grok Bot desktop on a remote Windows machine;
  recover a blank, frozen, off-screen, or signed-in-but-unusable Grok Bot window;
  use Mode 3 DUMB put+spawn when desktop tools are down. Use when the user says
  remote Grok Bot install, blank Grok Bot, flamingo onboarding, or /setup-remote-grok-bot.
github: https://github.com/SimonBarnett/agentic_build
---

# Setup remote Grok Bot (Windows)

End-to-end fleet onboarding. Mode 3 argv traps live in agentic_irc (issue #2 / mode3-dumb-ops). Temporal hangs are `unstick-grok-bot` (not a blank Electron window).

No secrets, PINs, connector.key, or Cursor passwords in chat or git. Do not claim Win95 TLS. Do not replace invite-airc.

## Bootstrap order

1. Mode 3 thin live on the target (invite-airc / zero-arg self-heal restart).
2. Chair (`cm-inv` or equivalent) online on a modern box with the **correct pair key** (do not mix walrus/flamingo keys).
3. Install **CLI first** (`grok` + `agent`), then **desktop**.
4. Human Cursor sign-in on the **interactive console session** (not a Mode 3-spawned GUI).
5. `ListMachines` / `ListGrokBotUserComputers` shows the host **connected** before relying on desktop Shell/Read.

## CLI + desktop via Mode 3 (put + spawn)

Official CLI: `irm https://x.ai/cli/install.ps1 | iex` — but **long installs exceed DUMB's 60s exec cap**.

1. `put` a `.ps1` into the thin jail (relative path). Keep URLs **inside** the file.
2. Short `exec`: `powershell.exe -File <script>` that only `Start-Process`es the installer and exits.
3. Poll a log with later `exec` / `get`.

Desktop Setup (x64): `https://downloads.cursor.com/grokbot/stable/win32-x64/<ver>/Grok_Bot_<ver>_Setup.exe`. Silent: `Start-Process ... -ArgumentList '/S' -Wait` from the put script.

DUMB argv:

| Symptom | Cause | Fix |
|---|---|---|
| `error: jail` | literal `https://` / `//` or `\\` / `..` in argv | URLs only inside put files |
| `error: bin` | meta chars `\\|><^` or non-allowlisted argv0 | no pipes/redirects/background `&` in argv; put scripts |
| `timeout` | foreground install >60s | spawn detached; poll log |
| false MISSING after install | `if exist "%LOCALAPPDATA%\\Programs\\Grok Bot\\..."` with spaces | `Test-Path -LiteralPath` in a put script |

CLI lands at `%USERPROFILE%\\.grok\\bin`. Desktop: `%LOCALAPPDATA%\\Programs\\Grok Bot\\Grok Bot.exe`.

## Never launch Grok Bot GUI via Mode 3 for sign-in

`Start-Process` of `Grok Bot.exe` from DUMB often yields a blank/frozen window (wrong session / GPU / Electron).

- Kill remotes if stuck.
- Operator launches from the **interactive desktop** (Start menu or shortcut).
- Prefer a "Grok Bot (no GPU)" shortcut: `--disable-gpu --disable-gpu-compositing --disable-software-rasterizer`.

## Blank / frozen window (Electron)

`%APPDATA%\\Grok Bot\\`:

| File | Signal |
|---|---|
| `desktop-status.json` | `signedIn: true` proves login even if UI looks dead |
| `window-state.json` | `x/y ~ -32000`, `width/height = 0` => "blank" is off-screen zero-size |
| `GPUCache` / `DawnWebGPUCache` / `Code Cache` | safe to clear while the app is killed |

Fix: kill the app, rewrite `window-state.json` to sane bounds (e.g. 80,80 / 1280x800), relaunch via the no-GPU shortcut. On ionos 2026-09-20 the file was `x:-31992 y:-32000 width:0 height:0 isMaximized:true` while the chat pane still painted; **Bob's screen** (sandbox VNC) stayed empty. That is not a Temporal unstick.

Memory: closing Edge/Steam can free 1+ GB and unstick the UI.

Kill by process name (space-safe):

```powershell
Get-Process | Where-Object { $_.ProcessName -eq 'Grok Bot' } | ForEach-Object { $_.Kill() }
```

(`taskkill /IM Grok Bot.exe` breaks on the space when argv is poorly quoted.)

## Mode 3 thin restart (already paired)

On the elder box, no new PIN:

```
cd /d C:\\airc
airc-moot-thin.exe
```

Zero-arg self-heal. Chair must already be joined. Fresh PIN only if the pair is lost (invite-airc).

## Fleet registration lag

After sign-in, `ListMachines` may show `connected: false` briefly while Grok Bot processes run and Mode 3 works. Retry; keep the desktop app open. Do not declare "no access" until Mode 3 smoke **and** `connected: true`.

## CAST IRON — harvest MRB process into free agents (Simon 2026-09-24)

When setting up a **free agent** (new Grok Bot / talk seat / shop worker that
may do MRB), harvest the STANDARD MRB process into that agent's
instruction/context: link skill `bob-mrb-worker` (tests-first; PASS merge;
FAIL one fix PR then merge both). So the next seat follows the same standard.
Foundation honesty box: `harvest-agent-skills`.

## Dual control planes

- **Desktop tools** (`machineId`) — preferred once connected.
- **Mode 3 DUMB** — fallback for install, kill, health when desktop is frozen/disconnected.

Executor subagents cannot use `machineId`; the parent must Shell with machineId or drive Mode 3 from the chair.
