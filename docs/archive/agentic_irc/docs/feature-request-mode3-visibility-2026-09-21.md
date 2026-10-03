<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-mode3-visibility-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Mode 3 operator visibility (task line + progress + icon)

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/4  
**Raised by:** Simon  
**UAT + hostile MRB owner:** TBD at dispatch (not Bob stamp on issue #5 SHA)  
**Build orchestrator:** Bob  

## Problem

Mode 3 thin/DUMB work is hard to follow on the operator desktop: jobs are opaque until DONE/FAIL. Operators want a human-readable task description, in-console progress (`\|/|` spinner), green **DONE** / red **FAIL** with local error text, and a desktop icon for the thin client.

## Ask

1. English one-line description of the active DUMB job (from job metadata or chair-provided label).
2. Spinner animation while the job runs (`\|/|` cycle).
3. Terminal colours: green `DONE`, red `FAIL` plus `{error on this machine}`.
4. Application icon for `airc-moot-thin.exe` (and consistent shortcut branding).

## Acceptance

1. Parked FR (this file) + build-and-test plan before implementation lands on `main`.
2. Behaviour demonstrated on Win8+ thin smoke (not CI IRC).
3. No secrets in UI strings; jail errors may show operator-safe text only.
4. Hostile MRB on issue #4 before any ready-for-human-UAT stamp for visibility.

## MUST NOT

- Ship spinner/icon on silent assumption (issue #5 blocker).
- Log live PIN, PSK, or `password=` / `XAI_API_KEY=` values.

## Non-goals

- Replacing `#bobiverse` MOOT transcript.
- macOS/Linux thin clients.

## Status

**Intake only** — addresses MRB issue #5 required fix #4. No code in this intake commit.
