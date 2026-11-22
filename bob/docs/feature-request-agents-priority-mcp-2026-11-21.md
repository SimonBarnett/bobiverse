# Feature request: Agents > Priority: configure mcp.ntsa.uk

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-53`  
**Phase:** `P4`  
**Date:** 2026-11-21  
**Theme:** Bob ear systray Agents/Workers/Weights + models webhook  
**Index:** `bob/docs/feature-request-systray-agents-workers-index-2026-11-21.md`  
**Depends-on:** BOB-50, PRI-03  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop)

## Objective

Deliver exactly one acceptance slice: **Agents > Priority: configure mcp.ntsa.uk**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Priority skills from mcp.ntsa.uk | MCP mcp.ntsa.uk configured | Config shows mcp.ntsa.uk — evidence in `docs/` + tray/log path | Wrong MCP |

LOCKED

## Shape

Primary: app

Hybrid note: anti-omnibus slice of theme `Bob ear systray Agents/Workers/Weights + models webhook`; reuse existing SimonBarnett/bobiverse product surface.

LOCKED

## Stack

Default: existing SimonBarnett/bobiverse stack (Windows fleet, public GitHub, bob intake). This slice does not invent SaaS hosts or secrets.

Why: smallest shippable FR for anti-omnibus park.

Why-not: omnibus tray mega-issue.

LOCKED

## Architecture

```
theme brief -> BOB-53 slice -> SimonBarnett/bobiverse change surface
depends: BOB-50, PRI-03
```

LOCKED

## Screens

HTML mocks (shared theme folder or local). Validator uses `--mocks-dir`.

| id | file | state |
|----|------|-------|
| M1 | home.html | primary |
| M2 | empty.html | empty |
| M3 | error.html | error |

## Gap vs current tree

See theme index. This issue owns only S1 above.

## Out of scope

Every other backlog ID. Implementation is after park when dispatched.

## LOCKED

- One acceptance row only
- Park-only until human dispatch
- Cross-link index + depends-on

## Dispatch evidence (FR #8695)

Human dispatch: owner comment UNHOLD on 2026-11-22 (pinned prerequisite BOB-50 closed). This seat is the dispatched implementer. No UAT stamp.

- `origin/main` at dispatch: `c30a23b6` (Merge pull request #8920). BOB-50 is on that tip: Agents > Priority calls `StartPriorityExe` (`vendor\priority\PriorityAgent.exe`). This slice keeps that start as the first submenu item and adds Configure MCP.
- PRI-03 is `SimonBarnett/priority-mcp#743` (still open). The owner unhold named BOB-50 only. S1 here is the tray registration of `https://mcp.ntsa.uk/mcp`, not the priority-mcp skills slice.
- S1 measurement: `bob-tray.exe --priority-mcp-configure` writes `name`, `url=https://mcp.ntsa.uk/mcp`, `state`, `doctor`. Live install hotpatch hash is not claimed in this PR.

## UNKNOWN

- Exact initial models matrix seed values (BOB-04) until CLI `--help` / Simon seed
- Favicon ToS for third-party sites when applicable
