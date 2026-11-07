# FR-OC-TURN: OpenCode turn_ended into BoredEmitter

## Goal

OpenCode seats get the same harvest-hold release / done-miss / startup-ready behaviour class as Grok/Cursor, without relying only on `harvest_hold_s` timers.

## Deliverables

- Define paired durable signals for `kind=opencode`: turn_started (when a run begins) and turn_ended (wrapper marker or `opencode run` exit).
- Wire both into BoredEmitter / Supervisor so harvest hold extends while a run is active after DONE (do not `!bored` into a still-running child when hold expires).
- Startup ready: do not hang-recycle OpenCode seats waiting for Grok `events.jsonl` turn_ended.
- Tests for bored release, done-miss arming, startup ready, and a run that outlasts harvest_hold_s after DONE.

## Testable

1. After a completed run with ACK open and no DONE, done-miss path can arm (or documented equivalent).
2. After DONE + run exit, `!bored` can fire without waiting full harvest_hold_s when turn-end signal present.
3. Startup with opencode does not recycle solely for missing Grok events.jsonl.
4. After DONE while a run is still active (hold expired), seat does not request another job until turn_ended.
