<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-reply-same-call-channel-2026-09-23.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Plan
1. Track `_last_call_channel` on channel PRIVMSG when `_joined_channel`.
2. Bare outbox drain uses that channel via new `say_to` / `say` update.
3. pytest for sticky + grok_talk.reply_target_for.
