# Jeeves chair commands (gh-Jeeves parity) and who may run them

The bobiverse chair (`irc_agent.py --chair`, service `ircJeeves`) carries every command the old Python
`gh-Jeeves` service handled in IRC (reference: `SimonBarnett/gh-Jeeves` @ `8d76d9a`, `src/jeeves/commands.py` +
`roles.py`). Everything is deterministic and token-less (roster = ChanServ mirror, digest, webhook queue; no GitHub
token, no secrets, no Ergo config edits). Replies are **private messages only**; typing a command in `#bobiverse` or
`#<machine>` never produces channel text (except the shop wire lines `!bored` assign and the `RECYCLE` route).
Source: `scripts/chair_commands.py` (registry, `!help`, principals, `!recycle` decision), `scripts/focus_ignore.py`
(focus / ignore store), glue in `scripts/irc_agent.py` (`_maybe_chair_commands`, `_handle_recycle_command`, ...).
Every reply is also appended to `<chair home>/cmd-trace.log` (bounded to ~256 KB) for audit.

## Commands

| Command | Reply (PM) | Notes |
|---|---|---|
| `!help [cmd]` | one line per command visible to the asker; `!help <cmd>` = at most 5 lines | 30 s rate limit per nick: `rate limit: wait Ns before !help again`; unknown / hidden: `unknown command; try !help` |
| `!list [all\|<repo>\|fr\|mrb\|uat]` | `N unaccepted (showing M)` + one job line each, `+K more; !list all` | focus order, ignore list applied; `(list sent Ns ago)` when repeated within the list rate window |
| `!filter [..]` | same as `!list <filter>` | alias (not in gh-Jeeves @8d76d9a; added because ops use the word) |
| `!status` | `Jeeves status: version=.. uptime_s=..`, `queue: unaccepted=U accepted=A`, `workers: busy=..`, `roster: machines=N (..)`, `last_resync: roster Ns ago` | read only. `uptime_s` is process/agent age (not first-command age). `version` resolves install-root `VERSION` when frozen (FR #2728). `workers: busy` counts digest `worker_list` seats with `state=doing` (not the accepted-queue length; that stays on the `queue:` line) |
| `!resync` | `resync: roster refresh requested; GitHub FR/MRB re-sync queued; queue unaccepted=U accepted=A purged_ignored=P` | **fallback** (FR #5170): forces ChanServ roster re-read and authenticated GitHub FR/MRB merge-resync. Live queue updates come from git webhooks; use `!resync` on startup/gap/delivery failure, not as the main check |
| `!sweep [#chan]` | `sweep: #chan re-planned; N grant/revoke sent` | re-runs the privilege plan (+h/+o) for the channel (asks NAMES first); subject to the hard cap below |
| `!ignore {repo}` / `!unignore {repo}` / `!ignored` | `ignore: now ignoring X (purged N queued)` / `unignore: resumed X (new events only)` / `ignored: (none)` or `ignored (N):` + `  repo` | bare: `ignore: usage !ignore {repo}` |
| `!focus [strict on\|off]\|[n\|high\|medium\|low] {repo\|owner/repo#N}` | `focus: owner/repo priority=1 (high)`, `focus: item o/r#5 rank=2`, `focus: skipped o/r#N (per-repo focus already covers …; FR #1520)`, `focus strict: on`; bare lists strict flag, items, repos | reading (`!focus`, `!focus strict`) is open to anyone. **Prefer repo-level focus** (`!focus high owner/repo`); item keys are refused when that repo is already focused (FR #1520). `!resync` also prunes redundant items. **FR #4969:** repos with GitHub topic `priority-customer` (refreshed once per resync via search, persisted beside the queue) sort after all non-customer work. Tag a customer repo: `gh repo edit SimonBarnett/<repo> --add-topic priority-customer`. Removing the topic restores normal priority on the next resync. Explicit `!focus` / item focus on a customer repo still wins. Topic lookup failure logs WARN and keeps the last set (queue is not blocked). |
| `!unfocus {repo\|owner/repo#N}\|all` | `unfocus: removed X` / `unfocus: cleared R repo + I item entries` / `unfocus: X was not focused` | |
| `!assign {worker-nick} {repo} {FR\|MRB\|UAT\|FIX} {num}` | `assign: sent <nick>: FR o/r#N <url>` (PM to the caller) or `assign: refused - <reason>` / `assign: usage ...` / `assign: denied (simon or bob-* ops only)` | **simon (verified account) or a Bob-\* ear only.** Jeeves stamps that queued row offered to the seat and posts the normal assign line (`format_assign_line`) in the seat's shop channel as Jeeves; the seat's `ACK` accepts it exactly like a `!bored` offer. Eligibility is the `!bored` rules: seat must be idle (not busy in the digest), no self-MRB/UAT (the author/implementer seat is refused), row must be queued and unaccepted (FR #4422: an open FR/MRB missing from the queue is fetched from GitHub and enqueued, then offered; FR #4652: FIX mode is accepted the same way for a red open PR (enqueued when missing; needs_human FIX refused) — no longer a hard refuse), not needs-human / on GIVEUP cooldown / already given up by that seat / pinned to another machine, and not offered to another seat inside the offer timeout. Seats only obey lines from Jeeves, so manual feeding goes through this command. Works from PM or a joined channel; the reply is always a PM |
| `!cleargiveup owner/repo#N [seat]` | `cleargiveup: owner/repo#N seat=all\|<seat> queue_rows=N ledger=N` / usage / denied | **Ops only (FR #5135).** Queue lock: clear giveup_seats / cooldown_until / giveup_ts / giveup_count / needs_human (or one named seat). Also clears seat-ledger giveup[owner/repo#n] for that seat or the whole key. |
| `!recycle [machine\|all]` | bare / `all` = every roster seat: `Recycling all seats (a, b, ..).` then `recycle: routed to bob seat(s) (fleet fleet); Jeeves runs no host ops`, `recycle: steps=..`, `recycle: bob must announce restarting then execute (deterministic)`; `!recycle <machine>` = `Recycling <machine>.` | Jeeves only **routes**: a `RECYCLE` wire line goes to `#bobiverse` (fleet: `RECYCLE machine=fleet by=<nick> scope=fleet exec=local-bob-seat`; one machine: `RECYCLE v1 <machine>`) and the target `bob-<machine>` announces and executes. The chair's own machine recycles locally; `!recycle jeeves` restarts the chair. 120 s duplicate cooldown per target: `recycle: cooldown Ns (duplicate prevented)`; unknown: `recycle: unknown machine X (want: .., all)` |
| `!recycle dry-run [machine\|all]` | `recycle dry-run: would recycle X (scope) as <owner\|ear>; nothing sent` + the route and steps | authorises and plans, sends nothing, no cooldown. Safe for tests (`dry`, `plan`, `check` also work) |
| `!build <owner/repo>[,..] <version> [ref]` / `!build status|cancel|dry-run ...` | PM: queued / dry-run plan / refused (no recipe, single-flight, denied) | **Ops only (simon / bob-*).** FR #4006/#4025 deterministic BUILD: in-repo `.bobiverse/build.yml`, no agent tokens. `<version>` must be numeric `x.y.z` or `x.y.z.w` (digits only); `v0.1.32` / `0.1.32-test2` are refused (#4186). Chair announces `BUILD v1` on #bobiverse; recipe machine (`ionos`/fold) enqueues + runs suites/pack/prerelease (never Latest); auto `release-blocker` issues. |
| `!installtest <owner/repo> <version> [tag]` / `!installtest dry-run ...` | PM: queued / dry-run plan / refused (no install_test, wrong machine, denied) | **Ops only (simon / bob-*).** FR #4026 WP3 INSTALL-TEST: msiexec pre-release MSIs + post-checks; release-blocker on fail; recipe `install_test` on ionos/fold. |
| `ping` / `ping <glob>` (no `!`) | `pong` | in a channel or by PM |
| `!register <#channel|machine>` | `ACK registered #<mid>` after ChanServ confirms; else `ERR !register ChanServ ...` / timeout; denied: `ERR !register denied (+o/+h required)` | +o/+h in #bobiverse (FR #4008 / #5274); ACK + roster + `REGISTERED v1 <mid>` on #bobiverse only after ChanServ REGISTER ok (or already-registered); operators.txt ignored |
| `!unregister <#channel|machine> [confirm]` / `!unregister dry-run <..>` | plan PM then `ACK unregistered #<mid>`; dry-run sends nothing; core refuse; idempotent not-registered | +o/+h gate; confirm or repeat within 60s; ChanServ UNREGISTER (+ code NOTICE); remove_registered; PART; `UNREGISTERED v1 <mid>` in #bobiverse; airc falls back to #wonderland (FR #3834/#4008); dry-run/confirm plan lists `*_console` nicks in `#<mid>` or `none seen` (FR #4040) |
| shop wire: `!bored`, `ACK`, `DONE`, `NACK`/`GIVEUP` | assign line / quiet | unchanged (`gitclaim`, `shop_listen`) |

* **GIVEUP `out-of-fuel` (FR #4181):** after a successful shop `GIVEUP … out-of-fuel`, the chair notes the nick in `seat-out-of-fuel.json` and **skips** FR #2811 `giveup-offer` (log `giveup-offer skipped … reason=out-of-fuel`). `offer_after_release` / `offer_focus_top` / `bored_gate` also refuse while marked. A fresh `!bored` clears the mark (worker only bores after fuel returns per bob-worker FR #3012) then offers normally. Other GIVEUP reasons keep giveup-offer.

## Queue hygiene (FR #180 / #258 / #595)

`gitclaim` never offers junk or fake work, even when `!focus` would otherwise select it:

* **FR skip labels** (`SKIP_FR_LABELS`): **`skill` is not SKIP_FR** (FR #1682: chair offers skill/harvest intakes as promote FRs; they still do not block repo UAT). Remaining: `umbrella`, `parent-fr`, `mrb-home` / `mrb_home`, `evergreen` / `evergreen-mrb`, and verdict boards `mrb`, `mrb-pass`/`mrb_pass`, `mrb-fail`/`mrb_fail` (**FR #2562 / #2677**: reverse #2464 — `mrb-fail` / `mrb_fail` stay SKIP_FR forever; remediation belongs on child product FRs, never on the verdict board). Matched at enqueue, claim, offer, prune, and resync. Legacy rows with an empty `title` still skip when `labels` or `line`/`title` text carry board tokens (`mrb-fail`, `mrb-pass`, `mrb-home`, ...); bare `mrb` is labels-only so real titles like "harden MRB/FR ..." stay offerable. Pull URLs must match the row `repo`.
* **FR hold** (FR #4009, mirrors FR #3928 for issues): label `hold` / `on-hold`, or an owner `**HOLD (…):**` body stamp, never enqueue or offer as FR. `fr_hold_reason` / `row_fr_hold_reason` gate enqueue, offer, `!assign`, and purge. **`hold` is not SKIP_FR** so held product FRs still block repo UAT until cleared or closed. When hold clears (label removed / stamp gone) and the issue is ready (e.g. `feature-request` added), resync re-enqueues normally.
* **MRB verdict titles** (FR #2562 / #2677 / #2687): titles matching `^MRB\s+(FAIL|PASS)\s*[-:]` (`MRB_VERDICT_TITLE_RE`) are SKIP_FR and do not block repo UAT. Colon or dash separators both match (`MRB FAIL: ...` / `MRB FAIL - ...` / `MRB PASS: ...`). Hard pin `simonbarnett/agentic_fomprep#11` (reverse #2521) stays in `_SKIP_FR_ISSUE_PINS`.
* **GIVEUP needs_human threshold** (FR #180 / #2562 / #2677 / #3277): early GIVEUPs stay per-seat (`giveup_seats`). Once `needs_human` is stamped, auto-offer (`!bored`, done-offer, idle, LOST_ACK revive) blocks **every** seat (FR #4336); only explicit `!assign` may hand the row out. Early GIVEUPs before the stamp stay per-seat via `giveup_seats` / cooldown (FR #1236). Give-up / NACK exclusions are exact-seat only (FR #5088); recycled fresh nicks are not blocked by a dead predecessor's giveup_seats on auto-offer. UAT still inherits a dead author seat on the same machine (FR #4336). Self-MRB GIVEUP (giver is `author_seat`/`implementer_seat`) does not increment `giveup_count` or stamp `needs_human`. **FR #4881:** GIVEUP `reason=out-of-fuel` likewise does not increment `giveup_count`, append `giveup_seats`, stamp `cooldown_until`, or set `needs_human` (seat mark FR #4181 is enough; the row stays offerable to a fuelled seat). **FR #4711:** an owner GitHub `issue_comment` (created) after `giveup_ts` clears `needs_human` / `giveup_count` / `giveup_seats` / `cooldown_until` and logs `needs_human cleared repo#n by=owner-comment` so the next `!bored` can offer again. Seat-shaped comments (`GIVEUP`/`ACK`/`DONE`/`## MRB board` / `reason=needs_human`) never clear. Hook events must include `issue_comment` (see `bob_git_hook.py`).
* **needs-mrb1** (legacy FR #1363; operator 2026-10-04): not a `SKIP_FR` label and **not an offer block** (`row_awaits_mrb1` always false — label was an intake hallucination). Intake no longer stamps it. GIVEUP/NACK always stamps `cooldown_until`; BobCallback principal / SYSTEM vs `.bobiverse` cues stamp `require_machine=ionos`.
* **UAT dual-seat block** (FR #265 / #227 / #635 / #649 / #665 / #618): repo-level UAT rows stamp `implementer_seat` (FR DONE) and `mrb_author_seat` (MRB PASS); `review_blocked_for_author` skips either seat (and same-machine siblings) while another machine is live. Legacy `author_seat` still works. When a repo UAT `#0` row is missing stamps, `enrich_uat_author_fields` fills seats from related accepted/done MRB rows (via `refs` / `merged_prs` / `mrb-N` cues) at offer time so cycle implementers and MRB/fix authors are not offered that UAT. Complements the seat ledger (t852u/t853u); per-PR UAT is never offered.
* **Self-MRB block** (FR #593 / #227): PR-opened / ready_for_review MRB rows stamp `author_seat` / `implementer_seat` from the linked accepted/done FR implementer nick (not only DONE FR enqueue), so the chair skips offering MRB to that seat while another machine is live.
* **Citing DONE FR** (FR #2623): when DONE FR points at a pull URL, `implementer_seat` / `author_seat` on the queued MRB prefer an existing MRB stamp or an earlier DONE FR that already cited that pull. A re-offered FR whose DONE only cites another seat's open PR must not overwrite the true implementer (otherwise both seats on a two-seat shop can be blocked from the hostile MRB). Ledger FRW for that citing DONE stays informational (t860u).
* **UAT is per REPO (t853u)**: there are no per-PR / per-issue UAT rows. A merge (webhook or MRB PASS) queues nothing; legacy per-PR UAT rows are pruned on every resync. The hourly / gap GitHub resync queues exactly ONE repo-level UAT row (UAT owner/repo#0, repo_uat, url https://github.com/owner/repo, merged_prs = the PRs merged this cycle) once the repo is **clear**: every open issue is closed or excluded (needs-human, blocked, release-gate, boards/mrb-home, harvest/skill records, CRITICAL spam shapes / bare seat-filed `CRITICAL:` without via-intake or feature-request, safe-to-close — FR #2670: via-intake / feature-request `CRITICAL:` filings are real FR work and **do** block UAT until closed) AND no PR is open, AND at least one PR was merged since the last repo UAT finished (cycle start = last DONE UAT, default 48 h). A new open issue/PR before the row is offered withdraws it. Eligible seat: one that neither authored (ledger role FR / PR commit author) nor MRB'd (ledger role MRB) any merged PR of the cycle — same self-UAT rule the worker skill applies (FR #2939). Empty !bored replies report `self_uat=N` like `self_mrb`. When every live seat is self-UAT or giveup blocked, the chair stamps `needs_human` and announces on #bobiverse that UAT needs a fresh/uninvolved seat or a human (no all-blocked escape that offers a seat which then refuses). Sibling `review_blocked` still ignores giveup / fellow-implementer seats on other machines so a same-machine sibling without cycle FR/MRB touches can take UAT when another machine has no viable free seat. **Live seats** come from digest `worker_list` (FR #1401) — legacy `workers` ghost PIDs that never `!bored` are ignored so they cannot strand the escape hatch. A seat that gave the repo UAT up never gets it again. DONE UAT starts the next cycle.
* **Seat ledger (t852u)**: seat-ledger.json beside queue.json is durable (GitHub resync rebuilds queue rows and drops their stamps). It records, per owner/repo#N, which seat did FR (implement; also PR commit authors) / MRB, and per row which seats gave it up. MRB is never offered to the implementer of the PR or its linked issues; nothing is re-offered to a seat that GIVEUP/NACKed it. **t860u:** only a PR's real commit authors (role FR, learned from GitHub) and the MRB reviewer block review/UAT; working an FR (FRW: ACK/DONE, DONE existing PR, no duplicate) is informational, and a GIVEUP on a *linked* row only blocks the same job kind (a seat that gave up the UAT of a linked issue can still review the PR).
* **Fuel chain (FR #5317 / #5865):** `BOB_FUEL_CODERABBIT`, `BOB_FUEL_COPILOT`, and `BOB_FUEL_FLEET` are each off unless set to `1`/`on`/`true`. When CodeRabbit is on and `.coderabbit.yaml` is present, `offer_focus_top` / `offer_top` hold an MRB until a review covers the current head SHA (`coderabbit=ready`), CodeRabbit fails/skips (`failed`), silence marks the app absent after 2 min (`absent`), or `BOB_CODERABBIT_WAIT_MIN` (default **12**) elapses (`timeout`). Assign lines always carry `coderabbit=<mode>` and `review=<light|full>` (sensitive paths force full). Removing the yaml or the app is an off switch (`absent`, no 12-min wait). `mrb_merge_gate` refuses while `coderabbit=pending`; merge-on-green treats the CodeRabbit check as non-blocking once the gate has cleared. Copilot is never required for a fleet offer. MRB DONE may append `cr_mode=... review=... tokens=<n> cr_findings=<n> fixed=<n> rejected=<n> na=<n>` (legacy confirmed/fp still parse); Jeeves records those fields for the digest light-vs-full comparison.
* **MRB pull URL** (FR #595 / #247 / #740 / #738 / #1323 / #1585): assign lines and offers use only a real https://github.com/{repo}/pull/N URL or an explicit pr_id / pr. The chair never invents /pull/{issue_id} from a bare row id. Rows with an issues-shaped URL, missing pull URL, a pull that 404s, or a pull that is **merged/closed** (when a GitHub token is available) are skipped at offer and purged from unaccepted; a real open /pull/240-style row stays offerable. After DONE MRB PASS/FAIL the same repo+#id is never re-offered (`done[]` plus durable ledger `mrb_done`, 7d hold) — even after `done[]` trim, offline, or a resync race that left `offered_to` on a MERGED phantom — **unless** GitHub still shows the pull **open** (premature DONE): then resync re-queues the MRB with a pull URL, clears the stale `mrb_done` stamp, and offer purge keeps the row (FR #1585). Author-seat / same-machine self-MRB blocking is unchanged.
* **require_machine** (FR #587 / #732): enqueue infers 
equire_machine from labels (
eeds-<machine>, 
equire_machine:<machine>, machine:<machine>) or title/body cues (PRIORITY_WP0_INSTANCE=ce-priority-dev, WP0 live, ce-priority-dev → ce-priority-dev1; 
eeds-ionos / chair-outbox → ionos). offer_focus_top and !assign (ssign_row / 
ow_machine_mismatch) both re-infer cues so unstamped legacy rows cannot be force-assigned to the wrong machine.

## Authorization matrix

A **principal** is derived per message from the nick plus the services account the chair learned *this session*
(account-tag / extended-join / account-notify / WHOIS 330). A nick alone never proves anything.

| Principal | How it is recognised |
|---|---|
| **owner** | services account `JEEVES_OWNER_ACCOUNT` (default `simon`), or an account in `BOB_OP_ACCOUNTS` / `op-accounts.txt`. Nick `simon` with no account (unverified) is **not** the owner. |
| **ear** | nick `bob-<machine>` (any case, e.g. the live `Bob-win-mpre8vi4u6u`) of a machine in the ChanServ roster - the same trust root that earns the ear its `+o` / `+h`. A `bob-x_` fallback nick, an unregistered machine, or a look-alike logged in to a different account is refused. |
| **allowlist** | nick in `JEEVES_FOCUS_MUTATORS` or account in `JEEVES_FOCUS_MUTATOR_ACCOUNTS` (additive, default empty) - `!focus` / `!unfocus` only. |
| anyone else | read-only commands |

| Command | owner | ear (`bob-<machine>`) | allowlist | anyone |
|---|---|---|---|---|
| `!help` `!list` `!filter` `!status` `!ignored` `ping`, `!focus` / `!focus strict` (read) | yes | yes | yes | yes |
| `!ignore` `!unignore` | yes | yes | no | no |
| `!focus ..` `!unfocus ..` (write) | yes | yes | yes | no |
| `!resync` `!sweep` `!recycle` `!assign` `!cleargiveup` | yes | yes | no | no |

`!assign <nick> <owner/repo> UAT 0` hands out the repo-level UAT row (`#0`).

Denial replies (gh-Jeeves strings): `ignore: denied (simon or bob-* ops only)`, `unignore: denied (simon or bob-* ops only)`,
`focus: denied (owner account required)`, `unfocus: denied (owner account required)`,
`assign: denied (simon or bob-* ops only)`, `recycle: denied (authorised operator + services account required)`; `!resync` / `!sweep` reply
`resync: denied (simon or bob-* ops only)` / `sweep: denied (simon or bob-* ops only)` (gh-Jeeves stayed silent).
A denied command from a nick whose account is still unknown also triggers a rate-limited `WHOIS` so the next try works.

Differences from gh-Jeeves @8d76d9a, deliberate:

* the ear (`bob-<machine>`) may also `!focus` / `!unfocus` / `!sweep` (gh-Jeeves: owner only unless `JEEVES_FOCUS_MUTATORS`), per Simon's
  "commands must work when issued by the bob ear nick";
* the ear is recognised by the **roster** (`bob-<registered machine>`), not by any `bob-*` string;
* the owner is recognised by **account** (any nick), not by the nick `simon` / `simon-*`;
* `!recycle` previously had no authorization check in the bobiverse chair at all; it now requires owner or ear;
  bare `!recycle` means the fleet (gh-Jeeves FR #197/#211) instead of a refusal; `dry-run` is new;
* `!status` also shows `github_resync:` and `webhooks:` (see Chair background jobs); `!resync` merges open FR/MRB from GitHub (never wipes accepted jobs);
* `!focus medium` (a bare priority word) is a usage error, gh-Jeeves focused a repo called "medium".

## Privilege grants (`+h` / `+o`) - hard cap

`chan_privs.py` grants `+h bob-<machine>` in `#bobiverse`, `+o bob-<machine>` in `#<machine>`, and `+o bob-<machine>` in
`#wonderland` (FR #3836; never `*_console` / worker seats). Idempotent: nothing is sent
when NAMES / MODE already show the rank (`%` halfop and multi-prefix `%+` are parsed; our own and server-sourced
(SAMODE) MODE echoes are recorded but never re-planned). **Hard cap: at most 3 sends per (channel, nick, mode) in any
10 minutes**; the 4th is suppressed with one `WARN ... suppressed: already sent 3x in 600s (hard cap 3)` per window.
If a mode we granted is removed by someone else (ChanServ AMODE / founder rule / another op) the chair logs
`WARN ... -h nick in #chan was removed by <actor> (not Jeeves)` once per 10 minutes - the signature of a fight.
`!sweep` clears retry back-off but not the cap. The `simon unverified in #chan: WHOIS to learn account` line is logged once
per 30 minutes per nick (with a count of suppressed repeats); the WHOIS itself keeps its cadence.

## Chair background jobs (inside `ircJeeves`)

| Job | Interval | What it does |
|---|---|---|
| webhook health probe | 30 min | `GET /bob/v1/report`, `/bob/v1/jira`, `/bob/v1/intake/jeeves-health-probe` and a synthetic `POST /bob/v1/git` ping (zen `jeeves-health-probe`, answered 204, no queue entry) against `http://127.0.0.1:7700` and `https://bob.ntsa.uk`. One retry before a target counts as down. State in `webhook-health.json`; announces to `#bobiverse` only on an up/down transition. |
| GitHub FR/MRB merge-resync | hourly + webhook gap (FR #3212) | Authenticated (existing Jeeves token, source logged once per process in `resync-token-source.log`, value never logged). **Webhooks are the source of truth**; this reconcile is the exception path (startup, gap in deliveries, or hourly ETag/304 conditional GETs under `github_api_budget`). **FR #4959:** open issues and open pulls are fetched independently (a 304 on issues must not skip pulls); both-304 repos log as `unchanged=N` (so `repos=0` is not "no repos"); startup and `!resync` force-refresh (no If-None-Match). Merges open FR/MRB into the queue; keeps accepted jobs, other task kinds, offered rows, failed and ignored repos; never purges on 403/401/429/5xx. Repos: `JEEVES_RESYNC_REPOS` or `resync-repos.txt` in the chair home, else queued repos plus the token owner's repos, **union `focus.repos`** (FR #3146; short keys expand to `SimonBarnett/<name>`). No token = run skipped, queue untouched. `!status` also shows `github-api:` remaining. **FR #4422:** when reconcile is skipped for hourly budget or rate-limit floor, log `WARN github-resync skipped: …` with the reason and schedule a retry at `X-RateLimit-Reset` (stale `remaining=0` clears after reset so the next try can run). |

`!resync` triggers the roster refresh and the GitHub resync immediately; `!status` reports both.

## Onboard a repo + clear give-ups (FR #5134)

Operator playbook skill: `jeeves/.grok/skills/bobiverse-jeeves-repos/SKILL.md` (`bobiverse-jeeves-repos`).

* **Resync list Jeeves reads:** `%USERPROFILE%\.jeeves\resync-repos.txt` (chair `--home` / `BOB_HOME`) via `configured_repos`, plus `JEEVES_RESYNC_REPOS`, plus union of digest-home `focus.repos` (FR #3146). Install also seeds a twin under `%USERPROFILE%\.bobiverse\resync-repos.txt`; edit the chair-home file (or keep both identical).
* **Onboard:** append `owner/repo`, `!focus low|medium|high owner/repo`, then `!resync` (reply: `resync: roster refresh requested; GitHub FR/MRB re-sync queued; ...`). Example: `!focus low SimonBarnett/priority-branding` -> `focus: SimonBarnett/priority-branding priority=9 (low)`. Webhook add needs Simon yes.
* **Give-up clear:** `GIVEUP_COOLDOWN_S=600`. Clear both digest-home `queue.json` give-up stamps and `seat-ledger.json` `giveup["owner/repo#n"]` (lower-case). `!resync` does not clear them. Then `!assign`. Back up first; never restart Jeeves during `!build`. Preferred (FR #5135): ops `!cleargiveup owner/repo#N [seat]` (implemented).
* `!help` lists `!focus` and `!resync` for authorised principals.

## Remote worker start: `!startworker` (Bob ear, t810u)

Not a chair command: it is handled by the **Bob ear of the target machine** (`bob-<machine>`), never by Jeeves (Jeeves runs no host ops).
Source: `common/scripts/startworker.py` (decision) + `irc_agent.py` (`_maybe_startworker`) + `bob/tray/tools/BobTrayStartWorker.ps1` (tray side).

| Syntax | Where | Reply |
|---|---|---|
| `!startworker [agent\|plan] [machine]` | in `#<machine>` (machine optional) or `#bobiverse` (machine **required**) or PM to the ear | `ACK startworker agent on <machine> (queued <id>; workers N/CAP; by <nick>)` or `NACK startworker: <reason>` on the same channel (PM for a PM) |

* **Who**: a *verified* services account only. `simon` (`JEEVES_OWNER_ACCOUNT` / `BOB_OP_ACCOUNTS`), `Jeeves`, or a `bob-<machine>` ear logged in to the account of the same name. A nick alone, a look-alike nick under another account, or a worker seat (`<machine>-<pid>`) is refused (`NACK ... denied`); an unknown account is `NACK ... not verified` and triggers a WHOIS so the retry works. An ear for another machine stays silent.
* **How it launches**: the ear runs as a service in session 0 and cannot open a window. It only authorises, caps and writes `<install>\run\startworker\req-<id>.json` (`{id, mode, by, kind, ts, expires}`, no secrets). The tray (interactive session) heartbeats `tray.alive` and, every 2 s, consumes requests (deleted before launch = at-most-once, dropped after 60 s) and runs the **same function as the Agent / Plan click** (`Start-BobTrayWorkerExe`), so the worker gets its own visible console and a fresh `<machine>-<pid>` nick, joins `#<machine>` and posts `!bored`. Audit: `res-<id>.json`.
* **Nobody logged in** (no fresh `tray.alive`, i.e. no interactive user with the tray running): `NACK startworker: nobody is logged in with the Bob tray running (...)`.
* **Limits**: at most `BOB_STARTWORKER_MAX` worker seats (default 4; root `bob-worker*.exe` processes, plan windows included) -> `NACK ... N/CAP workers already running`; `BOB_STARTWORKER_COOLDOWN_S` (default 30) between accepted starts -> `NACK ... cooldown Ns`. Kill switch: file `<ear home>\startworker.disabled` or `BOB_STARTWORKER_DISABLE=1` -> `NACK ... disabled`.
* **Worker input (t812u)**: a worker only injects lines **FROM `Jeeves` (exact nick) addressed to its own nick** (PM, or text starting `<nick>:`); other workers' lines, channel chatter and other bots never reach the model. PING/PONG and the fleet `ping` are answered by the exe.

### Closed issues leave the queue (t826u, FR #180 point 4)

- An `issues closed` webhook drops that issue's FR/PR rows (and a manually queued UAT row). The UAT row a **merged PR** queued (`action=uat`) is kept: every FR PR carries `Closes <owner>/<repo>#N`, so the merge closes the issue and its UAT must still be assigned.
- The hourly / gap GitHub resync also drops FR/MRB rows whose issue is closed, so a missed webhook self-heals. No separate prune job is needed.
- `Closes #N` and `Closes owner/repo#N` both link a PR to its issue; a link naming another repo is ignored for this repo's queue.

### UAT author enrich (FR #618)

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

UAT is per repo only (`UAT owner/repo#0` + `repo_uat`; t853u). Author stamps on that row can still be missing when DONE MRB stamped a Closes issue id or when stamps were dropped on resync. At offer time, `enrich_uat_author_fields` copies `implementer_seat` / `mrb_author_seat` / `mrb_fix_author_seat` from related accepted/done MRB rows (matching `refs` / `merged_prs` / `mrb-N` in title/line). `offer_focus_top` and `offer_top` both apply the author block after enrich. First related MRB wins (accepted before done).

## Live deploy evidence

Skill-intake consolidation: when a worker takes an FR from skill intake (label:skill / harvest), it must close all open issues for that skill book (every harvest/skill issue targeting the same book), open one consolidated PR for them, and cite every issue it closes (Closes #N for each); no per-issue PRs for the same skill book; the worker closes the issues itself as part of DONE.

- FR #1016 ionos chair/queue verification: [fr-1016-ionos-live-evidence.md](./fr-1016-ionos-live-evidence.md)

## !register / !unregister (FR #4008 / #5274)

| Command | Gate | Notes |
|---------|------|-------|
| `!register <#channel|machine>` | live +o/+h in #bobiverse | ChanServ REGISTER; ACK + roster + `REGISTERED v1 <mid>` only after ChanServ confirms (or already-registered); timeout/fail -> ERR, no ACK; operators.txt ignored |
| `!unregister dry-run <..>` | same | prints plan (includes `*_console` list / none seen, FR #4040), sends nothing |
| `!unregister <..> [confirm]` | same | plan then confirm/repeat within 60s; ChanServ UNREGISTER (+ code round-trip); PART; `UNREGISTERED v1 <mid>` on #bobiverse |
| core refuse | - | `#bobiverse` / `#wonderland` refused |
| airc | - | unregistered shop clients fall back to #wonderland (FR #3834) |
