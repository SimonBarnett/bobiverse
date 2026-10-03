<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/feature-request-pdf-illustrator-graphics-skills-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: PDF, Illustrator, and graphics design skills

**Repo:** `SimonBarnett/bob-design-uat`
**Date:** 2026-09-22
**Source:** Simon `#bobiverse` — harvest PDF / Illustrator / graphics skills; open an FR.

## Intent

Extend the design-uat product beyond UI screenshots so Bob visual UAT
also covers **print/PDF pages**, **Illustrator artboards**, and **loose
graphics packs** (SVG/PNG/icon sheets). Same G1-G3 bar; specialized
inputs and walk rules.

## Critique of current tree

| | |
|--|--|
| **Good** | `design-uat` G1-G3, fail-closed spelling, inventory, px/hex deltas. |
| **Bad** | PDF mentioned only as "pages as images"; no Illustrator or graphics skill homes. |
| **Ugly** | Agents will invent ad-hoc PDF/AI review steps and skip gates. |

## Ask (MUST)

1. Ship three companion skills under `.grok/skills/`:
   - `pdf-design` — multi-page PDF / print comps
   - `illustrator-design` — `.ai` artboards / AI exports
   - `graphics-design` — loose raster/SVG/icon packs
2. Each skill MUST defer visual gates to `design-uat` G1-G3 and MUST NOT
   stamp ready for human UAT.
3. `tools/Install-DesignUatSkill.ps1` installs all four skills into
   `~/.grok/skills`.
4. `tools/Validate-DesignUatSkill.ps1` (BT0) requires the three new
   `SKILL.md` files and key needles (`pdf-design`, `illustrator-design`,
   `graphics-design`, pointer to `design-uat`).
5. `design-uat` SKILL.md lists the companions under Inputs / Related.
6. Docs: this FR + short note in `docs/functional-spec.md` (Related skills).
   Golden fixtures for PDF/AI/graphics may follow as a later FR.

## Acceptance

| ID | Criterion |
|----|-----------|
| A1 | Three skill paths exist with YAML `name` matching folder. |
| A2 | Each description lists triggers; procedure calls design-uat G1-G3. |
| A3 | Install script copies all four skills. |
| A4 | Validator exits 0 and fails if any companion skill is missing. |
| A5 | `design-uat` cross-links the three companions. |
| A6 | No secrets; no UAT stamp language as worker authority. |

## Out of scope

- Figma API (U2).
- Native binary parsing of `.ai` without export.
- Replacing design-uat for product UI screenshots.

## Park only until dispatched

Open GitHub issue labeled `feature-request`. Do not stamp UAT.