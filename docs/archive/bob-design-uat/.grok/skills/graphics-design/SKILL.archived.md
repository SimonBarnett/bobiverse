<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path .grok/skills/graphics-design/SKILL.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: graphics-design
description: >
  Visual UAT of general graphics assets (PNG, JPG, WebP, SVG, GIF stills,
  icon sheets, brand kits) against a brief using design-uat G1-G3. Use when
  the user says graphics UAT, asset review, icon sheet, SVG vs brief, brand
  kit check, raster pack, or /graphics-design. Does not stamp ready for
  human UAT.
---

# Graphics design UAT

Companion to `design-uat` for **loose graphics packs** that are not a full
PDF deck or Illustrator artboard set. Still: brief first, then pixels. Do
not invent assets. Do not stamp ready for human UAT (Bob only).

## When to use

- Icon sheets, social crops, email headers, SVG icons, sticker packs.
- Mixed raster/vector folders named in the brief.
- Brand kit spot-checks (logo variants, color chips, type specimens).

## Inputs

- **Brief:** asset list, sizes, formats, forbidden variants.
- **Artifacts:** supplied files only. SVG: rasterize or open as image for
  G1-G3; do not claim path math without a render.

## Procedure

1. Inventory files vs brief checklist (missing asset = brief/G2 row).
2. For each visible render, run **design-uat** G1 -> G2 -> G3.
3. Extra graphics checks:
   - Wrong dimensions / aspect vs brief (G2 `delta_px`).
   - Transparent edges, compression halos, muddy downscales (G2).
   - SVG text that fails spelling once rasterized (G1).
   - Extra variants or watermarks not in brief (G3).
4. Report with asset filename in `where`.

## Relation to siblings

| Skill | Prefer when |
|-------|-------------|
| `pdf-design` | Multi-page PDF / print page stack |
| `illustrator-design` | `.ai` artboards / Illustrator exports |
| `graphics-design` | Loose asset folders, SVG/PNG packs |
| `design-uat` | Product UI screenshots / mocks |

## Do not

- Skip G3 inventory on icon sheets ("too many icons").
- Treat SVG source as reviewed without a visual.
- Stamp ready for human UAT.