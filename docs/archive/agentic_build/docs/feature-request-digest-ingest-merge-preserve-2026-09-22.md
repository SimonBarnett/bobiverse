<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-digest-ingest-merge-preserve-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: DIGEST ingest must merge-preserve rich peers

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**Related:** #142 ingest (merged PR #143), irc #36 `task` digest, #141 / #124 webhook  
**Raised by:** hostile MRB of #142 (issue #144)  
**UAT + hostile MRB owner:** Bob  

## Problem

`Import-BobIrcDigestJson` writes `bob-peers\<id>.json` from the keys on
**this** whisper. A thin presence `BOB DIGEST v1` (online / status /
`working_on` / workers, no `weekly` / `jobs` / `sha`) overwrites a rich
TRAY / status / full-digest peer with nulls and `jobs=[]`. Hover then
shows `no jobs` and loses weekly bars.

irc #36 / BT0l3 still use `machines[].task` (repo/sha/model/description/
run_time/state). This importer only reads `jobs[]`, so a `task`-only
whisper paints no job line.

#142 locked “do not drop fields we cannot map yet” as a UI rule and
scored a **full-shape** fixture. The clobber is a hole that PR made
visible. It is **not** a second ticket for the same #142 MUST.

## LOCKED

1. **Merge-preserve.** If the incoming machine omits `weekly`,
   `period_end`, `jobs` / `task`, `sha`, `repo`, `model`, `kind`,
   `cursor_label`, `cursor_period_end`, keep the existing peer values.
   Do not write `jobs=[]` over a jobs-rich peer because the chair is
   still presence-only.
2. **Do not replace** `_report-digest.json` with `{machines:{}}` when
   the whisper has nothing to merge for task / pcent / uptime.
3. **Map `machines[].task`** (irc #36 / BT0l3) into peer jobs and
   `_report-digest.json` `task`, not only `jobs[]`.
4. Test-Pack: full fixture still paints weekly + sha + Cursor bars;
   thin presence after a rich peer must not drop sha/jobs/weekly;
   `task`-only whisper paints sha + description. No live Ergo.
5. No `password=` / `XAI_API_KEY=` assignments in git.

## Gap vs current tree

| Current (post #142) | Wanted |
|---|---|
| Last whisper wins; missing keys become empty | Merge-preserve omitted tray fields |
| `jobs[]` only | Also `task` |
| `_report-digest.json` replaced even when empty | Keep prior task/pcent/uptime when incoming has none |

## Acceptance

1. Hermetic: rich peer + thin DIGEST → sha / weekly / jobs survive.
2. `task`-only DIGEST → hover job line has sha + description.
3. PR only; Bob stamps UAT.

## Non-goals

- Re-opening #142. Chair JSON growth (agentic_irc #81, already merged).
- #141 change-only POST. #124 shop JOIN.
