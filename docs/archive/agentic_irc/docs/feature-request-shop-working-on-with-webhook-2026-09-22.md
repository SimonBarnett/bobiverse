<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-shop-working-on-with-webhook-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: shop working_on at the same time as webhook

**Date:** 2026-09-22
**Repo:** https://github.com/SimonBarnett/agentic_irc
**GitHub:** https://github.com/SimonBarnett/agentic_irc/issues/102
**Raised by:** Simon on #agentic_irc

## LOCKED

1. Worker webhook POST with working_on and shop PRIVMSG
   (`{nick}: This is what I'm working on: …`) are the **same event**.
2. Going idle: webhook the idle **description** first (shop + POST), then
   POST state=idle. Never idle silently.
3. Channel is #{machine}, not #bobiverse. No secrets on the shop line.

## Deliverable

- post_working_on.enqueue_shop_working_on on working_on and on --idle
- irc_agent._cc_working_on POSTs webhook after shop PRIVMSG
