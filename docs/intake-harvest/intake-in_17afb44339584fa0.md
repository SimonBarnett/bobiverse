Session summary:
FR #2697: moved tray.alive off WinForms UI thread (C# Threading.Timer + PS System.Timers.Timer); TRAY_ALIVE_MAX_AGE_S 15->30; PR #2702

Lessons:
- FR #2697: tray.alive must use System.Threading.Timer (bob-tray.exe) or System.Timers.Timer SynchronizingObject=$null (Watch-BobTray); never a WinForms Timer sharing the UI thread with the 30s poll — stalls of 7-11s false-NACK !startworker against a 15s ear max age

---
_via-intake id=`in_17afb44339584fa0` ts=`2026-10-06T12:21:52Z`_
_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` book=`harvest` ver=`-`_
