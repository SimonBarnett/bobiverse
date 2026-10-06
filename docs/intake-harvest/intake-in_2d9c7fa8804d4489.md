Session summary:
FR #2696: submit-verify Enter-only retry after inject; PR #2700; first fresh-grok assign paste-after-Enter race

Lessons:
- After inject_console paste+double-Enter, probe grok turn_started/prompt.enqueue and retry Enter only (never re-paste) on miss; run verify async so IRC relay is not blocked (FR #2696 / PR #2700)

---
_via-intake id=`in_2d9c7fa8804d4489` ts=`2026-10-06T12:20:41Z`_
_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` book=`harvest` ver=`-`_
