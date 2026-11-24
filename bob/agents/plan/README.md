# Plan agent moved to skills-visionary

The bobiverse in-tree Plan agent (`bob/agents/plan`, `bobiverse-bob-plan` skill, `build-bob-plan` CI) was removed in FR #8833 after the bob MSI started vendoring `PlanAgent.exe` from the skills-visionary release (FR #9354 / BOB-49).

**Canonical home:** https://github.com/SimonBarnett/skills-visionary

**Latest release (PlanAgent.exe):** https://github.com/SimonBarnett/skills-visionary/releases/latest

Tray **Plan** starts `vendor\plan\PlanAgent.exe` (FR #9605; Pack/Sync mirror of the bob-ear / bob MSI `plan\PlanAgent.exe` payload downloaded and sha256-checked at pack time). Do not re-add a second Plan source tree under bobiverse.
