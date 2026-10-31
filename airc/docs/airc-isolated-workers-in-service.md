# Airc isolated workers  -  in-service only (no peer binaries)

**LOCKED** (operator 2026-10-31). Also recorded in `airc/VISION.md`.

## Rule

Any **isolated** process started from airc code (so the live IRC/console thread stays safe) MUST be:

1. **Owned by the Airc service deployment** under `<ai root>\airc` (and packaged MSI layout), and
2. Implemented by **importing / running airc-packaged modules or scripts** in a **new worker instance/process** the service starts,

and MUST NOT be:

- A **separate product binary** that is the verb’s runtime (`PriorityClient.exe`, `ExtensionWorker.exe`, `NetworkDiag.exe`, `LegionInstaller.exe`, or treating `airc-network-installer.exe` as the LEGION implementation path).

## Why

- One deployable surface: MSI / hotpatch / allow-list stay coherent.
- Verbs (UPDATE helpers, EXTENSION, NETWORK, LEGION, Priority Client, …) stay auditable as **service capabilities**.
- Isolation still protects the live console: spawn a **new instance**, but of **in-tree** code.

## Applies to (open Plan FRs)

| Capability | Vision / issues |
|------------|-----------------|
| Priority Client | `feature-request-airc-priority-client-2026-10-31.md` (#5275+); pack path `airc/priority-worker` (FR #5283) |
| EXTENSION | `feature-request-airc-extension-priority-web-2026-10-31.md` (#5290+) |
| NETWORK diag | `feature-request-airc-network-diag-2026-10-31.md` (#5302+) |
| LEGION | `feature-request-airc-legion-2026-10-31.md` (#5308+)  -  module import, not peer installer exe |
| UPDATE restart pack | `feature-request-airc-remote-update-restart-2026-10-31.md` (#5277+)  -  detached updater scripts already in deploy tree |

## Allowed

- Service-owned child process: `python`/`airc` worker entry that imports `airc_*` packages from the install tree.
- PowerShell under `airc\scripts` / `common\scripts` already laid down by the product MSI (e.g. `Update-BobiverseService.ps1`).
- Historical standalone tools in the MSI for **manual/offline** use only  -  not as the console-verb runtime.

## Fail-when

- Verb docs or code tell agents to run a peer `.exe` product to perform EXTENSION / NETWORK / LEGION / Priority.
- New worker ships as a separately versioned binary outside the airc service layout.
