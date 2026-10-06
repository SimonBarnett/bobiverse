Session summary:
FR #2601: seat 15152 died irc-lost exit=3; TipForm HealWorkerSeats + Ensure-BobWorkerSeats; PR #2602; live seats restored 1->2

Lessons:
- bob-worker irc-lost exit=3 is clean (no crash hook); TipForm Watchdog must top agent seats back to hard cap 2 (BOBIVERSE_WORKER_SEAT_HEAL=0 to opt out).

---
_via-intake id=`in_100c98c8f1144db5` ts=`2026-10-06T03:07:26Z`_
_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` book=`harvest` ver=`-`_
