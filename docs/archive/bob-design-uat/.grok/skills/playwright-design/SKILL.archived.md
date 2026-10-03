<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path .grok/skills/playwright-design/SKILL.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: playwright-design
description: >
  Capture authorized app routes, viewports, and UI states with Playwright,
  then score PNG stills with design-uat G1-G3. Use when the user says
  Playwright UAT, visual capture, route screenshot, viewport still,
  live UI capture, or /playwright-design. Does not stamp ready for human UAT.
---

# Playwright design capture

Companion to `design-uat` for **browser capture** before G1–G3 scoring.
Brief first. Capture only routes, viewports, and states the brief names.
Do not invent product URLs. Do not stamp ready for human UAT (Bob only).

## When to use

- Product UI on a dev/staging base URL named in the brief.
- Multiple viewports or breakpoints the brief requires.
- Interactive states (empty, error, loaded) the brief lists — capture stills
  after each state is reached.

## Inputs

- **Brief:** allowed base URL(s), route list, viewports, states, forbidden
  flows. Brief wins over operator habit.
- **Environment:** local or staging only when the brief authorizes it.
- **Output folder:** write PNGs with stable names (`route-viewport-state.png`).

## Procedure

1. Parse brief → capture plan (routes × viewports × states). Missing plan
   row for a required state = stop and report (do not guess URLs).
2. With Playwright, navigate each authorized URL, set viewport, reach the
   named state, save **full-page or region** PNGs per brief.
3. **Layout overlap (G2 adjunct, #71):** when the brief forbids intersecting
   chrome or when overlap is a stated acceptance row, run a bbox intersection
   pass on visible controls before scoring stills. Tag hits as **G2** /
   `class: layout` / overlap in `where`. Example hook:
   `tools/LayoutOverlap-PlaywrightHook.example.mjs`. Calibration fixture:
   `fixtures/T-G04-overlap/`.
4. Hand every PNG to **`design-uat`**: run **G1 → G2 → G3** on each still.
5. Report using `docs/templates/design-uat-report.md`; put capture filename
   in `where`. Verdict rules are `design-uat` only.

## Capture rules

- Use only base URLs and paths in the brief (or explicit operator paste tied
  to the brief). No live customer production URLs unless the brief names them.
- No PII in captures: use fixture accounts and redacted data from the brief.
- Do not log or commit `password=` or API key assignments.
- Playwright is for **still capture** — scoring stays in `design-uat`.

## Relation to siblings

| Skill | Prefer when |
|-------|-------------|
| `playwright-design` | Live app routes / viewports / UI states → PNG |
| `design-uat` | Scoring supplied or captured PNG/JPG/WebP mocks |
| `pdf-design` | Multi-page PDF / print page stack |
| `illustrator-design` | `.ai` artboards / Illustrator exports |
| `graphics-design` | Loose asset folders, SVG/PNG packs |

## Do not

- Replace `design-uat` gates with "looks fine in the browser."
- Capture routes or chrome not authorized in the brief (G3 risk).
- Stamp ready for human UAT.
