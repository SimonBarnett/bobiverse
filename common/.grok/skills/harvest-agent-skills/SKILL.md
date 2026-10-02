---
name: harvest-agent-skills
description: >
  FOUNDATION: harvest playbooks back as PRs to SimonBarnett/bobiverse.
  Use when harvest skills, honesty box, or /harvest-agent-skills.
github: https://github.com/SimonBarnett/bobiverse
---

# harvest-agent-skills (bobiverse)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.


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
