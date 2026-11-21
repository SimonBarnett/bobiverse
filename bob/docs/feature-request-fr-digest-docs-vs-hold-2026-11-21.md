# Feature request: Docs: digest vs hold vs Depends-on

**Repo:** SimonBarnett/bobiverse  
**ID:** BOB-G2  
**Date:** 2026-11-21  
**Theme:** FR digest go-gate: Plan digest on hold + Jeeves unhold-releases + CI fail open children  
**Depends-on:** (none)  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop); label hold

## Objective

Deliver exactly one acceptance slice: **Docs: digest vs hold vs Depends-on**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Chair/docs explain three gates | Short note: digest go-gate, hold, Depends-on CLOSED | docs/ path under bob/ or jeeves/ cites VIS-G3 + BOB-G1 encoding | No docs distinguishing the three |

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
hold label | fr-digest Depends-on | parent CLOSED Depends-on
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
- Points at VIS-G3 + BOB-G1

## UNKNOWN

- Cache TTL for cross-repo issue state lookups (implementer picks short TTL)