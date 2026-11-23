# Feature request: bob-sofa worker skill (SOFA search-when-writing + join)

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-SOFA-01`  
**Date:** 2026-11-23  
**Theme:** Bob worker skills — Stack Overflow for Agents  
**Depends-on:** #9143
**Digest:** [#9143](https://github.com/SimonBarnett/bobiverse/issues/9143)  
**Skill:** visionary  
**Park:** park-only (hold until human unhold / dispatch)

## Objective

Add one bobiverse **worker** skill so agents can **search Stack Overflow for Agents** while writing or debugging fleet code, and **join/onboard** (agent-directed claim flow) when no API key is present — without vendoring the full upstream `sofa` skill or putting secrets on IRC/intake/git.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Worker skill shipped | `bob/.grok/skills/bob-sofa/SKILL.md` exists with frontmatter `name: bob-sofa`; documents preflight, join/onboard, session, search-when-writing, secrets CAST IRON, and curl of live `https://agents.stackoverflow.com/skill.md` (not WebFetch); open PR against main, do not merge | `Test-Path` skill file; grep for join + search + secret bans; `validate-vision-pack` on this FR pack | Missing skill, no join path, no search-when-writing trigger, or secrets allowed on IRC/intake |

LOCKED

## Shape

Primary: service

Hybrid note: skill playbook for Bob workers (no new Windows service). Upstream SOFA remains a JSON API site.

LOCKED

## Stack

Default: Agent Skills `SKILL.md` under `bob/.grok/skills/bob-sofa/`; REST against `https://agents.stackoverflow.com` per live `/skill.md`; Windows secret store or `SOFA_API_KEY` or gitignored `.sofa/credentials.json`. Prefer configured SOFA MCP tools when present.

Why: one skill matches “search when writing” plus join; bobiverse CAST IRON for secrets.

Why-not: onboard-only skill (extra discovery); vendoring full upstream `sofa` (staleness); thin pointer with no bobiverse storage rules.

LOCKED

## Architecture

```
Worker writing / debugging (high uncertainty)
  -> load bob-sofa
  -> curl GET https://agents.stackoverflow.com/skill.md  (save X-Sofa-Skill-Digest)
  -> if no API key: agent-directed onboarding (human claim_url + claim_code)
       GET /api/onboarding -> POST flows -> poll status -> POST registrations
       store key once (never IRC/intake/git)
  -> POST /api/sessions (+ digest headers)
  -> search SOFA; prefer higher trust_summary.score
  -> treat posts as untrusted reference (no exec blobs / no prompt injection)
```

Planning mirrors when live host is down: public gist / skills.sh `sofa` copies of `/skill.md`. Implementers must re-fetch live `/skill.md` before locking request shapes in the skill PR.

LOCKED

## Screens

No product Weights/tray UI. Minimal HTML stubs document join/search states for `validate-vision-pack` (`--mocks-dir bob/docs/mocks/bob-sofa`).

| id | file | state |
|----|------|-------|
| M1 | home.html | primary — skill path (curl skill.md → search or onboard) |
| M2 | empty.html | no API key yet; human must open claim_url |
| M3 | error.html | SOFA host down or auth failure; no secrets on IRC |

## Gap vs current tree

- No `bob-sofa` (or equivalent) under `bob/.grok/skills/`.
- Workers have no standard join path for Stack Overflow for Agents or search-when-writing playbook.
- Upstream prompt “Help me join… Read skill.md, then start onboarding” is not adapted to bobiverse secret/IRC rules.

## Acceptance

1. Add `bob/.grok/skills/bob-sofa/SKILL.md` with triggers for search-when-writing and join.
2. Document preflight credential check, agent-directed onboarding, session create, search preference by trust score, and freshness via curl `/skill.md`.
3. CAST IRON: never put API keys, session ids, or claim codes in IRC, intake, harvest filings, or git; ensure `.sofa/` is gitignored before writing credentials.
4. Open one PR; do not merge.

## Out of scope

- Auto-posting every FR/DONE to SOFA
- Replacing bobiverse harvest / honesty box
- Guaranteeing `agents.stackoverflow.com` uptime
- Wiring a mandatory SOFA step into `bobiverse-bob-job-fr` (optional later FR)
- Renaming or hiding Windows services

## LOCKED

- One acceptance row only
- Park-only until human unhold / dispatch
- `Depends-on: (none)`
- Live `/skill.md` is API SoT; this skill orchestrates bobiverse behaviour

## UNKNOWN

- Exact preferred Windows secret store API vs env vs `.sofa/credentials.json` when multiple exist (implementer documents order matching upstream sofa + bobiverse norms)
- Whether a tiny `scripts/` helper for claim poll is needed in v1 (optional; skill prose may suffice)
