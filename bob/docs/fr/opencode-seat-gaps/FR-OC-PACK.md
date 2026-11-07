# FR-OC-PACK: MSI/Sync ships OpenCode fuel helpers + skill

## Goal

After Sync-BobiverseFromRepo / MSI upgrade, the flat install contains every file OpenCode selection and the launch wrapper need.

## Deliverables

- Sync/MSI include: flat `scripts/opencode_fuel.py` (composed from `common/scripts`), `tools/Get-BobOpencodeFuel.ps1`, updated `Get-BobAgentFuel.ps1`, `bob/.grok/skills/bob-setup-opencode/**` (also worker Shared book).
- Layout pin test (paths exist after Sync/Pack compose; missing helper fails the pin).
- `Get-BobOpencodeFuel.ps1` resolves `scripts\opencode_fuel.py` then `common\scripts\opencode_fuel.py` as files (FR #6159).
- Wrapper `_resolve_opencode_fuel_helper_path` finds helper on install-root flat `scripts/` (threaded via `build_launch` / `describe_agent_child_launch` `install_root=`).

## Testable

1. Sync compose fixture lists the OpenCode paths.
2. `Get-BobAgentFuel` on composed install returns `opencode` key (fixture ok).
3. Missing helper fails the pin.
