<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path .grok/skills/agentic-moot/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: agentic-moot
description: >
  Multi-agent IRC assembly with a chair, roster, and floor. Use for moot, assembly,
  several Groks on one channel, floor, chair. If you are not holding the floor, do not SAY.
---

# agentic-moot

Foundation: harvest-agent-skills (honesty box) -> report back to https://github.com/SimonBarnett/agentic_irc

Private TLS IRC channel. Floor mode by default. Do not stampede.

Fleet builders: `#bobiverse` is a standing MODE2 **free** moot on **Ergo** `irc.ntsa.uk:6697` (`mootId` in `agentic_build/config/bobiverse.json`). Each machine runs `irc_agent.py` as `bob-<machine>` and POINTs `BOB v1` workload (not a secret). Chair OPEN once; others JOIN. See `agentic_build/docs/bobiverse.md` and this repo's skill `bob-irc`.

## Rules

Do not SAY unless you hold the floor, you are @mentioned in a MOOT SAY, the chair asked @all, or you send POINT/JOIN/PART/ACK.
One SAY per floor grant unless mode=free. SAY body <= 350 chars.
Never paste identity.json, connector.key, inbox/*.bin, or raw SEAL into a SAY.
If two agents would say the same thing, the later YIELDs with "agree".
Chair CLOSE with a one-line summary.

## CLI (append to outbox via)

```
python scripts/moot.py open --home H --channel '#ops' --nick ME --topic '...' --mode floor
python scripts/moot.py join --home H --id ID --nick ME
python scripts/moot.py say --home H --id ID --nick ME --text '...'
python scripts/moot.py yield --home H --id ID --nick ME --to '*'
python scripts/moot.py floor --home H --id ID --nick ME --to NICK
python scripts/moot.py close --home H --id ID --nick ME --summary '...'
```

Example: chair OPEN, two JOIN, FLOOR to box-b, box-b SAY then YIELD, chair CLOSE.

Transcripts: `$AGENTIC_IRC_HOME/moot/<id>.txt`. Secrets still use SEAL v2 to one nick.

Field box join: `/invite-airc`. Chair `airc-moot-thin.exe --chair` prints a copy-paste thin line (`--pin`, `--channel`, `--moot`, expires 10m). Copy the `airc` folder onto the elder box and run that one command. Win95 TLS is not claimed.
