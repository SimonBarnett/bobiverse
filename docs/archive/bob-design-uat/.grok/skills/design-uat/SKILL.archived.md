<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path .grok/skills/design-uat/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: design-uat
description: >
  Bob visual UAT of product UI. Examine screenshots and mocks against the
  original brief for spelling mistakes, hallucinations, UI fuck-ups,
  pixel-perfect layout, and brief nits. Use when Bob says UAT, visual UAT,
  screenshot review, mock vs brief, spelling-in-image, G1 G2 G3 gates,
  pixel-perfect, or /design-uat. Workers do not stamp ready for human UAT
  (Bob only).
---

# Design UAT

Read the original brief first. Then inspect every supplied image. Report defects with gate tags **G1**, **G2**, **G3**. Do not praise.

**MRB for this skill repo:** `SimonBarnett/bob-design-uat` issue #1. Product PRs use that product's FR + `bob-hostile-mrb`.

## Inputs

- **Brief:** issue, `docs/*.md`, FR markdown, or operator paste. Brief wins.
- **Artifacts:** PNG/JPG/WebP, Figma exports, PDF pages as images. Do not invent pixels.
- **Optional:** reference mock for pixel-perfect **G2**.

## Companion skills

| Skill | Artifact |
|-------|----------|
| `playwright-design` | Authorized app routes / viewports / states → PNG stills (#57) |
| `pdf-design` | Multi-page PDF / print page stack |
| `illustrator-design` | Illustrator `.ai` artboards / AI exports |
| `graphics-design` | Loose PNG/SVG/icon/brand-kit packs |
| `mrb-project-management` | FR intake, BT0 evidence, MRB chairing on this repo (#49) |
| `uat-video-pack` | Human-speed video evidence pack after functional PASS (Jester/Simon 2026-09-24) |

`playwright-design` captures browser stills; every companion still runs **G1–G3**
from this skill after captures or page/artboard/asset renders exist. `uat-video-pack`
owns human-speed video edit (not functional assert); workers never stamp ready for human UAT.

## Procedure (issue #2)

1. Inventory artifacts and map each to brief sections (screens, states, breakpoints).
2. Run **G1 → G2 → G3** on each image. A FAIL stops the pass — do not score later gates as PASS to soften the verdict.
3. Then brief-fidelity rows where a state is missing.
4. Emit nit list using `docs/templates/design-uat-report.md` (include the G1/G2/G3 scorecard). Empty nits means no defect found — not a UAT stamp.

## G1 — Spelling-in-image (OCR / vision)

Visible words must match the brief and ordinary spelling. Fail on typos, wrong product names, missing letters, lorem left in place, inconsistent casing when brief is explicit. **Never approve spelling you did not read** (OCR the pack if it is large). Unread visible text is FAIL.

**Fail-closed (#6):** any G1 typo in chrome, labels, body copy, or product names (vs the brief or glossary) is a **blocker**, not a cosmetic nit. The check **FAIL**s. Do not downgrade a misspelling to PASS-nits.

## G2 — Layout-delta / pixel-perfect

Compare regions, spacing, alignment, sizes, and colors to the brief or supplied mock. Report deltas in px or hex when visible. "Looks close" / "close enough" is not a pass. Include contrast, clipping, overflow, broken grids, and **overlapping elements** (visible bbox intersection between controls or copy regions the brief treats as separate) here. No recorded delta when a drift is claimed is FAIL.

**Overlap (#71):** when the brief requires non-intersecting regions, FAIL on any positive overlap area between those regions. Record `delta_px` as overlap extent when measurable. Playwright capture may pre-compute pairs via `tools/LayoutOverlap-PlaywrightHook.example.mjs`; still verify on the PNG. Fixture: `fixtures/T-G04-overlap/`.

**Deltas (#8):** every G2 row must include at least one of `delta_px` or `delta_hex` in the report and fixture `expected-nits.yaml`. A G2 without a measurement is incomplete.

## G3 — Hallucination / invented chrome

Fail on controls, brands, nav items, invented buttons, fake stats, extra pages, data, imagery, testimonials, extra buttons, prices, or copy the brief did not authorize. Tag `NOT_IN_BRIEF` when the invention is obvious. Perfect pixels do not save invented chrome.

**Inventory (#7):** list every visible chrome, copy, image, and flow item; mark each `in_brief` (yes) or `NOT_IN_BRIEF`. Missing inventory is incomplete even if no hallucination is found.

## Per-image walk

On each artifact, in order:

1. **Read every visible word** (G1). Transcribe CTAs, headings, badges, errors, legal lines, and labels. Compare to the brief and glossary. Any typo vs the brief or glossary is a G1 **blocker** (not only product names).
2. **Overlay brief regions** (G2). For each named region in the brief, mark found / missing / wrong size. Measure deltas (px) and color (hex) for every G2 row. Clipped text and contrast fails live here.
3. **Inventory chrome/copy/images/flows** (G3). List each visible item; mark `in_brief` or `NOT_IN_BRIEF`. Subtract brief objects — anything unauthorized is invented chrome.
4. **Missing artifact** — if the brief requires a state/breakpoint and no image was supplied, add a G2 or `brief` row. Do not invent pixels to fill the gap.

## Severity rubric

| Severity | Use when |
|----------|----------|
| blocker | Wrong or missing primary CTA; **any G1 typo** (chrome, labels, body copy, product/brand names vs brief or glossary); invented primary nav; required screen/state absent; copy that contradicts the brief. |
| major | Contrast fail; overflow/clip; 8px+ misalignment vs mock; extra secondary chrome; wrong hex when brief names a token. |
| nit | 1–2px drift; decorative extras that do not change the task. (Misspellings vs brief/glossary are G1 blockers, not nits.) |

A single blocker forces verdict **FAIL**. Majors without blockers are still **FAIL** if they break the task; otherwise **PASS-nits candidate**. Zero defects is **candidate PASS-UAT, Bob stamp required** — not a UAT stamp.

## Brief nits

Review the brief for contradictions, missing acceptance, or copy no UI can satisfy. Tag gate `brief` in the report.

## Nit row format

| Field | Value |
|-------|--------|
| gate | G1 \| G2 \| G3 \| brief |
| where | artifact + region or brief heading |
| expected | from brief or mock |
| actual | what you see |
| severity | blocker \| major \| nit |
| delta_px | G2 only — px delta when measured |
| delta_hex | G2 only — hex delta when measured |

## Verdict (workers)

Allowed only:

- **FAIL** — blockers present (any of G1/G2/G3 FAIL).
- **PASS-nits candidate** — nits only; product PR may go to hostile MRB.
- **candidate PASS-UAT, Bob stamp required** — all gates green; **Bob** still applies the human UAT stamp.

Body must include **G1 / G2 / G3** (PASS or FAIL each). Bob alone may declare **ready for human UAT**. Workers must not post that phrase as their own stamp or final **PASS-UAT**.

## Do not

- Push `main` or merge your own PR.
- Second-create this repo or re-take owner-locked FRs.
- Commit secrets or `password=` / API key assignments.
- Treat Halloy as a fleet nick (Simon client).

## Fixture pack (#3 + absorbed #5)

Before real UAT, calibrate on `fixtures/`:

1. For each `fixtures/<case>/` read `brief.md` then `screenshot.png`.
2. Emit nits in the report template (G1/G2/G3 + severity).
3. Compare to that case's `expected-nits.yaml` (schema in `fixtures/README.md`).
4. **T-A00-clean** must produce **zero** nits. Bad cases must hit the expected `class` / `gate`.
5. Output is a nit list only. Do not stamp UAT.

Regenerate stills with `tools/New-GoldenFixturePngs.ps1`. Validate with `tools/Validate-DesignUatFixtures.ps1` (also invoked from BT0).

## Repo self-check

When changing this skill repo, run `tools/Validate-DesignUatSkill.ps1` (BT0).
