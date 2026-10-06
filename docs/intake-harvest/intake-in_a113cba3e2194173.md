Session summary:
FR #2612: airc outbound queue + stop DONE flush for long Command stall after seq=1

Lessons:
- Long airc Command stall after seq=1 was service stop mid-emit; queue Query replies across reconnect, flush DONE on stop, busy-DONE on overlapping shell; avoid Restart-Service during ReplyFile Wait

---
_via-intake id=`in_a113cba3e2194173` ts=`2026-10-06T06:52:03Z`_
_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` book=`harvest` ver=`-`_
