# Feature request: Skip offer when any depend OPEN

**Repo:** SimonBarnett/bobiverse  
**ID:** BOB-D3  
**Date:** 2026-11-21  
**Theme:** Depends-on preconditions: Plan stamps + Jeeves skip-until-closed  
**Depends-on:** (none)  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop)

## Objective

Deliver exactly one acceptance slice: **Skip offer when any depend OPEN**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | FR not offered while depend OPEN | Offer path returns depends-open reason | pytest fixture offer skip | Offered while depend open |

LOCKED

## Shape

Primary: service

Hybrid note: anti-omnibus slice; skill/chair behavior on existing product.

UNKNOWN

## Stack

Existing SimonBarnett/bobiverse stack (public GitHub, no new SaaS).

Why: smallest shippable FR.

Why-not: omnibus Depends-on mega-issue.

LOCKED

## Architecture

`
Plan park stamps Depends-on -> GitHub issue body
Jeeves parse_depends_on -> skip offer while OPEN
`

LOCKED

## Screens

No new screens.

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

## Gap

Depends-on backlog ids alone are not enforceable; hold is manual. This slice is one row of the theme.

## Out of scope

Other backlog IDs in this theme.

## LOCKED

- One acceptance row
- Grammar: `Depends-on: #N` same-repo; `owner/repo#N` cross-repo; `(none)` when empty
- Distinct from hold / HOLD: stamps

## UNKNOWN

- Cache TTL for cross-repo issue state lookups (implementer picks short TTL)
