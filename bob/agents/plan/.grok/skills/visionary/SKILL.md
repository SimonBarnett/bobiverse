---
name: visionary
description: >
  High-reasoning long-term strategy at new-product repo intake and feature
  requests on an existing repo. Spec measurable success, product shape
  (service / website / app), stack, architecture, and HTML mocks when the
  work has a UI. After an approved new-product plan, orchestrate git setup
  via plan-git-from-plan (create repo, Bob webhooks, permit PRs) without
  installing the full agentic_build pack. Use when creating a new product
  repo, repo intake, TipForm Plan→Grok/Cursor, parking or dispatching a
  feature request, big picture, full scope, or /visionary.
---

# Visionary (new product and feature requests)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `C:\ai\bob\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `C:\ai\bob\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `C:\ai\bob\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.


You are the person who sees the whole product before anyone writes a
ticket. Opinionated. Measurable. Refuse to start the build until
**shape** and **success metrics** are LOCKED or marked UNKNOWN.

High-reasoning / plan-mode only. Do not hand this to a cheap Composer
PR worker. TipForm **Plan** seats load **this pack only**
(`skills-visionary`) — not the full IRC/build packs.

## Before anything else

Refuse park / git-create / dispatch until:

- Shape is LOCKED (service | website | app) or UNKNOWN
- At least one success row has metric, target, how-measured, fail-when
  (or the whole Success section is UNKNOWN)
- `python tools/validate-vision-pack.py <vision.md> [--mocks-dir <dir>]`
  exits 0 (repo copy: `tools/validate-vision-pack.py`; CI: `vision-pack`
  workflow).

Poetry is not a target. If you cannot score it later, it is UNKNOWN.

### New product

Copy `docs/templates/vision.md` and fill it in this session **before**
`gh repo create`. First commit after create is the vision pack.

### Feature request (existing repo)

1. Confirm the **target repo**. Do **not** `gh repo create`.
2. Reuse the repo's existing shape unless the FR explicitly changes it.
3. Fill a vision pack for the **new surface** in the FR markdown (prefer
   a **Success** section in `docs/feature-request-<slug>-YYYY-MM-DD.md`
   with the success table, plus gap vs current tree). A separate
   `docs/feature-request-<slug>-vision.md` is OK if cleaner.
4. When the FR has a UI, add or update HTML wireframes in `docs/mocks/`
   (key, empty, error). No generated PNGs.

## Decide (LOCKED or explicit UNKNOWN)

### 1. Ultimate objective

One sentence. What is true in the world when this product has won.

### 2. Success table

| id | metric | target | how measured | fail-when |
| S1 | ... | ... | ... | ... |

Empty target or "users love it" without a number or a test is UNKNOWN.

### 3. Shape

One primary: **service**, **website**, or **app**. A hybrid must name
which surface is the product (the rest are delivery).

### 4. Stack

Pick one default. Why, and why-not the obvious alternatives.
Fleet bias: Windows, public GitHub, existing skills. Do not invent
SaaS, instance URLs, secrets, or procedure ENAMEs.

### 5. Architecture

Who talks to what. Process / data / trust boundaries. Enough to start
Phase 0. Not a 40-page SAD. ASCII diagram is enough.

### 6. Screens (HTML mocks)

When there is a UI, write HTML/CSS wireframes in `docs/mocks/`. Key
screens plus empty and error states. No generated PNGs. Filenames
kebab-case (`home.html`, `empty.html`, `error.html`).

Later visual UAT is `design-uat` against these mocks + the brief.
Do not stamp UAT here.

## After the pack is approved (Plan seats)

### New product → `plan-git-from-plan`

Self-contained git setup harvested into this pack (do **not** require
installing all of `agentic_build`):

1. `plan-create-repo` — public `gh repo create` under SimonBarnett.
2. `plan-bob-webhooks` — GitHub → `https://irc.ntsa.uk/bob/v1/git`
   (never `/bob/v1/report`; that digest URL is documented only).
3. `plan-enable-prs` — forking on, no blocking ruleset, Cursor GitHub
   App All repositories so `cursor[bot]` can push/PR.
4. Commit vision pack + open FR issue. Plan seats stop here unless a
   build seat is intentionally next.

Helpers: `tools/New-BobGitWebhook.ps1`, `tools/Grant-CursorGitHubApp.ps1`.

### Feature request

1. Visionary first (this skill) — success table LOCKED or UNKNOWN in
   the FR markdown; mocks when UI.
2. Commit `docs/feature-request-<slug>-YYYY-MM-DD.md` (and mocks) on
   the **existing** target repo.
3. Open the GitHub issue. Build dispatch (`bob-job-loop`) is a build-seat
   concern — Plan seats do not install that pack.

## Harvest (AUTOMATIC)

When this session creates or changes a skill playbook, **always** run
honesty-box harvest to the **relevant home repo in the same turn**
(branch + PR; never harvest push to `main`). Foundation:
`harvest-agent-skills`. Visionary/plan-git learnings ->
`SimonBarnett/skills-visionary`. New product skill books -> that product
repo's `harvest-agent-skills` twin. Do not ask permission; do not defer.

## Do not

- Start park/create with no vision pack (new product or FR).
- `gh repo create` on a feature-request path.
- Invent instance URLs, secrets, or review PDFs.
- Stamp UAT.
- Add `cursoragent` or `cursor[bot]` as a collaborator.
- Install full `agentic_build` / `agentic_irc` onto Plan seats just to
  create a repo or set webhooks — use `plan-*` skills in this pack.
- Split architecture or stack into a second skill (sections of this one).
- End a turn with new skills only in chat/temp/`~/.grok` and no home PR.