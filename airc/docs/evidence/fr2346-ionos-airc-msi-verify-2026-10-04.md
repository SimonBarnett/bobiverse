# FR #2346 — ionos airc MSI verify (2026-10-04)

Seat: `win-mpre8vi4u6u`. Live **Airc** service left Running (Ergo/BobIrcd untouched).

Backup noted: `C:\ai\backup-test-20261004-223334\airc-default-home`.

## Step results

| Step | Result | Notes |
|------|--------|-------|
| 1. Live service survives | **PASS** | SCM name is `Airc` (not `airc_console_service`). Status Running / Automatic / LocalSystem before and after verify. AppParameters unchanged (MachineId `win-mpre8vi4u6u`, ConsoleHome `C:\Users\Default\.airc`). |
| 2a. airc MSI on release v0.1.22 | **FAIL** | Release assets: only `bob-0.1.22.msi`. Filed **#2354**. |
| 2b. Build airc MSI from main | **PASS** | `Pack-BobiverseRelease.ps1 -Product airc` → `airc-0.1.22.msi` (831488 bytes, sha256 `4f0eb9e1f16cf60a29d25a493252e8d95506d3094c9ccc066ce4daf721840639`). WiX download flaked once; seeded local WiX from `C:\ai\release-0.1.22\common\third_party\wix`. |
| 2c. MSI CustomActions | **PASS** (static) | `SetUninstallCmd` + deferred `RunUninstall` (CAQuietExec64) present; `Install-Airc.cmd` / `Uninstall-Airc.cmd` wired. |
| 2d. Upgrade over live 0.1.21 | **SKIP** | Would replace live Airc; FR requires live survive. No scratch second UpgradeCode. |
| 2e. Self-update Check | **FAIL** | `Update-BobiverseService.ps1 -Product airc -Mode Check` → `result=no-matching-asset tag=v0.1.22` (follows from 2a). |
| 2f. Identity preserved (unit) | **PASS** | `airc/tests/test_fr1552_msi_preserve_identity.py` + related → part of **33 passed** (harvest1583 log assert failed separately; non-blocking). |
| 2g. Uninstall CA (unit) | **PASS** | `test_fr1566_msi_uninstall_stops_service.py` in the same pytest run. |
| 2h. Live uninstall cleanliness | **SKIP** | Would remove production console; deferred until airc MSI is released and a maintenance window. |
| 3. ARP vs VERSION desync | **FAIL** (observed) | ARP DisplayVersion **0.1.21**; `C:\ai\airc\VERSION` **0.1.22**. Expected while self-update cannot Apply. Covered by **#2354**. |

## Extra live nits (filed)

| Finding | Issue |
|---------|-------|
| NSSM DisplayName still `airc console (#{machine} IRC shell)` | **#2355** |
| ConsoleHome under `C:\Users\Default\.airc` as LocalSystem | **#2355** |

## Unit tests run

```text
python -m pytest airc/tests/test_fr1552_msi_preserve_identity.py \
  airc/tests/test_fr1566_msi_uninstall_stops_service.py \
  airc/tests/test_fr77_update_detached.py \
  airc/tests/test_harvest1583_appparameters_skill.py -q
# 33 passed, 1 failed (harvest1583 skill-harvest-log drift — not MSI path)
```

## Not done (by design)

- No `msiexec` upgrade/uninstall against live `Airc`.
- No Ergo / BobIrcd changes.
- No VERSION bump / no GitHub release publish from this seat (owner release path; see #2354).
