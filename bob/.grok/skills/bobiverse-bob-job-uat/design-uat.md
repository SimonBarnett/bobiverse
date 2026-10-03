# Visual UAT gates absorbed from bob-design-uat

Source repository: https://github.com/SimonBarnett/bob-design-uat
Source skill: `.grok/skills/design-uat/SKILL.md`

This companion is part of `bobiverse-bob-job-uat`. It preserves the design-UAT gates while the standalone repository is retired. Workers do not stamp `ready for human UAT`; Bob alone owns that human stamp.

## Inputs and companions

Read the original brief first. Review supplied screenshots, mocks, PDF pages, artboards, or authorized Playwright stills only; do not invent pixels or routes. Companion skills are `playwright-design` (authorized route/viewport stills), `pdf-design` (PDF pages), `illustrator-design` (AI artboards), `graphics-design` (loose graphics packs), and `uat-video-pack` (human-speed evidence after functional PASS). Every rendered artifact is scored here with G1-G3.

## Procedure

1. Inventory every artifact and map it to the brief (screens, states, breakpoints, and required flows).
2. Run G1, then G2, then G3 on every image. A FAIL stops the pass; do not soften later gates.
3. Add missing-state and brief-fidelity rows.
4. Emit a nit table with gate, location, expected, actual, severity, and measurements. Empty nits means no defect found, not a human-UAT stamp.

## G1 — spelling in image

Read/OCR every visible word and compare it with the brief and glossary: headings, labels, CTAs, product names, errors, legal lines, casing, and placeholder text. Any typo or wrong product name is a **blocker** and fails G1; unread visible text is also FAIL. Never downgrade a spelling failure to a cosmetic nit.

## G2 — layout and pixel deltas

Compare each named region with the brief or reference mock. Record measurable `delta_px` or `delta_hex` for every G2 row. Check spacing, alignment, size, color, contrast, clipping, overflow, broken grids, and positive overlap between regions that must be separate. A claimed drift without a measurement is incomplete. Playwright may pre-compute bounding-box overlap, but verify it on the PNG.

## G3 — hallucination and invented chrome

Inventory every visible control, copy block, image, brand, statistic, navigation item, page, flow, and testimonial. Mark each `in_brief: yes` or `NOT_IN_BRIEF`; fail invented or unauthorized chrome even when pixels are otherwise perfect.

## Severity and verdict

- `blocker`: any G1 typo, missing required state, wrong/missing primary CTA, invented primary navigation, or brief contradiction.
- `major`: contrast failure, clipping/overflow, 8px+ misalignment, or wrong named color token.
- `nit`: measured 1–2px drift or harmless decorative difference.

A blocker forces FAIL. Majors that break the task also FAIL. With only nits, report `PASS-nits candidate`. With all gates green, report `candidate PASS-UAT, Bob stamp required`. Workers must not post `PASS-UAT` or `ready for human UAT` as their own final stamp.

## Required nit row

| gate | where | expected | actual | severity | delta_px | delta_hex |
|---|---|---|---|---|---|---|
| G1/G2/G3/brief | artifact + region | brief/mock requirement | observed pixels | blocker/major/nit | G2 measurement | G2 measurement |

## Fixture calibration

Before real visual UAT, read each `fixtures/<case>/brief.md` and `screenshot.png`, emit the expected G1/G2/G3 nit list, and compare it with `expected-nits.yaml`. `T-A00-clean` must produce zero nits; bad cases must hit the expected gate/class. Preserve the source fixture and validation intent when fixtures are available in the product repository.

## Evidence and safety

Include the artifact filenames, brief/spec references, OCR/transcription, measurements, gate scores, and raw commands/output without secrets. Do not stamp human UAT, push main, merge your own PR, invent routes/assets, or commit passwords/tokens/API keys/private hosts. Run the source skill's validation tooling when changing this absorbed material.