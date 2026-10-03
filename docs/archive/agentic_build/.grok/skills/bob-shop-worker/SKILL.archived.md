<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-shop-worker/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-shop-worker
description: >
  Attach a Grok/Cursor MRB or git-task worker to the machine shop IRC channel.
  Use when starting Start-BobBuild, hostile MRB, cursor MRB, or any fleet job
  that should show "This is what I'm working on" on #flamingo / #ionos / etc.
---

# Shop worker attach

Canon: `agentic_irc` issue #46 +
`docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md` in both repos.
Fleet table: `config/bobiverse.json`. Do not use Windows hostnames.

## On start

1. Machine id from `bobiverse.json` nicks keys (`flamingo`, `marchhare`,
   `ionos`, `ce-priority-dev1`). Alias `dev1` = `ce-priority-dev1`.
2. `pid` = this process id. Nick `w-<shortid>-<pid>` (fl/mh/io/d1).
3. `--home` `~\.agentic-irc-bobiverse\workers\<id>\<pid>`.
4. JOIN `#<machine-id>` only. Do **not** JOIN `#bobiverse`.
5. `working_on` = one English line from the git-task title / MRB issue.
   Shop line: `This is what I'm working on: …`
6. POST `reportUrl` (`X-Bob-Secret` from `~\.grok\bob\report.secret`).
   Never `!report`.

## While running

- Visible assistant text → shop (flood 0.8s, ~350 chars).
- Thinking traces + tool transcripts → worker Query **only if that PM is open**.
- Drop `password=` / `XAI_API_KEY=` / connect.password / PIN / PSK lines.

## On exit

QUIT shop. If the process dies without QUIT, Watch POSTs `delete-worker`.
If local `bob-<id>` is dead, Watch POSTs `shop-down` and workers PART.

## Do not

- POINT or `!report` on `#bobiverse`.
- Stamp UAT.
- Print secrets.
