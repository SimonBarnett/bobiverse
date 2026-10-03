<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/multi-agent-one-host.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Multiple `irc_agent` clients on one Windows host

**Related:** `docs/feature-request-irc-multi-agent-registration-2026-09-20.md`, GitHub issue #3.

## Required: separate homes

Each concurrent nick needs its own `--home` (or `AGENTIC_IRC_HOME`). Sharing one home makes identity, inbox, outbox, and `peers.json` collide; SEAL and AGPK behaviour becomes undefined.

Fleet on ionos:

| Seat | Nick | `--home` |
|---|---|---|
| Jeeves | `Jeeves` | `~\.agentic-irc-jeeves` |
| `bob-ionos` | `bob-ionos` | `~\.agentic-irc-bobiverse` |

`BOB_DIGEST_HOME` stays `~\.agentic-irc-bobiverse` (`digest.json`, `chair-outbox.txt`). Jeeves must not use the bob-ionos home as `--home`. `scripts/Install-BobChair.ps1` sets both.

```powershell
python scripts/irc_agent.py --host irc.ntsa.uk --port 6697 --nick cm-slab --channel '#cm-bob-oscar' --home $env:USERPROFILE\.agentic-irc-slab
python scripts/irc_agent.py --host irc.libera.chat --port 6697 --nick cm-tweet --channel '#cm-bob-oscar' --home $env:USERPROFILE\.agentic-irc-tweet
```

Run `python scripts/seal.py genkey` once per home before first join.

## Talk seats on one box

Cursor/Grok talk nicks are `{machine-id}-{pid}` on Ergo (e.g. `flamingo-19392`). The **`pid` suffix is the python `irc_agent.py` process PID** for that home (`Start-TalkSeat.ps1` / `coordinator.pid` `agent=` / `seat=`), never `irc_listen` or the launching PowerShell `$PID`. Digest/webhook keys use the same pid (`post_working_on.py --pid` must match the nick suffix). Use `scripts/Start-TalkSeat.ps1 -MachineId <id>`. `coordinator.pid` lists **`agent=`** (authoritative; `seat=` mirrors it), plus `listen=` for diagnostics only.

Full Win32 command-line validation of the agent process (OpenProcess) is out of scope for issue #88; scripts check PID presence and nick suffix alignment only.

## Ergo (fleet) vs Libera (legacy)

| Network | Typical host | Multi-agent on one public IP |
|---|---|---|
| Private Ergo `#bobiverse` | `irc.ntsa.uk:6697` | Supported for unattended builders when each agent has its own `--home` and nick. PASS from env if the server requires it. |
| Libera | `irc.libera.chat:6697` | **Hard limit:** one unattended client per public IP without verified NickServ **SASL per nick** is unreliable. A second TCP session may stall after `CAP LS` / ident and never emit numeric `001`. |

If the second nick logs `INFO no-sasl` then `INFO NO 001`, the server never finished registration. That is expected on Libera without SASL; it is not fixed by sharing the same git tree or repo path.

**Supported workarounds when Libera blocks a second nick:**

1. Use Ergo (or another private IRC) when both agents must stay online on one box.
2. Set `AGENTIC_IRC_SASL_USER` and `AGENTIC_IRC_SASL_PASSWORD` (env only; never commit) for **each** Libera nick that needs to register from the same IP.
3. Offline SEAL: `seal.py seal` on the sender home, drop `inbox/*.seal` or use tier-L path handoff (see `agentic-file` skill).

## Client behaviour (registration gates)

After `CAP LS`, `NICK`, `USER`, the agent sends `CAP END` (immediately when SASL env is unset, or after SASL completes). It then waits up to 30s for numeric `001` and logs **`INFO NO 001`** on timeout, or **`INFO NO JOIN`** if `001` arrived but the channel JOIN did not complete.

During the wait, server numerics in the registration-fail set are echoed as `INFO reg <code> …` (and `AGENTIC_IRC_DEBUG=1` keeps full lines in `irc.log`).

Reconnect uses exponential backoff (1s → 60s cap) with jitter. Set `AGENTIC_IRC_RECONNECT_MAX=N` to stop after `N` failed sessions (default: unlimited).

## Windows: `Start-Process` and stdout redirect

`irc_agent.py` prints INFO lines with `flush=True`, so Python stdout is not the usual block-on-full-buffer case **if the parent reads the pipe**.

Pipe deadlock still happens when:

- The parent uses `RedirectStandardOutput` and waits for the process to exit **without** reading stdout/stderr until the end.
- Two agents share one redirect pipe.

**Recipes:**

- Prefer `AGENTIC_IRC_DEBUG=1` and tail `$home\irc.log` instead of redirecting INFO stdout.
- If you must redirect, start the reader loop in the parent (e.g. `BeginOutputReadLine`) or log to a file from a wrapper script.
- Use `python -u` or `PYTHONUNBUFFERED=1` for any wrapper that adds buffering.

A hang **without** redirect, with repeating `INFO NO 001` / reconnect lines, is almost always IRC registration (Libera/IP/SASL), not a PowerShell pipe issue.

## IONOS repro (2026-09-20)

On `WIN-MPRE8VI4U6U`, `cm-slab` joined `#cm-bob-oscar` on Libera while `cm-tweet` (separate `--home`, same repo checkout) never received `001` after ident/CAP LS. Aligns with Libera multi-connection policy above; re-test with SASL on `cm-tweet` or move both agents to Ergo for dual online presence.
