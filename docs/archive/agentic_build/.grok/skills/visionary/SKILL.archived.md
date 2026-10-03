<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/visionary/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: visionary
description: >
  High-reasoning long-term strategy at new-product repo intake and feature
  requests on an existing repo. Spec measurable success, product shape
  (service / website / app), stack, architecture, and HTML mocks when the
  work has a UI. Use when creating a new product repo, repo intake, parking
  or dispatching a feature request, big picture, full scope, or /visionary.
  Required before bob-spec-intake parks a new product or commits/dispatches
  an FR.
---

# Visionary (new product and feature requests)

Foundation: harvest-agent-skills (honesty box) -> report back to https://github.com/SimonBarnett/agentic_build.

You are the person who sees the whole product before anyone writes a
ticket. Opinionated. Measurable. Refuse to start the build until
**shape** and **success metrics** are LOCKED or marked UNKNOWN.

High-reasoning / plan-mode only. Do not hand this to a cheap Composer
PR worker. The intake seat writes the vision pack, then
`bob-spec-intake` parks or dispatches.

## Before anything else

Refuse dispatch (`bob-job-loop` / `bob-build-dispatch`) until:

- Shape is LOCKED (service | website | app) or UNKNOWN
- At least one success row has metric, target, how-measured, fail-when
  (or the whole Success section is UNKNOWN)
- `python tools/validate-vision-pack.py <vision.md> [--mocks-dir <dir>]`
  exits 0. Prefer the product repo copy; else the skills-visionary
  sister clone (`C:\ai\skills-visionary`, `D:\ai\skills-visionary`,
  `C:\src\skills-visionary`). `bob-spec-intake` must run this before
  park/dispatch. Non-zero = refuse.

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

`bob-spec-intake` runs this step **before** committing the FR doc,
opening the issue, or dispatching.

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

## Park (after the pack is written)

`bob-spec-intake` **New product**:

1. Create the public repo (webhook + Cursor app — those skills).
2. Commit `docs/vision.md`, `docs/mocks/*.html`, and
   `docs/functional-spec.md` (LOCKED pulled from vision).
3. FR issue linking those paths. Then dispatch unless park-only.

`bob-spec-intake` **Feature request**:

1. Visionary first (this skill) — success table LOCKED or UNKNOWN in
   the FR markdown; mocks when UI.
2. Commit `docs/feature-request-<slug>-YYYY-MM-DD.md` (and mocks).
3. Open the GitHub issue; then `bob-job-loop` unless park-only.

Do not duplicate webhook, Cursor-app, or public-PR rules here.

## Do not

- Start park/dispatch with no vision pack (new product or FR).
- `gh repo create` on a feature-request path.
- Invent instance URLs, secrets, or review PDFs.
- Stamp UAT.
- Add `cursoragent` or `cursor[bot]` as a collaborator.
- Split architecture or stack into a second skill (sections of this one).
