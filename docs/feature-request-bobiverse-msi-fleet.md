# FR: bobiverse MSI fleet (jeeves / bob / airc)

See docs/vision.md and docs/functional-spec.md.

GitHub: https://github.com/SimonBarnett/bobiverse/issues/1

## Deliverables
- Three MSIs with clean reinstall, tools IF MISSING, Release self-update
- !register + Bob mode grants; recycle/systray restart; skills

## Acceptance (vision S1-S4)

Locked by `tests/test_fr1_msi_fleet_acceptance.py`.

| id | metric | evidence on main |
|----|--------|------------------|
| S1 | Three MSIs publish | `Pack-BobiverseRelease.ps1 -Product all`; distinct UpgradeCodes; `MajorUpgrade`; latest GitHub Release lists `jeeves-*.msi`, `bob-*.msi`, `airc-*.msi` |
| S2 | `!register` + Bob modes | `registered_machines.parse_register_command`; `chan_privs` grants bob-+o on shop and +h on `#bobiverse`; operators-only `!register` in `irc_agent` |
| S3 | Recycle path | `Restart-BobEar.ps1` (depart-request + Restart-Service ircBob); TipForm/`Start-BobTray` Restart; `bob_recycle` `!recycle` / `!recycle jeeves` |
| S4 | Self-update | `Start-Bob` / `Start-Jeeves` / `Start-AircConsole` call `Update-BobiverseService.ps1` (sha256, opt-out, no Ergo/seat kill) |

Also covered: Install-BootstrapTools IF MISSING (`$ForceTools` refresh), per-product `AGENTS.<product>.md` + `.grok/skills/bobiverse-<product>` + harvest staged by Pack.

Remaining install/upgrade nits that are **out of this FR's umbrella** stay on their own issues (e.g. #70 RunInstall params / service-account gh auth).
