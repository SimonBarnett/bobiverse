<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-irc-is-a-mess-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: irc is a mess (#167)

FR: `docs/feature-request-irc-is-a-mess-2026-09-23.md`.

## Build

1. `channels_for_nick` / `Start-TalkSeat` / worker spawn
   - `#bobiverse`: Jeeves + `bob-*` (operator Halloy OK).
   - `#{machine}`: `bob-{id}` + talk + `w-*`.
   - Watch/talk that must hear fleet: JOIN both; reply on the addressed target.
   - `w-*` never `#bobiverse`.
2. Drop Query `working_on`. `post_working_on.py` is the only status path. Skill + scripts.
3. Assign: `bob-*` PRIVMSG shop, not Query.
4. Jeeves GIT stays `chair-outbox` / `#bobiverse` only.
5. Duplicate flamingo: Start-TalkSeat refuse steal; killproc one home; tests if any.
6. Harvest `bob-irc` / agentic_build wrappers as a **PR** if join defaults live there.
7. Open a PR. Do not push `main`. No UAT.

## Test

- pytest / Test-Pack for nick→channel map, no `PRIVMSG simon` working_on in skill/scripts.
- Hermetic: dual-channel listen does not drop shop when fleet is first `--channel`.

## Do not

- Stamp UAT. Mode 3 PIN on `#bobiverse`. Second 11904 lanes.
