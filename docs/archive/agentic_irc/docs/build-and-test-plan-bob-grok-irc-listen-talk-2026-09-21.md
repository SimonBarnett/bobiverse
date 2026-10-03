<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-bob-grok-irc-listen-talk-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build-and-test plan: Grok-talk on IRC

**FR:** `docs/feature-request-bob-grok-irc-listen-talk-2026-09-21.md`

## Goals

Optional LLM replies on `#bobiverse` (and Query) when a fleet `bob-*` nick is
addressed, without putting grok.exe inside `Watch-Bobiverse` or the #54 ACK
fast path.

## Non-goals

Live Ergo in CI. Burning Grok Bot weekly when build fuel exists. Implementing
the full BobBridge worker in this repo (sister `agentic_build`).

## Phase order

1. **Contract** — `docs/grok-talk-envelope-v1.md` (or section in FR): JSON
   line enqueued from `irc_agent`, JSON completion written back to
   `grok-outbox.jsonl` → drained to `outbox.txt` as PRIVMSG lines.
2. **irc_agent** — After successful ACK (or instead of ACK when grok-talk
   enabled and fuel gate passes), append enqueue record; dedupe by
   `(asker, hash(body))` within cooldown.
3. **Drain helper** — `scripts/grok_talk_drain.py` or BobBridge hook (sister
   PR) reads completions and calls existing outbox append (no new IRC socket).
4. **Pytest** — Fake enqueue + fake completion; assert PRIVMSG recorder lines.
5. **Skills** — `bob-irc` / `agentic-irc`: recycle Watch after merge; env
   flag; “ACK always; grok-talk when enabled and fuel OK”.
6. **PR** from `work/grok-irc-listen-talk`. Do not stamp UAT.

## Locked constants

- Fleet nicks: `bob-flamingo`, `bob-marchhare`, `bob-ionos`, `bob-dev1`
- Channel `#bobiverse`, moot `b0b1be15e0000001`
- `MENTION_COOLDOWN_S = 20` (shared with #54)
- Line cap 350 chars

## Tests

```bash
python -m pytest tests/test_bobtalk.py tests/test_agent.py tests/test_grok_talk.py -q
```

## Sister (agentic_build)

Park matching FR: enqueue from `~\.agentic-irc-bobiverse\grok-inbox.jsonl`,
fuel via `Get-BobWeeklyRemaining` / tray, reply via outbox append. Ionos
recycle: pull `agentic_irc`, `install_skill.py`, restart Watch-Bobiverse.
