---
name: plan-git-from-plan
description: >
  After an approved TipForm Plan (vision pack LOCKED), create the product
  git repo, point Bob git webhooks, and enable PR workflow — without
  installing the full agentic_build or agentic_irc skill packs. Use when
  Plan → Grok/Cursor seats finish a new-product plan, park new product,
  or /plan-git-from-plan. Steps: plan-create-repo, plan-bob-webhooks,
  plan-enable-prs. Vision content: visionary. Feature requests on an
  existing repo skip create.
---

# Plan → git setup (orchestrator)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `..\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `..\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `..\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.


TipForm **Plan** seats load **skills-visionary only**. This skill is the
self-contained bridge that used to live inside `agentic_build`
`bob-spec-intake` (create + webhook + Cursor app). Fleet build/IRC jobs
stay in their packs; Plan does not install them.

## When to run

**New product** — vision pack approved this session, validator green,
no target repo yet.

**Feature request** — do **not** run create. Confirm target repo; commit
FR markdown + mocks there; open the GitHub issue. Webhook/Cursor app
should already exist on that repo.

## New-product sequence (same turn)

0. **Visionary** — skill `visionary`. Fill `docs/templates/vision.md`.
   Refuse until shape + success LOCKED or UNKNOWN **and**

```
python tools/validate-vision-pack.py docs/vision.md --mocks-dir docs/mocks
```

   exits 0 (product `tools/` else sister clone of this repo).

1. **Create repo** — skill `plan-create-repo`.
   `gh repo create SimonBarnett/<name> --public`.

2. **Bob git webhook** — skill `plan-bob-webhooks`.
   Hook URL `https://irc.ntsa.uk/bob/v1/git` only.
   Digest `https://irc.ntsa.uk/bob/v1/report` is not a GitHub hook.
   **Gate:** `python tools/bob_git_hook.py SimonBarnett/<name>` must exit 0
   (exact hook config, ping 2xx, Jeeves `GIT ping` seen) **before step 4**.
   No push and no issue until it does. Anything earlier is never delivered.

3. **Permit PRs** — skill `plan-enable-prs`.
   Forking on; no blocking ruleset; Cursor GitHub App All repositories
   (Contents + Pull requests Read and write).

4. **First commit** (still this seat / orchestrator):

   - `docs/vision.md`
   - `docs/mocks/*.html` (when UI)
   - `docs/functional-spec.md` (LOCKED pulled from vision)
   - If the product is a skill pack: **honesty box foundation**
     `.grok/skills/harvest-agent-skills/SKILL.md` with frontmatter
     `github:` set to **this new product repo** (same pattern as
     agentic_build). AUTOMATIC harvest of later learnings is PR-only.

5. Open a GitHub issue titled from the spec, body linking those paths,
   label `feature-request` (`gh label create feature-request --force`
   first; a new repo has no such label and `gh issue create --label` fails).
   Push. Confirm Jeeves announced `GIT issues SimonBarnett/<name> opened #N`
   on `#bobiverse` (`~/.agentic-irc-bobiverse/irc.log`). If not, run
   `python tools/bob_git_hook.py SimonBarnett/<name> --replay-missed`.
   Tell the human the issue URL + SHA + the Jeeves line.

6. **Stop for Plan seats.** Do not run `bob-job-loop` /
   `bob-build-dispatch` unless a build seat with the build pack is
   intentionally next. Plan's job ends when git + hooks + PR path are
   ready and the vision pack is on the remote.

## Quick command checklist

```
# 0 validator
python tools/validate-vision-pack.py docs/vision.md --mocks-dir docs/mocks

# 1 create
gh repo create SimonBarnett/<name> --public --description "<objective>"

# 2 webhook + verify (gate: before ANY push/issue)
python tools/bob_git_hook.py SimonBarnett/<name>

# 3 Cursor app pages (Simon clicks All repositories if needed)
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Grant-CursorGitHubApp.ps1
```

## Honesty / harvest

These playbooks were harvested from `agentic_build` (and webhook URL
docs shared with `agentic_irc` / bobiverse). Changes land as PRs on
`SimonBarnett/skills-visionary` via `harvest-skills-visionary`. Do not
leave Plan-only git setup only in `~/.grok/skills`.

## Do not

- Install all of `agentic_build` or `agentic_irc` onto Plan seats.
- `gh repo create` on an FR path.
- Point GitHub at `/bob/v1/report`.
- Put secrets in git.
- Restart IRC.
- Stamp UAT.
- Add `cursoragent` / `cursor[bot]` as collaborators.