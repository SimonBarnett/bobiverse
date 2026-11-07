# FR-OC-SYNC: Sync/ff + rebuild bob-worker so live exe selects OpenCode

## Goal

On a fleet box with `opencode.exe` and known OpenCode fuel, `bob-worker --dry-run` (and tray Agent after Grok/Cursor exhaust) can decide `opencode`. Today the installed frozen exe and fuel helper are pre-#6120.

## Deliverables

- Document/assert Sync-BobiverseFromRepo (or MSI upgrade) brings `Get-BobAgentFuel.ps1` opencode section, `Get-BobOpencodeFuel.ps1`, `common/scripts/opencode_fuel.py`, `bob-setup-opencode` skill.
- Rebuild and ship `bob-worker.exe` that contains OpenCode selection/launch (source-only ff is not enough).
- Pin: after pack, `--dry-run` JSON `decision=opencode` when fixtures show Grok+Cursor exhausted, OpenCode **usable** fuel (positive free or a usable per-model reading --- not aggregate Go alone when all models exhausted), and exe present; or ASCII/pyinst probe for opencode markers.
- Start guidance: new seat after rebuild (hashed run-copy); never resume.

## Testable

1. Fresh install/Sync tree: `Get-BobAgentFuel.ps1` JSON includes `opencode` object.
2. Rebuilt `bob-worker.exe` `--dry-run` with fuel fixture -> `decision` is `opencode` when Grok/Cursor unavailable and OpenCode usable fuel is known (free>0 or usable model reading).
3. Pre-#6120 exe without opencode markers fails the pin (regression guard).

## Refs

- Non-gap core: #6120 / #6121 / #6134
- Related paint: #6146 / #6147
