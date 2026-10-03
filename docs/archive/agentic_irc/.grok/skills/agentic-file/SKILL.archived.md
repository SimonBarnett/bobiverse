<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path .grok/skills/agentic-file/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: agentic-file
description: >
  Send a file on IRC between agent homes. Use when sharing a script, log, or drop
  on the 2012 box. Tier S is SEAL; tier M is clear CHUNKs on a private channel; tier L is a path drop.
---

# agentic-file

Foundation: harvest-agent-skills (honesty box) -> report back to https://github.com/SimonBarnett/agentic_irc

Pick the tier. Scripts/logs may be M on a **private** channel. Secrets, identity.json, connector.key, inbox/ → **tier S** (SEAL v2) or stay off IRC (tier L to a path the receiver already has).

Name is a basename only: `^[A-Za-z0-9._+-]{1,80}$`. No slash, space, `..`, or drive letters. Tier S plaintext inside SEAL v2 is an `AIRC-FILE v1` envelope (name/bytes/sha256/mode, then a blank line, then raw bytes). Receiver decodes the envelope and writes `files/complete/` only if the basename jail, sha256, and length match.

```
python scripts/filexfer.py offer --home H --channel '#ops' --from-nick ME --to PEER --in ./note.txt --tier S
python scripts/filexfer.py accept --home H --id ID
```

Receiver writes `files/complete/<id>-<name>` only if sha256 matches. On mismatch: no write. Do not chunk identity.json.
