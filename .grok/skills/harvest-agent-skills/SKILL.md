---
name: harvest-agent-skills
description: >
  FOUNDATION: harvest playbooks back as PRs to SimonBarnett/bobiverse.
  Use when harvest skills, honesty box, or /harvest-agent-skills.
github: https://github.com/SimonBarnett/bobiverse
---

# harvest-agent-skills (bobiverse)

**Home:** https://github.com/SimonBarnett/bobiverse

Promote learned install/maintain procedures as PRs. Prefer scripts. No main pushes for harvest.

## Where to put lessons

| Area | Path |
|------|------|
| Jeeves / Ergo host / BobJeeves cutover / DPAPI | `.grok/skills/bobiverse-jeeves/SKILL.md` |
| Bob ear / tray / outbox→airc | `.grok/skills/bobiverse-bob/SKILL.md` |
| Airc console / AircConsole leftover | `.grok/skills/bobiverse-airc/SKILL.md` |
| Operator checklist | `docs/post-install.md` |
| This harvest index | `docs/skill-harvest-log.md` |

Branch `harvest/…` or `fix/…` → PR to `main`. Bump `src/VERSION` when the change must ship in the next MSI pack.
