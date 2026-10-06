---
name: bobiverse-jeeves-commands
description: >
  Full Jeeves chair command reference, replies, authorization matrix and how to test every command as the bob ear. Use when asked about !help, !list, !filter, !status, !resync, !sweep, !ignore, !focus, !recycle, ping, or Jeeves permissions.
---

# bobiverse-jeeves-commands

## Keep the flow of work to the workers going

**Keep the flow of work to the workers going.** You are the **MONITORING** agent for the deterministic Jeeves service (not the chair, not a worker). Report delays via intake, de-duplicated against open issues: idle seat, empty offer queue, NAK/wait gates, GIVEUP loops, stale digest, open issues not offered/queued, self-review (pairing) blocks, stuck accepted rows, Jeeves/IRC/webhooks down. Never `!assign` / `!focus`; never touch Ergo/BobIrcd; no secrets.


> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

Authoritative reference: `docs/jeeves-commands.md` (read it for the full table, replies and the authorization matrix).

## Command surface (all deterministic, token-less, gh-Jeeves @8d76d9a parity)

| Command | Who | What |
|---|---|---|
| `!help [cmd]` | anyone | role-aware list / one-command detail (PM reply; 30 s per-nick limit) |
| `!list [all\|repo\|fr\|mrb\|uat]`, `!filter ...` | anyone | queue by PM (`!filter` = alias of `!list`; 30 s per-nick limit); strict focus hides unfocused items ("queue empty") |
| `!status` | anyone | version, uptime, queue counts, roster, `github_resync:`, `webhooks:` |
| `!resync` | owner, ears | refresh roster from ChanServ + run the authenticated GitHub FR/MRB resync now; purges ignored repos |
| `!sweep [#chan]` | owner, ears | re-plan +h/+o grants in a channel |
| `!ignore <repo>`, `!unignore <repo>`, `!ignored` | owner/ears (ignored: anyone) | suppress/resume a repo for the whole chair |
| `!focus [strict on\|off]\|[n\|high\|medium\|low] <repo\|owner/repo#N>`, `!unfocus <repo\|owner/repo#N\|all>` | owner, ears, allowlist (`JEEVES_FOCUS_MUTATORS`) | priority-sort `!list` and assign-on-`!bored`. Prefer **repo-level** `!focus high owner/repo` (FR #1520); item `owner/repo#N` is skipped when that repo is already focused, and `!resync` prunes leftover items |
| `!assign <worker-nick> <repo> <FR\|MRB\|UAT> <num>` | owner, ears | make Jeeves post the normal assign line to one idle seat (seats only obey Jeeves); the seat's ACK accepts it. Rules: seat not busy, no self-MRB/UAT (seat ledger), row queued + unaccepted, not needs-human/cooldown/given-up/machine-pinned. UAT is per repo: `UAT 0` = the repo-level UAT, queued only when every issue is closed and every PR merged. Reply by PM |
| `!recycle [machine\|all\|dry-run [machine\|all]]` | owner, ears | route a seat recycle (bare/all = fleet; 120 s cooldown). `dry-run` only prints the plan. `!recycle jeeves` restarts `ircJeeves` only |
| `!register <machine>` | operators | ChanServ REGISTER `#<machine>` |
| `ping` / `ping <glob>` | anyone | bare word (no `!`), channel or PM -> `pong` |
| `!bored`, `ACK`/`DONE`/`NACK`/`GIVEUP` | workers in `#<machine>` | shop wire, not PM commands: assign / claim / finish jobs. **FR #2811:** after GIVEUP/NACK ok, chair may push next eligible job via `offer_focus_top` (`offered_via=giveup`, longer sticky); send nothing when empty (no `nothing queued`) |

## Who counts as who (authorization)

- **owner** = a verified NickServ account in `JEEVES_OWNER_ACCOUNT`/`BOB_OP_ACCOUNTS` (the nick alone is never enough).
- **ear** = nick `bob-<roster machine>` (case-insensitive), refused if logged in to a different non-bob account.
- **allowlist** = `JEEVES_FOCUS_MUTATORS` / `JEEVES_FOCUS_MUTATOR_ACCOUNTS`, focus/unfocus only.
- Denials reply like gh-Jeeves (`focus: denied (owner account required)`, `ignore: denied (simon or bob-* ops only)`); `!sweep` denial is a one-line reply.

## Testing a command as the bob ear (no real side effects)

Append `PRIVMSG #bobiverse :!help` (UTF-8 no BOM, `\n`) to the ear's `home\outbox.txt`; pace 3 s apart (32 s for `!help`/`!list`).
Read `<chair home>\cmd-trace.log` for timed replies and `logs\stdout.log` for `kind=ear` lines. Safe set: `!help`, `!status`,
`!list`, `!filter fr`, `!ignored`, `!ignore zz-test/none` + `!unignore zz-test/none`, `!focus`, `!recycle dry-run`, `ping`.
Restore any state you changed (`!focus strict on` if it was on). Never send `!recycle`, `!recycle <machine>` or `!bored` for real.

Chair pytest: `!assign` tests that hit `fr_row_offerable` must stamp fixture rows `state=open` + issues URL and monkeypatch `github_is_pull_checker` / `github_issue_open_checker` / `github_pr_exists_checker` so a live GH token cannot 404-refuse the fake repo (FR #2730 / MRB #2756 / harvest-lesson #2757).

## Harvested resync and deployment rules (skill records #1221-#1460)

- Resync all GitHub issue pages, not only the newest 100; a pagination regression silently starves older FRs. Keep fetch timeout/retry and stale/off-main alerts enabled.
- Before copying live scripts, ensure the install worktree is on `main` and clean; never let a leftover feature branch or failed fetch silently drift the live chair behind `origin/main`.
- After a merged PR, fast-forward main, sync the installed tree, and restart only `ircJeeves`/the affected scheduled task. Verify the live endpoint and the relevant queue/monitor smoke before declaring success.
- Frozen chair `!status`: VERSION must resolve install-root / `JEEVES_INSTALL_ROOT` / `sys.executable` before `Path(__file__)` under `_MEIPASS`; uptime must use `Client` construct time (`_process_started`), not lazy first-command `_cc()` (FR #2728 / MRB #2733 / harvest-lesson #2734).
