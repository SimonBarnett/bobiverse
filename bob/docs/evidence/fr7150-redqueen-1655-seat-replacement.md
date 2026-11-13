# FR #7150 --- redqueen 16:55 GMT 13 Nov 2026 seat replacement RCA

Acceptance (i) of #7117: identify the cause of seats `redqueen-916` / `redqueen-14100`
being replaced by `redqueen-11952` / `redqueen-8540` around 16:55 GMT. Jeeves had no
`!recycleseat` log for that swap. PR #7126 did not identify it.

## Verdict

**Cause: bob-worker `hang-restart-limit` (exit=5) after repeated FR #4123
`startup-no-first-turn` hang-recycles.**

Not Jeeves `!recycleseat`. Not `console-closed` for 916/14100. Not tray auto-restart
(FR #3180: tray logs `seat-exit` / `not restarted`). Dirty local recycle scripts were
present on the install but did not drive this swap.

## Timeline (UTC, redqueen)

| Time | Event |
|---|---|
| 15:53:12 | Prior seats 1964/8940: `shutting down (console-closed) exit=0` |
| 15:53:14 | Tray: `seat-exit` was=2 now=0 action=`not restarted` via `bob-tray-watchdog` |
| 15:53:49 | Seat 916 starts (agent.log seat marker; worker.log) |
| 15:54:08 | Seat 14100 starts |
| 16:08:52 / 16:09:10 | Both: startup ready cap 900s, `saw_turn_started=False` --- hang-recycle 1/3 |
| 16:24:01 / 16:24:17 | Hang-recycle 2/3 (`startup-no-first-turn`) |
| 16:28:01 | Seat 916 relay ACK for MRB #6935 (mid hang cycle; review later lost) |
| 16:39:21 / 16:39:33 | Hang-recycle 3/3 |
| 16:40:07 / 16:40:20 | Fourth agent start after 3/3 |
| 16:55:11 / 16:55:14 | Seat 916: cap again; `restart limit 3/1800s reached - giving up`; `shutting down (hang-restart-limit) exit=5` |
| 16:55:15 | Tray: `seat-exit` was=2 now=1 `not restarted` |
| 16:55:20 | Seat 14100: same `hang-restart-limit` exit=5 |
| 16:55:30 | Tray: `seat-exit` was=1 now=0 `not restarted` |
| 16:56:08 / 16:56:16 | New seats 11952 / 8540 start (manual Agent / startworker path; tray did not restart) |
| ~16:56 | `!resync`; queue accepted=0 |

## Evidence paths

* `%LOCALAPPDATA%\Bobiverse\worker\run\worker-redqueen-916-7a0b2545\worker.log`
* `%LOCALAPPDATA%\Bobiverse\worker\run\worker-redqueen-14100-bb6e1698\worker.log`
* `%LOCALAPPDATA%\Bobiverse\worker\logs\bob-worker-agent.log` (seat markers)
* `%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log` (`seat-exit` / `not restarted`)
* `C:\ai\bob\logs\stdout.log` --- no `recycleseat` for 916/14100; later
  `state_unavailable` only for other nicks; assigns to 11952/8540 after resync

## Why Jeeves saw nothing

Hang-restart-limit previously only wrote `worker.log`. Ear stdout and Jeeves recycle
logs never saw a reason. FR #7150 adds a shop PRIVMSG
`hang-restart-limit reason=... restarts=N/Ws exit=5` and a
`run_dir/hang-restart-limit.txt` marker so the next exit=5 is visible without digging
run folders.

## Related

* FR #4123 --- startup ready-cap hang-recycle when first `turn_ended` never arrives
* FR #3180 --- tray observes seat-exit, does not auto-restart seats
* FR #7123 / PR #7126 --- hang-recycle must GIVEUP an ACKed job (not silent drop);
  QuickEdit off (separate from this trigger)
* #7117 (a)-(h) --- recycleseat / SYSTEM / dirty scripts / QuickEdit / watchdog
  (covered by PR #7126); this doc covers (i) only

## Follow-up

Repeated `startup-no-first-turn` on redqueen grok seats (916, 14100, and then 11952)
points at agents that never start a turn. QuickEdit freeze is one suspect (Si: need
Enter to continue); PR #7126 clears QuickEdit on new seats. If ready-cap hangs
continue after that build is live, file a separate FR for grok first-turn readiness.
