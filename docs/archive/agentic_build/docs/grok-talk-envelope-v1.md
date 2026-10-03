<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/grok-talk-envelope-v1.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Grok-talk wire envelope v1

Canonical copy: SimonBarnett/agentic_irc `docs/grok-talk-envelope-v1.md` (hook #56).

IRC `irc_agent` enqueues listen-talk jobs; this repo's `Invoke-BobGrokTalkTick` /
`Watch-GrokTalk.ps1` consumes `grok-inbox.jsonl` and appends completions to
`grok-outbox.jsonl`. agentic_irc `scripts/grok_talk_drain.py` turns completions
into `outbox.txt` lines for the existing outbox poller.

Paths are under `AGENTIC_IRC_HOME` (fleet default `~\.agentic-irc-bobiverse`).

See agentic_irc for full field tables and examples.
