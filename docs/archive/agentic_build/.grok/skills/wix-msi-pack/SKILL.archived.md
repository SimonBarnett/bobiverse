<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/wix-msi-pack/SKILL.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: wix-msi-pack
description: >
  Pack a per-machine Windows MSI with WiX Toolset v3 (heat/candle/light),
  deferred CAQuietExec post-install, and SHA256 sidecar. Use when building or
  fixing an MSI, WiX Product.wxs, heat harvest, candle/light, CAQuietExec64,
  CustomActionData, QtExecCmdLine, msiexec 1603, admin-extract workaround,
  Pack-*Release.ps1, Fetch-Wix, or /wix-msi-pack. Product-specific install
  behaviour for airc console stays in SimonBarnett/agentic_irc airc-console.
---

# WiX MSI pack (fleet releases)

Foundation: harvest-agent-skills -> https://github.com/SimonBarnett/agentic_build

Generic playbook for shipping a **single per-machine MSI** (+ `.sha256`) from a
staged install tree. Reference implementation: `SimonBarnett/agentic_irc`
`scripts/Pack-AircConsoleRelease.ps1`, `scripts/Fetch-Wix.ps1`,
`packaging/airc-console/Product.wxs` (issue #305 / #309).

## Toolchain

- **WiX v3** binaries: `candle.exe`, `light.exe`, `heat.exe`, plus
  `WixUtilExtension.dll` (needed for `CAQuietExec64`).
- Cache under the product repo `third_party/wix` (no machine-wide WiX install).
  Fetch pattern: download `wix311-binaries.zip` from
  `wixtoolset/wix3` release `wix3112rtm`, expand, copy bin folder.
- Always pass `-ext WixUtilExtension.dll` to **both** candle and light when the
  product uses quiet-exec custom actions.

## Pack shape

1. Stage a clean tree (scripts, config, third_party binaries the install needs).
2. `heat dir <stage> -cg <ComponentGroup> -gg -sfrag -srd -sreg -scom -dr INSTALLDIR -var var.StageDir -out HarvestedFiles.wxs`
3. Author `Product.wxs` with `InstallScope="perMachine"`, `SetDirectory` for the
   fleet install root (example: `C:\ai\<product>`), `MajorUpgrade`, embedded cab.
4. `candle -ext WixUtilExtension.dll -dProductVersion=... -dStageDir=<stage> Product.wxs HarvestedFiles.wxs`
5. `light -ext WixUtilExtension.dll -cultures:en-us -out dist/<name>-<ver>.msi *.wixobj`
6. Write `dist/<name>-<ver>.msi.sha256` as `<hash>  <filename>` (ASCII).
7. Publish the MSI (+ checksum) on the GitHub release; prefer MSI-only assets.

## Deferred quiet-exec (CAST IRON)

Post-install launch of an elevated `.cmd` / installer uses WiX
`CAQuietExec64` (`BinaryKey="WixCA"`).

| Mode | How to pass the command line |
|------|------------------------------|
| **Immediate** quiet-exec | Property `QtExecCmdLine` |
| **Deferred** quiet-exec (`Execute="deferred"`) | Property named after the **deferred CA Id** (becomes `CustomActionData`) |

Correct deferred pattern:

```xml
<CustomAction
    Id="SetInstallCmd"
    Property="RunInstall"
    Value="&quot;[INSTALLDIR]scripts\Install-Thing.cmd&quot;"
    Execute="immediate" />
<CustomAction
    Id="RunInstall"
    BinaryKey="WixCA"
    DllEntry="CAQuietExec64"
    Execute="deferred"
    Impersonate="no"
    Return="check" />
<InstallExecuteSequence>
  <Custom Action="SetInstallCmd" After="InstallFiles">NOT Installed OR REINSTALL</Custom>
  <Custom Action="RunInstall" After="SetInstallCmd">NOT Installed OR REINSTALL</Custom>
</InstallExecuteSequence>
```

Wrong: deferred CA + `Property="QtExecCmdLine"`. Symptom on install:

- `msiexec` exit **1603**
- log: `CAQuietExec64: Error 0x80070057: Failed to get command line data`
- files copy then roll back

Seen on `airc-console-v0.1.16` (agentic_irc issue #309). Fix is the property
table above; cut a patched MSI after rebuild.

## Verify after pack

1. SHA256 of the MSI matches the sidecar.
2. On a clean elevated box: `msiexec /i <msi> /qn /norestart` exits **0**.
3. Post-install service / files exist; no rollback in the MSI log.
4. If MSI CA is broken, admin-extract still recovers the staged tree:

```bat
msiexec /a product.msi /qn TARGETDIR=%TEMP%\msi-extract
```

Then copy the extracted product folder to the install root and run the
product's `Install-*.cmd` (unsigned downloads: Unblock-File + Bypass).

## Ownership

| Concern | Repo / skill |
|---------|----------------|
| Generic WiX MSI pack / QuietExec rules | this skill (`agentic_build`) |
| airc console product install / nick / Ergo | `agentic_irc` skill `airc-console` |
| Fleet job dispatch | `grok-build-fleet` / `bob-build-dispatch` |

Do not duplicate airc-console behaviour here. Point agents at `airc-console`
for console-specific flags (`-MachineId`, NSSM `AircConsole`, ergo.password).
