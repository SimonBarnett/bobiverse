<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-git-webhook-jeeves-announce-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: extend webhook to accept git webhooks; Jeeves announces (park-only)

**Ask (Simon `#bobiverse` 2026-09-23):**
fr on irc please: extend the webhook to accept webhooks from git. These
will be announced by jeeves.

**Repo:** https://github.com/SimonBarnett/agentic_irc  
**Park-only** until Simon says go. Do not dispatch.

## Summary

The ionos digest webhook today is `POST /bob/v1/report` (write-only fleet
digest merge, `x-bob-secret`, allow-list). Simon wants that surface
extended so **git** (GitHub) can POST events. **Jeeves** (digest chair)
announces those events on IRC. Talk seats do not send `!bobiverse`.

## Gap vs current tree

`scripts/bobcallback.py` / `apply_callback` accept the bob digest JSON
only. There is no git/GitHub event route, no Jeeves announce of pushes,
PRs, or issues from a git webhook.

## LOCKED

1. Target repo is `agentic_irc` (existing webhook + Jeeves chair).
2. Extend the webhook to accept git webhooks. Do not invent a second
   public host. Prefer the existing write-only ionos callback, or a
   documented sibling path on the same listener.
3. Jeeves announces accepted git events. Do not have `bob-*` or talk
   seats narrate them.
4. No secrets in git, issues, or channel text (no webhook secret, no
   HMAC, no tokens).
5. No UAT stamp. Talk seats never send `!bobiverse`.

## UNKNOWN

- Exact GitHub events (push, pull_request, issues, ping only, …).
- Announce channel (`#bobiverse` vs shop vs whisper).
- Whether this reuses `x-bob-secret` or a separate GitHub HMAC (do not
  invent the header or the secret path).
- Payload fields Jeeves must print (repo, SHA, actor, title).
- IP allow-list vs GitHub hook source ranges.

## Acceptance (when dispatched)

- A1: A git webhook POST is accepted by the documented route.
- A2: Jeeves announces that event on IRC. No fleet-status spam.
- A3: Digest `POST /bob/v1/report` behaviour is unchanged for bob peers.
- A4: No secrets in repo. No UAT stamp. Tests cover the new route without
  a live GitHub.

## Out of scope

Implementing until Simon says go. Changing Watch digest producer
(agentic_build #196). Client or trigger packs.

Workers do not stamp UAT.
