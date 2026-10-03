<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-setup-remote-grok-bot-2026-09-20.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: harvest skill — setup remote Grok Bot / agent on Windows (flamingo playbook)

**Date:** 2026-09-20  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/1  
**Raised by:** Slab (Simon: harvest remote Grok agent setup)  
**UAT + hostile MRB owner:** Slab (standing order — originating agent)  
**Build orchestrator:** Bob  

## Ask

Park and implement reusable skill `setup-remote-grok-bot` (under `.grok/skills/`) from the flamingo playbook in issue #1: CLI + desktop install via Mode 3 put+spawn, interactive sign-in (no Mode-3 GUI), no-GPU shortcut, window-state 0×0 blank fix, Edge/Steam memory relief, ListMachines connected lag, dual control planes (desktop machineId + Mode 3 fallback).

Complementary to [agentic_irc#2](https://github.com/SimonBarnett/agentic_irc/issues/2) (DUMB protocol ergonomics) — this FR is end-to-end remote Grok Bot fleet onboarding.

## Acceptance (from issue #1)

1. Skill `.grok/skills/setup-remote-grok-bot/SKILL.md` with clear when-to-use triggers.
2. Playbook: CLI install, desktop via DUMB put+spawn, interactive sign-in, no-GPU shortcut, window-state reset, memory relief, Mode 3 restart, ListMachines connected check.
3. Cross-link agentic_irc Mode 3 DUMB traps and `unstick-grok-bot`.
4. Append `docs/skill-harvest-log.md`.
5. Update `Test-Pack.ps1` BT0 skills list if required.
6. Commit/push. Slab UAT skill text vs flamingo; hostile MRB back to Bob.

## Non-goals

No secrets/PINs/connector.key in docs. No Win95 TLS claims. Do not replace invite-airc / Mode 3 protocol work in agentic_irc.
