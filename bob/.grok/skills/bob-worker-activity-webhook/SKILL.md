---
name: Bob worker activity webhook
description: >-
  Use when TipForm shows stale START jobs, workers must report or clear activity
  on the digest webhook, idle seats should show no jobs, or workers must !bored
  after 2m idle.
---
# Worker activity on the digest webhook

## Source of truth
Peer activity for TipForm is **`https://irc.ntsa.uk/bob/v1/report`** (`machines.<id>.jobs`, `running`, `queued`, `working_on`, `repo`, plus **agent** + **model** on each job). Same webhook owns the **unaccepted** GIT claim queue (see Bob GIT ACCEPT claim).

## Worker agents MUST
1. **On start** of real FR/MRB/UAT work: publish activity (`Write-BobIrcStatus` / Watch-Bobiverse tick) with repo + running + **agent** + **model**.
2. **On finish / fail / cancel / idle**: clear activity — empty `jobs`, `running=0`, `queued=0`, clear `working_on`.
3. **Idle > 2 minutes with no work:** send **`!bored`** (Cursor, Grok, Aider, free — every worker process). Keeps Jeeves queue flowing. See Bob GIT ACCEPT claim.
4. **Never** treat bob-* IRC ear presence as a coding START job. Never publish bare `repo: irc` as a worker job.

## TipForm / operators
- Expect `no jobs` on every seat when no worker process is alive.
- Stale START tiles: clear fingerprint / republish; counts must follow filtered `jobs` only.

## Related
- [Bob digest webhook fuel](sand-workflow:bob-digest-webhook-fuel)
- [Bob GIT ACCEPT claim](sand-workflow:bob-git-accept-claim)
- agentic_build: `Write-BobIrcStatus`, TipForm, shop watchers
