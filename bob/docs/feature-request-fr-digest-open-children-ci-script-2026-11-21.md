# Feature request: Open-children gate script

**Repo:** SimonBarnett/bobiverse  
**ID:** CI-G1  
**Date:** 2026-11-21  
**Theme:** FR digest go-gate: Plan digest on hold + Jeeves unhold-releases + CI fail open children  
**Depends-on:** (none)  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop); label hold

## Objective

Deliver exactly one acceptance slice: **Open-children gate script**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Script fails when open children Depends-on #P | Given PR/FR #P, exit non-zero and list open Depends-on children | ``python``/``pwsh`` script + pytest under bob/ or .github/ | Silent pass while open child Depends-on #P |

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
PR closes #P -> search open issues Depends-on:#P -> fail with list
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
- Reusable for other SimonBarnett repos

## UNKNOWN

- Cache TTL for cross-repo issue state lookups (implementer picks short TTL)