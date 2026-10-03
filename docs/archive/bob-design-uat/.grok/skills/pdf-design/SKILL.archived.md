<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path .grok/skills/pdf-design/SKILL.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: pdf-design
description: >
  Visual UAT of PDF design artifacts (briefs, decks, print comps, multi-page
  exports). Rasterize or page-image each page, then run design-uat G1-G3.
  Use when the user says PDF UAT, PDF vs brief, print PDF review, page
  export, Acrobat proof, or /pdf-design. Does not stamp ready for human UAT.
---

# PDF design UAT

Companion to `design-uat`. PDFs are **paged artifacts**: treat each page
(or each supplied page render) as one image under G1-G3. Do not invent
pixels. Do not stamp ready for human UAT (Bob only).

## When to use

- Brief or FR is a PDF, or the product under review ships PDF output.
- Operator supplies PDF page screenshots / exports.
- Print or multi-page layout must match a written brief.

## Inputs

- **Brief:** md/issue/paste, or text extracted from the same PDF (brief wins
  over decorative chrome).
- **Artifacts:** PDF page images (PNG/JPG/WebP). Prefer one file per page
  named `p01`, `p02`, ... If only a multi-page PDF is available, ask for
  page renders or render locally when tools exist — never invent pages.

## Procedure

1. Inventory pages vs brief sections (cover, TOC, screens, legal).
2. For each page image, run **design-uat** G1 -> G2 -> G3.
3. Extra PDF checks (tag gate `pdf` or fold into G2/G3):
   - Missing required page / wrong page order.
   - Crop marks, bleed, or margins that contradict the brief.
   - Body copy truncated by page box (G2 clip).
   - Headers/footers or page numbers not in brief (G3) or wrong (G1).
4. Report with `docs/templates/design-uat-report.md` plus page id in `where`.

## Do not

- OCR the whole PDF as a substitute for per-page G1 when images exist.
- Treat embedded fonts / Acrobat preflight as a pass without visual gates.
- Stamp ready for human UAT.