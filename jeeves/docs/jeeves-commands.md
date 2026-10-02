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
| `!status` | `Jeeves status: version=.. uptime_s=..`, `queue: unaccepted=U accepted=A`, `workers: busy=..`, `roster: machines=N (..)`, `last_resync: roster Ns ago` | read only |
| `!resync` | `resync: roster refresh requested; GitHub FR/MRB re-sync queued; queue unaccepted=U accepted=A purged_ignored=P` | forces the ChanServ roster re-read now, queues the authenticated GitHub FR/MRB merge-resync (Jeeves token) and purges ignored repos |
| `!sweep [#chan]` | `sweep: #chan re-planned; N grant/revoke sent` | re-runs the privilege plan (+h/+o) for the channel (asks NAMES first); subject to the hard cap below |
| `!ignore {repo}` / `!unignore {repo}` / `!ignored` | `ignore: now ignoring X (purged N queued)` / `unignore: resumed X (new events only)` / `ignored: (none)` or `ignored (N):` + `  repo` | bare: `ignore: usage !ignore {repo}` |
| `!focus [strict on\|off]\|[n\|high\|medium\|low] {repo\|owner/repo#N}` | `focus: owner/repo priority=1 (high)`, `focus: item o/r#5 rank=2`, `focus strict: on`; bare lists strict flag, items, repos | reading (`!focus`, `!focus strict`) is open to anyone |
| `!unfocus {repo\|owner/repo#N}\|all` | `unfocus: removed X` / `unfocus: cleared R repo + I item entries` / `unfocus: X was not focused` | |
| `!recycle [machine\|all]` | bare / `all` = every roster seat: `Recycling all seats (a, b, ..).` then `recycle: routed to bob seat(s) (fleet fleet); Jeeves runs no host ops`, `recycle: steps=..`, `recycle: bob must announce restarting then execute (deterministic)`; `!recycle <machine>` = `Recycling <machine>.` | Jeeves only **routes**: a `RECYCLE` wire line goes to `#bobiverse` (fleet: `RECYCLE machine=fleet by=<nick> scope=fleet exec=local-bob-seat`; one machine: `RECYCLE v1 <machine>`) and the target `bob-<machine>` announces and executes. The chair's own machine recycles locally; `!recycle jeeves` restarts the chair. 120 s duplicate cooldown per target: `recycle: cooldown Ns (duplicate prevented)`; unknown: `recycle: unknown machine X (want: .., all)` |
| `!recycle dry-run [machine\|all]` | `recycle dry-run: would recycle X (scope) as <owner\|ear>; nothing sent` + the route and steps | authorises and plans, sends nothing, no cooldown. Safe for tests (`dry`, `plan`, `check` also work) |
| `ping` / `ping <glob>` (no `!`) | `pong` | in a channel or by PM |
| shop wire: `!bored`, `ACK`, `DONE`, `NACK`/`GIVEUP`, `!register <machine>` | assign line / quiet | unchanged (`gitclaim`, `shop_listen`, `registered_machines`); not PM commands |

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
| `!resync` `!sweep` `!recycle` | yes | yes | no | no |

Denial replies (gh-Jeeves strings): `ignore: denied (simon or bob-* ops only)`, `unignore: denied (simon or bob-* ops only)`,
`focus: denied (owner account required)`, `unfocus: denied (owner account required)`,
`recycle: denied (authorised operator + services account required)`; `!resync` / `!sweep` reply
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

`chan_privs.py` grants `+h bob-<machine>` in `#bobiverse` and `+o bob-<machine>` in `#<machine>`. Idempotent: nothing is sent
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
| webhook health probe | 30 min | `GET /bob/v1/report`, `/bob/v1/jira`, `/bob/v1/intake/jeeves-health-probe` and a synthetic `POST /bob/v1/git` ping (zen `jeeves-health-probe`, answered 204, no queue entry) against `http://127.0.0.1:7700` and `https://irc.ntsa.uk`. One retry before a target counts as down. State in `webhook-health.json`; announces to `#bobiverse` only on an up/down transition. |
| GitHub FR/MRB merge-resync | 15 min | Authenticated (existing Jeeves token, source logged once per process in `resync-token-source.log`, value never logged). Merges open FR/MRB issues into the queue; keeps accepted jobs, other task kinds, offered rows, failed and ignored repos; drops closed FR/MRB rows. Repos: `JEEVES_RESYNC_REPOS` or `resync-repos.txt` in the chair home, else queued repos plus the token owner's repos. No token = run skipped, queue untouched. |

`!resync` triggers the roster refresh and the GitHub resync immediately; `!status` reports both.

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
