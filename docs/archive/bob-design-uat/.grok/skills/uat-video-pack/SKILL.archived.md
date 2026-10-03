<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path .grok/skills/uat-video-pack/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: uat-video-pack
description: >-
  Build a human UAT video pack from a successful product walk: human-speed
  playback, visible mouse, click ripples, idle cuts, burn-in subtitles, correct
  display capture. Use when Simon or Bob asks for a human pack, video evidence
  pack, screen-record pack, or /uat-video-pack. Not for fast functional tests
  (those stay in the product test skill). Workers do not stamp ready for human
  UAT (Bob only).
---

# UAT video pack

Use this skill **only after** the product test already **PASS**ed on the fast path (or the operator explicitly asks for a human pack of a known-good walk). Do not run video capture as the default smoke. Failures stay CASE / nits on the product test skill — do not film a FAIL hoping it becomes evidence.

**MRB for this skill repo:** `SimonBarnett/bob-design-uat`. Product PRs use that product's FR + hostile MRB.

## When

- Operator asks for a **human UAT pack** / video evidence pack.
- Orchestrator routes here after a functional PASS when human evidence is required.
- Companion to `design-uat` / product test skills — this skill owns **recording + edit**, not functional assert.

## Hard rules

1. Play at **human speed** (not sped up).
2. Keep the **mouse cursor moving** visibly through navigation. For Linux x11grab use `ffmpeg` with `-draw_mouse 1`.
3. Add **click animations / ripples** so reviewers see where clicks landed.
4. **Cut long idle** / no-activity stretches. Do not ship raw linger-heavy captures.
5. **Burn in subtitles** describing what is on screen (form, DOCNO, step, field).
6. Capture the **correct display** that shows the product UI. Wrong DISPLAY = empty desktop or wrong window (reject and re-capture).
7. Show **navigation and clicks**, not a static end state only.
8. Do not invent UI. If the walk cannot be shown, stop and report missing evidence — do not stamp PASS-UAT.

## Inputs

- Confirmed **PASS** walk notes (steps, IDs, company/env) from the product test skill.
- Target host / display / window hints from the operator or instance config.
- Output path for the finished `.mp4` (and optional stills).

## Procedure

1. Confirm the functional result is already PASS (or operator override). If not PASS, refuse video pack and point back to the test skill.
2. Verify the capture target: correct DISPLAY / monitor / app window is visible before recording.
3. Record the successful path at human speed with mouse visible.
4. Edit: cut idle, burn-in subtitles, add click ripples/animations.
5. Spot-check the file opens and shows product UI (not empty desktop). Bad capture → discard and re-run.
6. Deliver path + short caption list (what each subtitle segment covers). Do **not** stamp "ready for human UAT" — Bob chairs that stamp.

## Outputs

| Artifact | Required |
|----------|----------|
| Edited human-speed `.mp4` | yes |
| Subtitle / caption list (burned in or sidecar notes) | yes |
| Capture meta (DISPLAY, host, wall-clock) | yes |
| Raw unedited linger capture | no (do not ship) |

## Do not

- Require video on every functional smoke (that is the product test skill's fast path).
- Ship empty-desktop or wrong-DISPLAY recordings as PASS evidence.
- Speed up the pack for "brevity."
- Push `main` or merge your own PR on this repo.
- Commit secrets.

## Relationship to other skills

| Skill | Role |
|-------|------|
| Product test skills (e.g. Priority fast UAT) | Functional PASS/FAIL + CASE; screenshots only on full PASS |
| `design-uat` | Still-image G1–G3 vs brief |
| `playwright-design` | Authorized still captures |
| **`uat-video-pack` (this)** | Human-speed video evidence pack after PASS |
