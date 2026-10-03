<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/feature-request-three-gates-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: three design-UAT gates

**Date:** 2026-09-22
**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/2
**Raised by:** ce-priority-dev1-11904 on #agentic_irc (Simon: anyone FRs after create)

## Problem

The skill lists checks in parallel. Bob needs a fixed order so a pretty layout
cannot hide a misspelled CTA, and a clean OCR pass cannot hide invented chrome.

## LOCKED

Three gates, in this order. Any FAIL stops the pass.

1. **G1 OCR / spelling** — read every visible word (or OCR the screenshot). Brand,
   CTA, errors, empty states. Do not approve text you did not read.
2. **G2 Layout-delta vs brief** — measure spacing, alignment, type, radius against
   the brief or design source. Record the pixel/delta. "Close enough" is FAIL.
3. **G3 Invented chrome = hallucination** — any control, nav, testimonial, price,
   or claim not in the brief is FAIL, even if the pixels are perfect.

## Done when

Skill + report template name G1→G2→G3 with a scorecard. Bob's DESIGN-UAT issue
body includes a Gate 1 / Gate 2 / Gate 3 score.

## Non-goals

- Golden fixture PNGs (issue #3).
- Shipping an OCR binary (v1 is Bob/agent eyes + optional local OCR).
- Auto-fixing pixels in CI.
