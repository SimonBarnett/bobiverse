<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-irc-coordinator-listener-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: IRC coordinator listener (so you get responses)

**Repo:** https://github.com/SimonBarnett/agentic_irc
**Date:** 2026-09-21
**Related:** harvest `a8c2daa`; #54 ACK; #56 grok-talk hook

## Problem

Coordinator sessions wrote `outbox.txt` and grepped `irc.log` later. That is
send-only. The skill must include running a listener, so that you get
responses. LAN SMB (`\\192.168.1.200\nas\bot.txt`) cannot reach ionos.

## Gap vs current tree

`origin/main` `a8c2daa` already harvested:

- `.grok/skills/agentic-irc/SKILL.md` section **Listener (required)**
- `.grok/skills/bob-irc/SKILL.md` pointer
- `scripts/irc_listen.py` (drop POINT/PING/DIGEST/AGPK; print `FROM nick target text`)
- `irc_listen.py` in `install_skill.SCRIPTS`
- `tests/test_irc_listen.py`

This FR parks that as a tracked feature-request (issue + `/docs`) so Bob
chairs it. Worker: confirm the MUST is in the repo; fill holes; do not
drop the listener requirement.

## LOCKED

1. Skill text keeps: the skill must include running a listener, so that you get responses.
2. `irc_listen.py` stays in `install_skill.SCRIPTS`. Do not remove existing SCRIPTS names.
3. Coordinator uses its own `--home` (flamingo: `~/.agentic-irc-cursor`). Watch home stays `~/.agentic-irc-bobiverse`.
4. `AGENTIC_IRC_DEBUG=1` so `$home/irc.log` exists. Watch stays no grok.exe.
5. No LAN SMB to talk to ionos. No secret assignments in git.

## Acceptance

1. `agentic-irc` SKILL.md has **Listener (required)** and names `irc_listen.py`.
2. `install_skill.SCRIPTS` includes `irc_listen.py`; pytest covers filter + list.
3. Offline only. No live Ergo in the pack.

Owner: Bob (UAT + hostile MRB).
