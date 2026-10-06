Session summary:
FR #2669: tray wrapper doubled BOB_*_HOME backslashes + CURSOR_/SAND_ inherit; fixed Start-BobFleetTray + bob-worker prepare_seat_child_env; PR #2680

Lessons:
- Start-BobFleetTray seat wrappers must single-quote BOB_* paths (PS does not escape \); bob-worker prepare_seat_child_env normalises doubled homes and scrubs CURSOR_*/SAND_* for tray==CLI env parity

---
_via-intake id=`in_2de39531aba44a6c` ts=`2026-10-06T11:19:52Z`_
_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` book=`harvest` ver=`-`_
