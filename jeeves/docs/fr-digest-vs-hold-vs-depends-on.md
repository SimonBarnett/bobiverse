# Digest go-gate vs hold vs Depends-on CLOSED

**BOB-G2 / FR #8838.** Chair short note for the FR digest go-gate theme.
Cites Plan playbook **VIS-G3** (skills-visionary digest go-gate skill) and product
encoding **BOB-G1** (`bob_g1_skip_held_digest` in `common/scripts/gitclaim.py`).

Three different gates. Do not collapse them.

## 1. Digests go-gate (`fr-digest` + `hold`)

| | |
|---|---|
| What | One **digest** issue per target repo parks a batch. Labels: `fr-digest` and `hold`. Children stamp `Depends-on: #digest` (plus any intra-batch Depends-on). |
| Release | **Unhold alone** (remove `hold`). Digest may stay OPEN. Close is optional. |
| Offer path | BOB-G1: depend with `hold` -> skip reason `depends-held` (`bob_g1_skip_held_digest`). Unheld `fr-digest` -> `ok-fr-digest` while still OPEN (does not trip depends-open). |
| Plan | VIS-G3: visionary skill parks the digest with those labels; children are not assignable until unhold. |
| Monitor | `fr_digest` (FR #8849): EXIT 1 when an offered/accepted child still Depends-on a local `fr-digest`+`hold` row. |

## 2. Hold (issues-only)

| | |
|---|---|
| What | Label `hold` / `on-hold` on an **issue/FR** (never on a PR — FR #9082). Also `HOLD:` body stamps. |
| Effect | Blocks **that** FR from offer (FR #4009 `row_fr_hold_reason`). Does not by itself mean "digest go-gate". |
| Distinct | A lone `hold` without `fr-digest` is not the digest check. Ops watchers that only look for `hold` are not VIS-G3 / BOB-G1. |

## 3. Depends-on CLOSED (ordinary backlog)

| | |
|---|---|
| What | Issue body `Depends-on: #N` (or `owner/repo#N`). Ordinary parent FRs must be **CLOSED** before the child is offerable. |
| Effect | BOB-D3 / FR #8754 / FR #8807: open depend -> skip (`depends-open` / `bob_d3_skip_open`). |
| Exception | Unheld `fr-digest` parents are allowed OPEN (BOB-G1 `ok-fr-digest`). Held digests use gate 1 (`depends-held`), not this CLOSED rule. |
| Monitor | `depends_on` (FR #8848): EXIT 1 when an offered/accepted row still Depends-on an OPEN local queue row (chair missed BOB-D3). |

## Quick map

```
hold label alone          -> block that FR (issues-only)
fr-digest + hold          -> block children until unhold (digest go-gate; close optional)
Depends-on ordinary OPEN  -> block until parent CLOSED
Depends-on unheld fr-digest OPEN -> offer OK (BOB-G1)
```

Architecture (theme LOCKED): `hold label | fr-digest Depends-on | parent CLOSED Depends-on`.

## Related

- Index: `bob/docs/fr-index-fr-digest-go-gate-2026-11-21.md` (docs branch park)
- BOB-G1 offer path: FR #8837 / `bob_g1_skip_held_digest`
- VIS-G3 Plan skill: SimonBarnett/skills-visionary VIS-G3
- BOB-G3 Digest flag recognition: FR #9108 (separate)
- Product Depends-on vs hold docs theme (BOB-D8 #8812) is the D* track; this note is the G* digest go-gate track
