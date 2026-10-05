# Release v0.1.23 pack evidence (FR #2447 / #2511)

## What
Finished bob+airc 0.1.23 MSI pack after Build-BobWatcher stderr-redirect fix (#2442) and Install-AircConsole ASCII/HomePath fix (#2501). Re-packed airc from tip so the Quiet Apply CA ships `$HomePath` (not read-only `$Home`). Uploaded replacement airc assets to GitHub release `v0.1.23`. Installed bob+airc on ionos (win-mpre) and smoked.

## Pack
- Worktree: tip `origin/main` (post-#2501 HomePath).
- `Pack-BobiverseRelease.ps1 -Product airc -Version 0.1.23 -OutDir C:\ai\release-out`
- Seeded local NSSM/WiX caches (nssm.cc 503; corrupt WiX zip on fetch).
- Admin-extract confirmed `Install-AircConsole.ps1` contains `HomePath` (6 hits) and no `[string]$Home,`.
- bob-0.1.23.msi already present from post-#2442 pack; jeeves-0.1.23.msi already present.

## Assert
`Assert-BobiverseReleaseAssets.ps1 -Tag v0.1.23` -> OK for bob, airc, jeeves (msi + sha256).

Local sha256 (post re-pack):
- airc: `7f0786102935ec48f4b759ccab74fcbf4badeb35e41cab587da0a47ada73e2ad`
- bob: `c2367a6f30e0d825399eff508137d042d9a2a0e068e0c1218f78fe1a0fb34ae6`
- jeeves: `6b2a4ca1aa521b95ac996e41b84903035bc0f70603bfbb69670ed2ee2aa03719`

## Install + smoke (ionos / win-mpre)
- Cleared airc `blocked-loop-guard` (prior Apply hit msiexec-timeout on pre-#2501 MSI CA parse failure).
- `Update-BobiverseService` Apply with `-AllowLocalAssets` + local release JSON:
  - airc 0.1.22 -> 0.1.23: msiexec-exit=0, apply-ok, service Running, live script has HomePath.
  - bob 0.1.22 -> 0.1.23: arp-desync heal + msiexec-exit=0, apply-ok, ircBob Running.
- Smoke: Airc/ircBob/ircJeeves Running; `airc.exe --selftest` ok; Assert OK; bob-ear.exe present; Watch-AgentHealth.exe under `Watch-AgentHealth\`; bob-worker.exe under `worker\`.
- jeeves InstallRoot VERSION remains 0.1.21 (out of #2447 bob+airc scope; jeeves MSI already on the release).

## Notes
- Prior airc Apply failures were the broken packaged `Install-AircConsole.ps1` (try/catch / `$Home`); re-pack was required (#2511).
- No self-MRB. No VERSION file bump in-repo (pack used `-Version 0.1.23`).
