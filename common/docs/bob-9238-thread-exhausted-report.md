# FR #9238: report webhook under thread exhaustion

## Problem
Walrus bobcallback filed `webhook failure: report` with `err: can't start new thread` after auth. `bobreport.digest_lock` starts a daemon heartbeat thread on every held lock; when the process cannot create more threads, `Thread.start()` raises and `handle_report_post` returned 500 + intake.

Related: FR #9236 listener self-exit when `ThreadingHTTPServer.process_request` cannot start a worker thread (FR #7618 fatal path).

## Fix
- Soft-skip digest-lock heartbeat on `RuntimeError` "can't start new thread"; keep the lock and serve the report.
- Map escaped thread-exhaustion `RuntimeError` in `handle_report_post` to **503** `thread_exhausted` (no failure intake storm).
- `_BobCallbackHTTPServer.process_request` closes the peer and logs instead of killing `serve_forever`.

## Non-goals
Do not raise OS thread caps. Tray untouched.
