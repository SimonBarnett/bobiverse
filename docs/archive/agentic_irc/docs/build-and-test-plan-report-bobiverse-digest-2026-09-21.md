<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-report-bobiverse-digest-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: !report + !bobiverse JSON digest

**Date:** 2026-09-21
**FR:** `docs/feature-request-report-bobiverse-digest-2026-09-21.md`
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/36
**Profile:** generic
**Do not:** open Ergo from CI, print connect.password, POINT BOB v1 to
the channel as a compatibility hack, push `main`, MRB in-session.

## Work tree

Branch `work/<jobId>` off current `main`. Open a PR. Never push `main`.

## Steps (agentic_irc)

1. Add a digest store in-process (and optional file under `--home`,
   e.g. `digest.json`). Not SEAL inbox.
2. Parse `!report` in `irc_agent` / `bobtalk.py` (or a sibling
   `bobreport.py` imported by both). First token `!report`.
3. Implement TASK START/STOP, PCENT, UPTIME, `?` / `help` per FR.
4. `!bobiverse` answer path: whisper compact JSON digest to asker.
   If over ~350 chars, chunk `BOB DIGEST v1 i/n`. Never PRIVMSG the
   JSON to `#bobiverse`.
5. Drop or gate any remaining code that says a full `BOB v1` POINT
   into the channel from this client. POINT parse of **incoming**
   historical lines may stay for one release.
6. Update `.grok/skills/bob-irc/SKILL.md`: write `!report`, read
   `!bobiverse` JSON, no tick firehose.
7. Pytest offline: fixtures for each verb, secret refuse, help,
   digest merge, no-echo flag, alias `dev1`/`ce-priority-dev1`.

## Steps (agentic_build, if same worker or a follow-up git task)

1. `Write-BobIrcStatus` / Watch: emit `!report …` on change only.
2. Test-Pack: idle ticks do not produce POINT channel lines.
3. Docs `docs/bobiverse.md` point at this FR.

If build cannot move in this PR, comment that gap on #36 and still
ship irc ingest + JSON read so Halloy can be tested by hand.

## Prove

```bash
pip install -r requirements.txt pytest
pytest -q
```

No socket to `irc.ntsa.uk` or Libera.

## Halloy UAT (Bob, after PASS-nits)

1. Idle minute: `#bobiverse` has no new `MOOT v1 POINT` walls.
2. From a `bob-*` (or test harness): `!report TASK START …` — digest
   updates; channel does not repeat the raw command as a blob.
3. `!bobiverse` from `simon` — JSON arrives as whisper, not as a
   channel paste.
4. `!report ?` — help whisper.

## Done when

PR open, pytest green, issue #36 commented with PR URL, wait for
handed-off MRB. FAIL → FIX PR. PASS-nits → MRB agent merges.
Only Bob stamps UAT.
