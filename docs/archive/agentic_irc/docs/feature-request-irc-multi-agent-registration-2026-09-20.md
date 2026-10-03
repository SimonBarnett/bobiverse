<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-irc-multi-agent-registration-2026-09-20.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: harden irc_agent registration for multiple agents on one public IP

**Date:** 2026-09-20  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**Raised by:** Tweet (via Simon)  
**UAT + hostile MRB owner:** Merc (Tweet is reporter + join re-test only)  
**Build orchestrator:** Bob  

## Problem

On IONOS (`WIN-MPRE8VI4U6U`):

- `cm-slab` joins `#cm-bob-oscar` fine (`INFO joined`).
- Home `C:\Users\Administrator\.agentic-irc-tweet` as **`cm-tweet`** (same tree `C:\Users\Administrator\agentic_irc`) never gets numeric **`001`**.
- After CAP LS / Ident / hostname (`ip217-154-57-228.pbiaas.com`), session ends `TimeoutError` and reconnects (`INFO no-sasl` loop).
- `irc.log` never shows registration past hostname/CAP LS notices.
- Same host; no SASL env on either client.

## Impact

Blocked live SEAL handoff Tweet→Slab. Workaround: offline `seal.py seal` + drop into slab `inbox\from-cm-tweet.seal` (Slab confirmed offline open OK).

## Ask

1. Why CAP END + NICK/USER yields no `001` for a second nick while another stays joined (shared public IP / Libera).
2. Clearer INFO on TimeoutError: **NO 001** vs **NO JOIN**.
3. Optional: backoff / stop reconnect spam; document multi-agent-on-one-box Libera limits.
4. Windows `Start-Process` + `RedirectStandardOutput`: confirm no pipe deadlock (hang also without redirect).

## Acceptance

1. Second nick on same box registers, **or** docs state hard limit + supported workaround.
2. Timeout errors name which gate failed (001 vs JOIN).
3. Reconnect backoff implemented and/or documented.
4. Manual/IONOS repro notes; pytest where feasible.
5. Commit/push. Slab UAT + hostile MRB; Tweet re-tests join.

## Non-goals

- Mandating SASL for all agents unless documented as required.
- Secrets in chat.

## Ownership update (2026-09-20)

Tweet is **reporter only** (not agentic_irc UAT owner). **Slab** owns UAT + hostile MRB after the build lands. Tweet will re-test `cm-tweet` join on IONOS when a candidate tip is ready.

## Ownership update (2026-09-20b)

**Merc** owns UAT + hostile MRB. Tweet = reporter + cm-tweet join re-test only.
