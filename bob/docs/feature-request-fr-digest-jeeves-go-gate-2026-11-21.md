# Feature request: Digest go-gate in offer path

**Repo:** SimonBarnett/bobiverse  
**ID:** BOB-G1  
**Date:** 2026-11-21  
**Theme:** FR digest go-gate: Plan digest on hold + Jeeves unhold-releases + CI fail open children  
**Depends-on:** SimonBarnett/bobiverse#8805, #8807  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop); label hold

## Objective

Deliver exactly one acceptance slice: **Digest go-gate in offer path**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Offer respects digest hold/unhold | Skip when depend has hold; fr-digest without hold satisfies while OPEN; pytest | pytest fixtures for depends-held and fr-digest OPEN without hold | Offered while digest held; or blocked after unhold on fr-digest |

LOCKED

## Shape

Primary: service

Hybrid note: anti-omnibus slice; skill/chair/CI behavior on existing product.

UNKNOWN

## Stack

Existing SimonBarnett/bobiverse stack (public GitHub, no new SaaS).

Why: smallest shippable FR.

Why-not: omnibus digest mega-issue.

LOCKED

## Architecture

`
parse Depends-on -> if hold skip depends-held -> else if fr-digest ok -> else OPEN skip
`

LOCKED

## Screens

No new screens.

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

## Gap

Batch park lacked a digest go-gate; children could be offered before human unhold; PRs could build while open children still Depends-on the parent. This slice is one row of the theme.

## Out of scope

Other backlog IDs in this theme. Editing parked VIS-D* / BOB-D*.

## LOCKED

- One acceptance row
- Digest label `fr-digest` + `hold`; unhold alone releases children; close optional
- Children `Depends-on: #digest`; intra-batch Depends-on among children; one digest per target repo
- CI fails when open issues still Depends-on the PR's FR
- Extends BOB-D3; needs BOB-D1 parse

## UNKNOWN

- Cache TTL for cross-repo issue state lookups (implementer picks short TTL)