# Plan agent moved to skills-visionary

The bobiverse in-tree Plan agent (`bob/agents/plan`, `bobiverse-bob-plan` skill, `build-bob-plan` CI) was removed in FR #8833 after the bob MSI started vendoring `PlanAgent.exe` from the skills-visionary release (FR #9354 / BOB-49).

**Canonical home:** https://github.com/SimonBarnett/skills-visionary

**Latest release (PlanAgent.exe):** https://github.com/SimonBarnett/skills-visionary/releases/latest

Tray **Plan** still starts `plan\PlanAgent.exe` from the bob-ear / bob MSI payload (downloaded and sha256-checked at pack time). Do not re-add a second Plan source tree under bobiverse.
