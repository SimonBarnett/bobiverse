---
name: bobiverse-jeeves-commands
description: >
  Full Jeeves chair command reference, replies, authorization matrix and how to test every command as the bob ear. Use when asked about !help, !list, !filter, !status, !resync, !sweep, !ignore, !focus, !recycle / !build (FR #4006) / !installtest (FR #4026), bobiverse-build skill, repo onboard / give-up clear (FR #5134), ping, or Jeeves permissions.

---

# bobiverse-jeeves-commands

## Keep the flow of work to the workers going

**Keep the flow of work to the workers going.** You are the **MONITORING** agent for the deterministic Jeeves service (not the chair, not a worker). Jeeves itself files stall issues (FR #5164: self-review deadlock, all-gave-up, sticky auto-pin, resync fail, stale ACK, !bored latency) with a stable fingerprint, twin comment, and rate cap. Keep-it-running is a light 2-hourly check of that path. Never `!assign` / `!focus`; never touch Ergo/BobIrcd; no secrets.


> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://bob.ntsa.uk/bob/v1/intake`; offline it is
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
| `!assign <worker-nick> <repo> <FR\|MRB\|UAT> <num>` | owner, ears | make Jeeves post the normal assign line to one idle seat (seats only obey Jeeves); the seat's ACK accepts it. Rules: seat not busy, no self-MRB/UAT (seat ledger), row queued + unaccepted (or **accepted only under a departed nick** — FR #3400 releases with `prior ACK void` then offers), not needs-human/cooldown/given-up/machine-pinned; refuse a nick **absent** from a non-empty shop `worker_list` (`not in the shop channel`). Never steal from a live accepted holder. UAT is per repo: `UAT 0` = the repo-level UAT, queued only when every issue is closed and every PR merged. Reply by PM |
| `!cleargiveup owner/repo#N [seat]` | owner, ears | FR #5135: clear queue giveup stamps + seat-ledger giveup key (or one seat); PM summary |
| `!recycle [machine\|all\|dry-run [machine\|all]]` | owner, ears | route a seat recycle (bare/all = fleet; 120 s cooldown). `dry-run` only prints the plan. `!recycle jeeves` restarts `ircJeeves` only |
| `!build <owner/repo>[,...] <version> [ref]` / dry-run/status/cancel | owner, ears | FR #4006/#4025 deterministic BUILD from `.bobiverse/build.yml` (no agent) |
| `!installtest <owner/repo> <version> [tag]` / dry-run | owner, ears | FR #4026 WP3 INSTALL-TEST: msiexec + post-checks; release-blocker on fail |
| `!register / !unregister (FR #4008 / #5161 / #5274) <machine>` | +o/+h in #bobiverse | ChanServ REGISTER/UNREGISTER `#<machine>`; !register ACK + `REGISTERED v1` only after ChanServ confirms (else ERR/timeout); dry-run/confirm; core refuse; airc -> #wonderland; unregister tombstones the shop so a lagging ChanServ LIST cannot re-add or rejoin |
| `ping` / `ping <glob>` | anyone | bare word (no `!`), channel or PM -> `pong` |
| `!bored`, `ACK`/`DONE`/`NACK`/`GIVEUP` | workers in `#<machine>` | shop wire, not PM commands: assign / claim / finish jobs. **FR #2811 / #3893 / #4089:** after GIVEUP/NACK/DONE **ok only** (never DONE status=missing), chair may push next eligible job via `offer_focus_top` (`offered_via=giveup|done`, sticky offer_timeout_s); one open job per seat (no push while accepted/pending offer; seat-holds.json; **FR #4260:** re-offer to another nick or DONE/NACK/GIVEUP by any seat clears all holds for that job key); log `done-offer` / `giveup-offer` / `done-offer skipped`; send nothing on the channel when empty (no `nothing queued`). **FR #4181:** after `GIVEUP … out-of-fuel`, mark `seat-out-of-fuel.json` and **skip** giveup-offer / refuse offers until a fresh `!bored` clears the mark; other GIVEUP reasons keep the FR #2811 giveup-offer path (product PR #4190) |

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

- **!unregister (FR #4008 / #4040 / #5161):** mirror of !register; gate is live +o/+h (operators.txt removed); dry-run/confirm; core channels refused; airc falls back to #wonderland; dry-run/confirm plan lists `*_console` nicks seen in `#<mid>` (or `none seen`). Unregister is final locally: the roster tombstones the shop and ignores a lagging ChanServ LIST (no re-add, no JOIN) until LIST confirms the channel is gone.
- **FR #4181 out-of-fuel giveup-offer:** after `GIVEUP … out-of-fuel`, chair marks `seat-out-of-fuel.json`, skips giveup-offer, and refuses offers until a fresh `!bored` clears the mark; other GIVEUP reasons keep FR #2811 giveup-offer (do not park this under `harvest/SKILL.md`).

## !build (FR #4006 / skill FR #4038)

Ops-only. `!build <owner/repo>[,...] <version> [ref]`, `!build status|cancel|dry-run`. Requires in-repo `.bobiverse/build.yml`. `<version>` must be numeric `x.y.z` or `x.y.z.w` (digits only); `v0.1.32` / `0.1.32-test2` are refused (#4186). Chair is token-less decide + announce; suite/pack/release run on the recipe machine (WP2). Full playbook (classification, announce lines, when to re-run): skill `bobiverse-build` / `jeeves/.grok/skills/bobiverse-build/SKILL.md` and `docs/bobiverse-build.md`.

## Repo onboard + give-up clear (FR #5134)

Full operator playbook: skill `bobiverse-jeeves-repos` (`jeeves/.grok/skills/bobiverse-jeeves-repos/SKILL.md`).

- **Discovery file Jeeves reads:** `%USERPROFILE%\.jeeves\resync-repos.txt` (chair `--home` / `BOB_HOME`) via `configured_repos`, plus env `JEEVES_RESYNC_REPOS`, plus union of digest-home `focus.repos` (FR #3146). A twin is seeded at `%USERPROFILE%\.bobiverse\resync-repos.txt` but is not what discovery reads when homes differ.
- **Onboard:** append `owner/repo` to the chair-home list (and/or `!focus low|medium|high owner/repo`), then `!resync`. Expected reply: `resync: roster refresh requested; GitHub FR/MRB re-sync queued; ...`. Example: `!focus low SimonBarnett/priority-branding` -> `focus: ... priority=9 (low)`.

- **FR #5163 / #5268 MRB reviewer deadlock:** when every idle seat is ineligible for every waiting MRB, Jeeves may clear cross give-ups (idle non-authors) or queue one tray `recycleseat` (kind `mrb-reviewer-deadlock`), deduped/~180s. Cross-giveup clear requires two or more idle seats. A sole idle seat that GIVEUP'd the only waiting MRB is not healed (give-up sticks; FR #2811 / #628). No manual `!cleargiveup` for a true multi-seat stall.
- **Give-up re-assign:** `GIVEUP_COOLDOWN_S=600`; clear **both** digest-home `queue.json` stamps (`giveup_seats`, `cooldown_until`, `giveup_ts`, `giveup_count`, `needs_human`) **and** `seat-ledger.json` `giveup["owner/repo#n"]` (lower-case key). `!resync` does **not** clear them. Then `!assign <seat> owner/repo FR|MRB|UAT|FIX N`. Back up both files first; never restart Jeeves during `!build`. Gap: recommend `!cleargiveup` (not implemented yet).

`!help` already lists `!focus` and `!resync` for authorised principals.

## !installtest (FR #4026 WP3)

Ops-only. `!installtest <owner/repo> <version> [tag]`, `!installtest dry-run ....` Requires `install_test` in `.bobiverse/build.yml`. Chair is token-less decide + announce; msiexec/post-check run on the recipe `install_test.machine`. Failures become release-blocker issues (WP2 filer).

