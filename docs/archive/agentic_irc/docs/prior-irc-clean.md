<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/prior-irc-clean.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Prior cleanup before an ear connects

Deterministic. No LLM. The same rules run every time a `bob-*` builder, talk seat, or worker `irc_agent` is about to connect.

Hung `irc_listen.py` processes plus a stale `irc_agent` that still holds the nick make the next client register a suffixed nick (`bob-flamingo_1` on the server, or the client `433` rename `bob-flamingo_l`). Killing one `irc_agent` and starting another leaves that ghost. `Start-Process -WindowStyle Hidden` under spawn load has also failed python with `0xc0000142`.

## Rules

Nick `N`, home `H`. Never kill the current process or a `--keep-pid`. Never print command lines (a `--password` argument must not hit the log).

**`irc_agent.py`** whose command line names that script, and any of:

1. `--nick` equals `N` (exact, case-insensitive; `bob-flamingo` does not match `bob-flamingo2`)
2. `--home` is the same path as `H` (normalized; a worker home under `H` is not `H`)
3. `N` is a `bob-*` builder and `--nick` is exactly `bob` (bare ionos ghost)

**`irc_listen.py`** whose command line names that script, and any of:

1. `--home` is `H`
2. `N` is a `bob-*` builder and `--home`'s last component is exactly `.agentic-irc-cursor` (not `.agentic-irc-cursor-2`)

`irc_listen` only tails `irc.log`. Workers do not start it. The cursor-home sweep clears the hung default-seat pile seen next to a builder. It does not touch other seats. A live legacy listen on `.agentic-irc-cursor` is replaced later by `Start-TalkSeat.ps1` / `Start-IrcTsr.ps1` (one process). Preferred wake remains Watch-AgentHealth, which does not use `irc_listen`.

One home is one `irc_agent`. A different nick on `H` (for example Jeeves sharing the builder home) is killed. Give the chair its own `--home`.

After a kill, wait `AGENTIC_IRC_PRIOR_WAIT_S` (default 3, clamped to 2–5) so Ergo can drop the TCP session, scan once more, then stop. No wait when nothing matched. Two passes maximum.

## Where it runs

- `irc_agent.py` calls it once before the first connect (not on reconnect). For a `bob-*` builder it also sweeps `irc_listen`. A talk seat or worker does not, because `Start-TalkSeat.ps1` kills listens and then starts exactly one. `--once` and `AGENTIC_IRC_SKIP_PRIOR_CLEAN=1` skip.
- `Start-TalkSeat.ps1` and `scripts/Start-BobEar.ps1` call it, then start **one** python via `ProcessStartInfo` `CreateNoWindow` / `UseShellExecute false`.
- `start_worker_irc_agent.py` calls it before spawn (not on `--dry-run`).

`scripts/Start-BobEar.ps1` is the callable for `agentic_build` `tools/Watch-Bobiverse.ps1` and `tools/Install-BobIrc.ps1`. Those files live in the sister repo. Until they call this script, `irc_agent.py` still runs the same cleanup before the first connect once the process has started. Watch rule when it is wired up: if more than one process has `--nick N`, call `Start-BobEar.ps1` with no `--keep-pid` so it kills them and starts one; if exactly one live `N` is up, do not call it on every poll. Do not use `Start-Process -WindowStyle Hidden`.

## Verify

Kills nothing. Prints `pid` and `kind` only:

```bash
python scripts/prior_irc.py --nick bob-flamingo --home ~/.agentic-irc-bobiverse --dry-run
```

`INFO prior-clean dry-run count=0` means no matching prior. Pytest: `python -m pytest tests/test_prior_irc.py -q`.
