<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bob-systray-start-update-2026-09-27.md, last changed 2026-09-27. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: Bob Systray Start menu + deterministic git update on start/restart

## Summary

Simon (ionos watch seat 2026-09-27): Start Menu must have a **Bob Systray** folder/shortcut using the **same robot icon** as the NotifyIcon. Starting and Restarting must **check git for updates and install** before the tray comes up. When updates exist, show an **Updating** dialog for the duration. Update path is **deterministic scripts only** (no LLM).

## Ultimate objective

Operators open Bob Systray from Start and always get a tray that matches `origin/main`, with a visible updating dialog when git had work to do.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Start Menu folder | `Programs\Bob Systray` exists with at least one `.lnk` | `Test-Path` after `Install-BobFleet` / shortcut installer | Folder or `.lnk` missing |
| S2 | Shortcut icon | `.lnk` `IconLocation` points at `assets/bob-systray.ico` (same robot as tray) | Read shortcut COM / test installer output | Icon missing or wrong path |
| S3 | Start/restart update gate | `Start-BobFleetTray.ps1` (and Restart watcher) runs git fetch + install when behind `origin/main` | Hermetic Test-Pack with fake git / `BOB_FLEET_REINSTALL_FAKE` | Behind remote and no update invoked |
| S4 | Updating dialog | Dialog shown while update runs; closes when done | Test-Pack asserts dialog script + done-flag contract; manual STA smoke | Updates run with no dialog path |
| S5 | No LLM in update | Update uses only PowerShell/`git`/`Invoke-BobFleetReinstall.ps1` | Code review + Test-Pack: no agent/LLM invoke in update scripts | Any LLM/agent call on the update path |

## Shape

LOCKED

Primary: app

Windows Start Menu shortcut + WinForms updating dialog + systray. Delivery: PowerShell scripts in `agentic_build`.

## Stack

LOCKED

- Windows PowerShell 5.1, WScript.Shell shortcuts, WinForms STA dialog
- `git` ff-only / `Invoke-BobFleetReinstall.ps1` for install
- Same Font Awesome robot drawn for tray → exported `assets/bob-systray.ico`

## Architecture

```
Start Menu\Programs\Bob Systray\Bob Systray.lnk
        │  (icon: assets/bob-systray.ico)
        ▼
Start-BobFleetTray.ps1
        │
        ├─ Test-BobSystrayGitBehind (git fetch + rev-list)
        │     └─ if behind: Show-BobSystrayUpdatingDialog.ps1 (second process)
        │              + Invoke-BobFleetReinstall.ps1 (scripts only)
        │              + done-flag closes dialog
        └─ start / ForceNew Watch-BobTray.ps1 (single instance)

Restart watcher (TipForm) → same update gate + ForceNew relaunch
```

## Gap vs current tree

- Shortcuts live under `Programs\Bob Fleet` as `Bob Fleet.lnk`, no robot `.ico`, Start does not git-update before launch.
- `Restart-BobTrayWatcher` already calls `Invoke-BobFleetReinstall` but has no Updating dialog and Start path skips update when tray already running.

## Acceptance

| ID | Criterion |
|----|-----------|
| A1 | Start Menu `Programs\Bob Systray\` exists after install/shortcut helper. |
| A2 | Shortcut uses `assets/bob-systray.ico` (robot matching NotifyIcon). |
| A3 | Start and Restart always check git; when behind, run scripted install. |
| A4 | Updating dialog visible for the update duration; closes on done/fail. |
| A5 | Update path has zero LLM/agent calls. |

## Mocks

`docs/mocks/bob-systray/`: `home.html` (updating), `empty.html` (already current), `error.html` (update failed).
