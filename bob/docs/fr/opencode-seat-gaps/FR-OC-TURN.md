# FR-OC-TURN: OpenCode turn_ended into BoredEmitter

## Goal

OpenCode seats get the same harvest-hold release / done-miss / startup-ready behaviour class as Grok/Cursor, without relying only on `harvest_hold_s` timers.

## Deliverables

- Define a durable turn-end signal (wrapper marker line or treat each `opencode run` exit as turn_ended).
- Wire into BoredEmitter / Supervisor for `kind=opencode`.
- Startup ready: do not hang-recycle OpenCode seats waiting for Grok `events.jsonl` turn_ended.
- Tests for bored release, done-miss arming, startup ready on opencode.

## Testable

1. After a completed run with ACK open and no DONE, done-miss path can arm (or documented equivalent).
2. After DONE + run exit, `!bored` can fire without waiting full harvest_hold_s when turn-end signal present.
3. Startup with opencode does not recycle solely for missing Grok events.jsonl.
