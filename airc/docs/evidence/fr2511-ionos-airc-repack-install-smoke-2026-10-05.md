# FR #2511 — ionos airc MSI re-pack + install/smoke (2026-10-05)

Seat: `win-mpre8vi4u6u` (COMPUTERNAME `WIN-MPRE8VI4U6U`, ionos Ergo host).  
Product fix already on main via PR #2501 / closed #2499 (`Install-AircConsole` ASCII + `$HomePath`).

## Ask

Re-pack airc MSI with the fixed script, `Assert-BobiverseReleaseAssets`, install+smoke on ionos (`require_machine=ionos`).

## Results

| Step | Result | Notes |
|------|--------|-------|
| 1. Tip script has FR #2499 `$HomePath` | **PASS** | `C:\ai\airc\scripts\Install-AircConsole.ps1` and `airc\scripts\...` both contain `FR #2499` / `[string]$HomePath`. Parser errors: **0**. |
| 2. Local MSI vs pre-fix backup | **PASS** | `airc-0.1.23.msi.bak-pre2511` = 9502720 bytes (10:37). New `airc-0.1.23.msi` = 9510912 bytes (14:14). |
| 3. MSI payload contains fix | **PASS** | `dark -x` extract: File blob contains `FR #2499` + `HomePath` (not `$Home` bind). |
| 4. GitHub release v0.1.23 assets | **PASS** | `airc-0.1.23.msi` sha256 `7f0786102935ec48f4b759ccab74fcbf4badeb35e41cab587da0a47ada73e2ad` matches local release-out; uploaded 2026-10-05T13:17Z. |
| 5. Assert-BobiverseReleaseAssets | **PASS** | `-Tag v0.1.23 -Products airc,bob,jeeves` → `ok=true` (exit 0). |
| 6. Install root / ARP | **PASS** | `C:\ai\airc\VERSION` = `0.1.23`. ARP DisplayName `bobiverse airc` DisplayVersion `0.1.23`. |
| 7. Service smoke | **PASS** | `Get-Service Airc` → Running / Automatic. NSSM Application `C:\ai\airc\airc\airc.exe`. |
| 8. `airc.exe --selftest` | **PASS** | `selftest ok` exit 0. `--help` prints argparse. |
| 9. Self-update Check | **PASS** | `Update-BobiverseService -Product airc -ServiceName Airc -InstallRoot C:\ai\airc -Mode Check -ForceCheck` → `result=current local=0.1.23 latest=0.1.23`. |

## Not done (by design)

- No Ergo / BobIrcd changes.
- No VERSION bump (still `0.1.23`; re-pack replaced the broken airc asset on the same tag).
- Did not leave a second live upgrade running while msiexec mutex was held by another session.

## Hashes

```
airc-0.1.23.msi sha256=7f0786102935ec48f4b759ccab74fcbf4badeb35e41cab587da0a47ada73e2ad
```
