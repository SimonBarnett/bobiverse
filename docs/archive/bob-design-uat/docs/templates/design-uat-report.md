<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/templates/design-uat-report.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Design UAT report

**Job / PR:**  
**Brief:** (link or path)  
**Artifacts reviewed:** (file names + dimensions if known)  
**Reviewer agent:**  
**SHA or build id:**  

## Gate scorecard (issue #2)

Run **G1 → G2 → G3**. A FAIL stops the pass.

| Gate | Result | Evidence (1 line) |
|------|--------|-------------------|
| G1 OCR / spelling | PASS / FAIL | |
| G2 Layout-delta vs brief | PASS / FAIL | |
| G3 Invented chrome | PASS / FAIL | |

## Inventory

| # | Artifact | Brief section | Notes |
|---|----------|---------------|-------|
| 1 | | | |

## Nit list (G1 | G2 | G3 | brief)

| gate | where | expected | actual | severity | delta_px | delta_hex |
|------|-------|----------|--------|----------|----------|-----------|
| | | | | | | |

### G1 — Spelling-in-image

(Summary or extra rows if needed. Any G1 typo is a **blocker** / FAIL.)

### G2 — Layout-delta / pixel-perfect

(Summary or extra rows if needed. Every G2 row must include `delta_px` and/or `delta_hex`.)

### G3 — Hallucination / invented chrome

(Summary or extra rows if needed.)

### G3 inventory (required)

| item | kind | in_brief |
|------|------|----------|
| | chrome / copy / image / flow | yes / NOT_IN_BRIEF |

## Brief fidelity

| Requirement | Status | Evidence |
|-------------|--------|----------|
| | pass / fail / nit | |

## Verdict (evidence only)

Choose one:

- **FAIL** — blockers listed above; not ready for MRB PASS-nits on product PR.
- **PASS-nits candidate** — no blockers; cosmetic nits only; product PR may proceed to hostile MRB.
- **candidate PASS-UAT, Bob stamp required** — all gates green; **Bob** must still stamp ready for human UAT.

**Blockers:**  
**Nits:**  
**Evidence commands run:** (e.g. BT0 validator, manual BT1)
