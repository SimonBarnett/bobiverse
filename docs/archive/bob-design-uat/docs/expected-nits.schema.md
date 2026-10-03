<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/expected-nits.schema.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# expected-nits.yaml schema (P0b / P1 / P2)

Golden (#3) and adversarial (#5) packs use this shape. Canonical path: `docs/expected-nits.schema.md` (L10). Fixture files: `fixtures/<pack>/<id>/expected-nits.yaml`.

## G1 fail-closed (#6)

Any G1 misspelling vs the brief or glossary must use `severity: blocker`. G1 typos are never cosmetic nits.

## G2 deltas (#8)

Every G2 nit row must include at least one of `delta_px` or `delta_hex`.

## G3 inventory (#7)

Each fixture file must include an `inventory[]` list. Each entry has `item`, `kind` (`chrome` | `copy` | `image` | `flow`), and `in_brief`: `yes` or `NOT_IN_BRIEF`.

## Example

```yaml
fixture_id: T-G01
clean_control: false
nits:
  - gate: G1
    where: hero / primary button
    brief_field: primary_cta
    expected: "Book a table"
    actual: "Bok a table"
    severity: blocker
  - gate: G2
    where: primary button
    expected: "16px / #111111"
    actual: "14px / #222222"
    severity: major
    delta_px: 2
    delta_hex: "#111111->#222222"
inventory:
  - item: Book a table
    kind: copy
    in_brief: yes
  - item: Donate now
    kind: chrome
    in_brief: NOT_IN_BRIEF
```

## Rules

- One file per fixture directory: `fixtures/<pack>/<id>/expected-nits.yaml` (nits list; empty nits only for the clean control).
- `clean_control: true` requires zero nits and may use an empty `inventory: []`.
- `gate` must match the skill tags G1/G2/G3/brief.
- `brief_field` names the brief heading or token the nit cites.
- Do not commit secrets or live customer screenshots with PII.
