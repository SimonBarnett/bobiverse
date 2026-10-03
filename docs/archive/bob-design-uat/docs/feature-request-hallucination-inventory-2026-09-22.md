<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/feature-request-hallucination-inventory-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: hallucination inventory vs original brief

Date: 2026-09-22
Issue: https://github.com/SimonBarnett/bob-design-uat/issues/7
Repo: https://github.com/SimonBarnett/bob-design-uat

## Ask

List UI chrome, copy, imagery, and flows that appear in the screenshot but are not in the original brief (invented buttons, fake stats, extra pages).

## Gap vs tree (after P0 / #1)

| Area | Now | Residual |
|------|-----|----------|
| G3 + `NOT_IN_BRIEF` | In skill + report template | None at procedure level |
| Proof | No fixture | #3 T-G03 |

Do not rewrite G3. Remaining: fixture proof; brief format (U2/U4) if Simon locks it.

## Locked

- Invented chrome/copy/imagery = G3 hallucination.
- Full per-artifact inventory with `in_brief` / `NOT_IN_BRIEF` (T-S07).
- No UAT stamp. No secrets.

## Traceability (#7 → acceptance)

| FR MUST | Spec | Acceptance |
|---------|------|------------|
| G3 inventory table in reports | L5 | A2 |
| `inventory[]` in fixture YAML | L10 | A7 |
| BT0 T-S07 needles | L9 | A3 |

## Unknown

- Brief format (md / pdf / png mock).
