# Skill harvest log

## 2026-09-29 — WIN-MPRE8VI4U6U airc/bob/jeeves cutover

Harvested into `.grok/skills/bobiverse-{jeeves,bob,airc}` + `docs/post-install.md` + install scripts:

| Lesson | Fix |
|--------|-----|
| `Start-Jeeves` / `--channel` + PowerShell `#` comment | `irc_agent.py`: `--channel` optional when `--chair` |
| MSI LocalSystem ChairHome → `C:\Users\Default\…` | `Install-Jeeves`: prefer Admin chair or `home-jeeves` |
| Legacy `BobJeeves` + `ircJeeves` both Running | `Disable-BobiverseLegacyBobJeeves` on install |
| `CryptUnprotectData` with LocalSystem + Admin identity | post-install + skill: ObjectName / park identity interim |
| Crash-loop stderr flooding airc console | NSSM AppStdout/AppStderr → `C:\ai\jeeves\logs\` |
| Leftover `AircConsole` beside bobiverse `Airc` | `Install-Airc` **removes** `AircConsole` from SCM |
| Legacy `BobJeeves` left Stopped/Disabled in services.msc | `Remove-BobiverseLegacyService` deletes SCM entry (tree kept) |
| Remote ops via bob outbox PRIVMSG to `*_console` | bobiverse-bob / bobiverse-airc skills |
| Duplicate MSI tray vs Watch-BobTray | already 0.1.5 (#14); documented again |

VERSION → **0.1.6** (pack when shipping).

## 2026-09-30 — DEV1 TipForm companion durable start

Harvested into .grok/skills/bobiverse-bob + docs/post-install.md + tray launcher:

| Lesson | Fix |
|--------|-----|
| Tray logs `tray up` then dies when started from Grok agent shell | `Start-BobFleetTray` uses WMI `Win32_Process.Create` (job-object breakaway) |
| Broad seat-wrapper `match Watch-BobTray` kills diagnosing shells | Kill filter requires `-File …Watch-BobTray.ps1` / `_Watch-BobTray-*.ps1` |
| Product is service + companion, not BobFleet task | HKCU `Run\BobiverseTray`; disable `BobFleet-<id>` |
| LocalSystem skipped update-check | `Start-Bob` no longer forces `BOBIVERSE_NO_UPDATE`; `Check-BobiverseUpdate` resolves `gh` + Releases API |
| TipForm recycle JIT `PipelineStoppedException` | CatchException before Controls; swallow on ticks (agentic_build Watch-BobTray) |
| Version visible on card | TipForm footer `bob {ver}` |

VERSION → **0.1.8** (pack when shipping).
