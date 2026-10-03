<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path .grok/skills/illustrator-design/SKILL.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: illustrator-design
description: >
  Visual UAT of Adobe Illustrator artwork and AI exports (artboards, logos,
  vector comps) against a brief. Export or screenshot artboards, then run
  design-uat G1-G3. Use when the user says Illustrator, .ai review, artboard
  UAT, vector logo vs brief, AI export, or /illustrator-design. Does not
  stamp ready for human UAT.
---

# Illustrator design UAT

Companion to `design-uat`. Native `.ai` is not pixels — **export or
screenshot each artboard** (PNG/JPG/WebP or PDF page) before gating. Do
not invent artwork. Do not stamp ready for human UAT (Bob only).

## When to use

- Brief calls for Illustrator deliverables (logo, icon set, poster, pack).
- Operator supplies `.ai` exports, artboard PNGs, or PDF from AI.
- Brand mark / vector chrome must match locked brief geometry or tokens.

## Inputs

- **Brief:** artboard names, sizes, colors (hex/Pantone if locked), copy.
- **Artifacts:** one image (or PDF page) per artboard. Name files after
  artboard labels when possible.

## Procedure

1. List artboards vs brief (missing artboard = G2/brief row).
2. For each artboard render, run **design-uat** G1 -> G2 -> G3.
3. Extra Illustrator checks:
   - Wrong artboard size vs brief (G2 `delta_px`).
   - Spot/process color token mismatch (G2 `delta_hex`).
   - Expanded vs outlined type that changes spelling (G1).
   - Live effects / raster embeds that invent chrome (G3).
   - Logo clear-space / lockup violations called out in the brief (G2).
4. Report with page/artboard id in `where`. Link `design-uat` severity rubric.

## Do not

- Score the binary `.ai` file without a visual export.
- Pass on "vectors are infinite resolution" — still measure layout vs brief.
- Stamp ready for human UAT.