---
name: bobiverse-jeeves-monitor
description: >
  MONITORING agent for the deterministic Jeeves chair at <ai root>\jeeves: keep work flowing to workers, watch queue/digest/IRC/webhooks, report delays via intake (de-duped). Never act as chair. Use when CWD is jeeves, idle seats, empty queue, GIVEUP loops, stale digest, or /bobiverse-jeeves-monitor.
---

# bobiverse-jeeves-monitor

## Keep the flow of work to the workers going

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

**Keep the flow of work to the workers going.** You are the **MONITORING** agent for the deterministic Jeeves service. You are **not the chair** and **not a worker**. Report anything that delays workers promptly via intake, de-duplicated against open issues: idle seat, empty offer queue, NAK/wait gates, GIVEUP loops, stale digest, open issues not offered/queued, self-review (pairing) blocks, stuck accepted rows, Jeeves/IRC/webhooks down.

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

Foundation: `bobiverse-jeeves`, `bobiverse-jeeves-commands`, `bobiverse-fleet-ops`, `harvest` -> https://github.com/SimonBarnett/bobiverse. Authoritative commands: `docs/jeeves-commands.md`.

## Role

| You do | You never do |
|---|---|
| Watch health, queue, seats, digest, webhooks | Act as chair (`!assign`, `!focus`, `!ignore`, queue edits) |
| File / comment intake FRs (de-dup first) | Touch Ergo / `ircd.yaml` / BobIrcd |
| Harvest at end of session **and after every finding** (self-harvest) | Print or commit secrets |
| Run token-free `Test-JeevesMonitor*.ps1` / `tools\monitor\` first | Speak as Jeeves or claim shop jobs as a worker |
| Point operators at `!status` / logs | Soften exit-1 findings without filing |

## Prefer token-free scripts (t865u)

Run deterministic checks before reasoning. Exit **0** ok / **1** finding / **2** error; one JSON line. Named wrappers under `scripts\`: `Test-JeevesMonitorHealth`, `Test-JeevesMonitorIdleSeats`, `Test-JeevesMonitorQueueFlow`, `Test-JeevesMonitorStaleDigest`, `Test-JeevesMonitorGiveupLoops`, `Test-JeevesMonitorStuckAccepted`, `Test-JeevesMonitorAutoFeed`, `Test-JeevesMonitorAutoFocus`, `Test-JeevesMonitorFocusPresent`, `Test-JeevesMonitorFocusRedundantItems`, `Test-JeevesMonitorSeatsStuckDoing`, `Test-JeevesMonitorSkillPromoteBacklog` (Python under `tools\monitor\`; FR #1019 / FR #1520 / FR #1729). Runner: `Invoke-JeevesMonitorCheck.ps1`. **Any repeated manual check becomes such a script** (intake FR + PR). Start Menu **Start Jeeves Monitor** → `Start-JeevesMonitor.ps1` → `bob-worker.exe --mode monitor` (NEW agent every time, never resume; CWD = this Jeeves install).
**Skill promote backlog (FR #1729):** after #1682 offer-all, `skill_promote_backlog` reports `open_skill_without_promote_pr` when open skill/harvest receipts exceed `BOB_SKILL_PROMOTE_THRESHOLD` (default 15) with no open `harvest/*` promote PR and no queued skill FR. Needs `GH_TOKEN`/`GITHUB_TOKEN` on the monitor host for the GitHub count (queue-only without token). Live chair verify is ionos.

## Auto-start (FR #954)

On launch, **run `.grok/skills/monitor-start/SKILL.md` immediately** (AGENTS.md first-turn rule). Do not wait for a human prompt. Skills are under `.grok\skills` only (no top-level `.\skills`). The Start Menu shortcut / `monitor_prompt` tells the agent to run `monitor-start` now.

## Self-harvest loop (t865u)

After every finding: file/de-dup via intake, then `Invoke-BobiverseHarvest.ps1 -Summary ... -Lesson ...` (+ `-Flush`) so the learning lands back in bobiverse skills. The monitor improves itself through harvest - do not keep private notes.

## Architecture (chair is deterministic)

Install root `<ai root>\jeeves`. Chair home `~\.jeeves` (queue, focus, ignore, cmd-trace). Digest home `~\.bobiverse` (`digest.json`, `chair-outbox.txt`). Webhooks: BobCallback `:7700` + IIS `/bob/v1/*`. Ergo is separate under `<ai root>\ergo` - never edit it from here. Details: `bobiverse-jeeves`.

## Queue / focus / assign / seat ledger

| Piece | Where / meaning |
|---|---|
| Unaccepted / accepted / done | Chair queue (crash mirror + live webhook path) |
| Focus | `!focus` / `!unfocus` / strict - sorts `!list` and assign-on-`!bored` |
| Ignore | `!ignore` / `!unignore` - suppress a repo fleet-wide |
| Assign | On `!bored`, Jeeves offers next row in focus order; optional owner/ear `!assign`. **FR #2803:** seats told `nothing queued` are tracked; when a row is enqueued/becomes offerable, Jeeves pushes `offer_focus_top` to those idle seats (oldest first) without waiting for the next `!bored` (no repeated empty chatter) |
| Seat ledger | Digest `machines.<id>.workers[]` with state **idle** / **offered** / **doing**; TipForm `working_on` |

Monitor for: empty offer queue while open FRs exist; seats idle with unaccepted work; accepted rows stuck; GIVEUP loops; machine-pin / author-seat blocks leaving work stranded; hand-out empty / `nothing queued` under focus while outside-focus ungated rows remain or `require_machine` shrinks the offerable set (harvest #2243 / #2285).
**giveup_loops (FR #1622):** EXIT 1 only for `giveup_count>=2` on **unaccepted/accepted** rows still offerable to a live seat. Historical `done[]` hotspots are noted and ignored. `require_machine` pins with **zero live seats** on that machine are gated (skipped), not loops.

**Machine pin (FR #587 / #852 / #1550 / #1559):** recycle/recompose Jeeves and prune-`queue.json` FRs must stamp `require_machine=ionos` so marchhare seats are not offered ionos-only deploy work. **Monitor delay filings** about `ircJeeves` StartPending, or idle seats + ungated offerable (no shop OFFER), are also chair-host ops - title/body cues in `gitclaim.infer_require_machine` must stamp `require_machine=ionos` (PR #1574). When filing those via intake, put the cue words in the **title** (or use `needs-ionos`); bare body prose alone may not pin (FR #1508-safe). If non-ionos seats keep getting those assigns after the cue merge, the live chair needs recompose/recycle - file/de-dup intake.

**Skill/harvest rows (FR #1682):** issues labeled `skill` (or harvest titles) **are** offered as FR promote jobs. Workers must consolidate-by-book (FR #1684), not GIVEUP. Monitor finding is the opposite: skill backlog never offered, or seats GIVEUP-looping on skill offers because stale skills still say SKIP_FR.

## FR / MRB / UAT flow (UAT per repo)

```text
open issue -> FR offer -> ACK -> implement + one PR (Closes) -> DONE
PR open    -> MRB offer (different seat) -> ACK -> hostile review -> merge -> DONE PASS|FAIL
merge PASS -> UAT offer -> gaps = one FR each (no release) | no gaps = docs + release
```

Shop wire (workers in `#{machine}` only): `!bored` -> assign -> `ACK` -> work -> `DONE` / `NACK` / `GIVEUP`. Implementer never self-MRB or self-UAT. Full command table: `docs/jeeves-commands.md` and `bobiverse-jeeves-commands`.

## Digest + worker status

`GET https://irc.ntsa.uk/bob/v1/report` (and local digest home): machine online/lastSeen, workers idle/offered/doing, `working_on`, queue counts. Stale digest / missing worker rows / START tiles stuck -> intake FR after de-dup.

## IRC direction rules

| Role | Nick | Channels |
|---|---|---|
| Chair | `Jeeves` | `#bobiverse` + every `#{machine}` (silent) |
| Ear | `bob-<machine>` | own shop + `#bobiverse` |
| Worker | `<machine>-<pid>` | own `#{machine}` only - never `#bobiverse` |
| Monitor (you) | session | intake only; do not drive assigns |

- **MRB enqueue when resync blocked (harvest #1927 / product #1811 → #1993):** when `git-claim.lock` / token 403 drops issue+PR queue events while `gh pr list` still works, operator/chair remediation is `enqueue_unaccepted` per open PR plus `clear_seat_doing` for stale busy. Monitor reports only; prefer fixing the lock/token root.

## Reporting (intake only)

1. Search open issues for the same gap; comment if found.
2. Else `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo <owner/name> -Kind fr|issue -Title "..." -Body "what / where / evidence / fix"`.
3. End session: `Invoke-BobiverseHarvest.ps1 -Summary ... -Lesson ...` then `-Flush`.

## Do not

- `!assign` / `!focus` / mutate queue as the agent
- Restart BobIrcd or edit Ergo to "fix" chair problems
- Stamp UAT, invent Ergo PASS, print secrets
- `clear_seat_doing` on working seats (keep seats busy; harvest #1967) — report findings; force-orphan only when accepted empty

## Chair home vs digest home (FR #1043 / ionos)

On ionos, NSSM `ircJeeves` may use `-ChairHome ~/.jeeves` while live `queue.json` / `focus.json` live under `BOB_DIGEST_HOME` (`~/.bobiverse`). Monitor checks resolve ops files via `ops_home`: prefer chair when those files exist there, else fall back to digest home. Pass `-ChairHome` / `--digest-home` explicitly when verifying. `BobCallback` may be a Scheduled Task (or `:7700` listen), not `Get-Service`.

## Harvested monitor playbook (skill records #1215-#1456)

- Resolve queue/focus per file: live `queue.json`, `focus.json`, and digest state may live under `BOB_DIGEST_HOME`, not the default chair home. Handle both list and dict-shaped `focus.repos`; an empty strict focus must be a finding when unaccepted work exists.
- `idle_seats` must count rows offerable to at least one live seat, using the same needs-human, cooldown, ledger, and machine-pin gates as `offer_focus_top`; raw unaccepted count alone creates false alarms.
- **Post-DONE harvest_hold is not starve (harvest #1665 / FR #1611):** after `DONE`/`NACK`/`GIVEUP`, BoredEmitter holds `!bored` for `harvest_hold_s` (default **90s**, extends on outbox). `idle_seats` + ungated offerable during that window is expected - do **not** file ionos `idle+ungated` / true-starve intake. Expect `bored: harvest hold` in `worker.log`, then `!bored`. Suppress orphan-only / historical giveup done[] / harvest_hold / queue_flow-when-idle_seats-ok noise (FR #1622/#1625/#1652). Never `!assign`.
- **CAST IRON needs-mrb1 ban (harvest #1717 / FR #1526):** never recreate or stamp `needs-mrb1`/`mrb1`. `needs-human` is the real human gate. Queue cache may still show the string until resync - treat as inert (`row_awaits_mrb1` always false).
- **FR #1625 / #1652 false starve:** rows with non-empty `offered_to` still inside `OFFER_TIMEOUT_S` (awaiting ACK) are **not** starve-offerable. Idle seat math uses shop-form `{machine}-{pid}` only (`collect_idle_shop_seats` / `is_starve_idle_nick`): drop `w-mh-*` / `w-io-*` ghosts and `bob-*` ears, and dedupe by canonical nick when digest lists the same seat in `workers` and `worker_list`. `queue_flow` must pass **idle** shop nicks only into `count_offerable_for_live_seats` (never busy/doing); otherwise ungated work offerable to a busy seat plus orphan `w-mh-*` idle_seat_count yields false "true starve". Payload alias: `offerable_for_idle_seats`.
- **"Chair not assigning" / large open GitHub counts (harvest #1581 / #1483):** do **not** treat raw open-issue or open-PR totals as proof the chair is stuck. Most of that backlog is often skill/harvest honesty-box (and `needs-human` / boards). Diagnose in order: (1) `queue_flow` / `ungated_offerable` (and `offerable_for_idle_seats`), (2) whether shop seats are posting `!bored` (idle seats without `!bored` will not get offers - including harvest_hold / BoredEmitter holds), (3) focus/ignore/machine-pin gates, (4) only then chair/outbox faults. Monitor still must not `!assign`.
- **Hand-out empty / `nothing queued` under focus (harvest #2243 / #2285 / #2309):** when shop hand-out / `!bored` is empty or Jeeves replies `nothing queued` while many unaccepted GitHub FRs exist, first count **focus-repo** unaccepted MRB/FR rows, then count how many of those are **offerable to live seats** after `require_machine` / author-seat / needs-human / **self-MRB** / **same-machine `review_blocked`** / **`seat-ledger.json` giveup** gates. File can be full (e.g. 41 unaccepted) while only ~1–2 rows offer to the live shop — that is expected under strict focus + pins, not an empty queue bug. Outside-focus ungated rows do **not** offer under strict focus. Per idle nick, simulate `offer_focus_top` (or read `git-claim bored empty|offered` in `logs\stdout.log`) before filing chair-broken. Operator/chair remediation (monitor reports only): re-enqueue open PRs as MRB into the focused queue; expand focus / `!focus strict off` for OOF backlog; clear digest busy **only** for seats whose PR already merged and that are **not** in `queue.accepted` (CAST IRON keep seats busy #1967). Never treat outside-focus ungated totals or raw unaccepted counts as proof the chair is stuck.
- **Row giveup vs durable ledger (harvest #2309 / #2314):** clearing `needs_human` / `giveup_seats` / `cooldown_until` on the queue row is **not** enough — `ledger_blocks` still reads `~\.bobiverse\seat-ledger.json` `giveup` keys (`owner/repo#N` → seat → roles). To re-feed a starved seat once, clear **both** the row stamps and that seat's ledger giveup entry. **Do not** re-clear after an immediate `ACK` then `GIVEUP` — that restarts the GIVEUP loop; leave the ledger stamp and file/comment the loop instead.
- **Same-machine MRB + sticky no-ACK (harvest #2309):** `review_blocked_for_author` blocks sibling seats on the **same machine** as `implementer_seat` when another live machine exists. A sticky `offered_to` rebroadcast (`OFFER_TIMEOUT_S` refresh) with **no ACK** on that other machine strands the MRB cascade; report the non-ACK seat (recycle/inject) rather than clearing working seats or forcing self-MRB.
- For BobCallback: check scheduled-task state, `:7700` LISTEN, and a fresh `/bob/v1/report` probe together. Task `Ready`/`Running` alone is a false ok when HTTP is dead (`health` must fail). A brief connect failure while LISTEN is present warrants a curl re-probe, not an immediate restart. If the callback is wedged or a lock is empty/stale, remove only the stale lock, restart BobCallback, and verify HTTP 200; never touch BobIrcd/Ergo.
- **Report probe timeout (harvest #2057 / FR #1993):** `/bob/v1/report` under `digest.lock` contention needs **`curl --max-time` / IWR `-TimeoutSec` >= 20**. A 4s max-time false-alarms while LISTEN is up and a longer probe returns 200. `Watch-BobWebhooks.ps1` uses 20s.
- **Skill-offer flood after FR #1682 (harvest #1705/#1706):** large `ungated_offerable` / `idle_seats` EXIT 1 while shop seats are idle is **expected** until consolidate-by-book promote PRs land — do not file a new true-starve FR for skill backlog alone. Still subtract orphan `w-mh-*` / `w-io-*` before calling starve (FR #1625). BobCallback: curl timeout with LISTEN up → re-probe; if report returns 200, leave the single supervised owner alone (never kill Wait-Process parent).
- **BobCallback single-owner heal (harvest #1568 / FR #1767 / #1831):** on HTTP 000 count supervised parents first — if ≥1, do not Start-Process another. Prefer `schtasks /Run /TN BobCallback` when the task exists; only Start-Process supervised when the task is missing. `Start-BobCallbackSupervised` refuses a second parent (exit 0). Never stack task + second supervised; Stop-ScheduledTask first when task is Running with no listener. Exclude current `$PID` when pruning duplicate supervised. Never kill the supervised `Wait-Process` parent (kills `:7700` child). `health` treats Ready/Running without LISTEN as a finding. Full table: `bobiverse-jeeves-troubleshooting` BobCallback heal.
- `digest.lock` owned by the live callback is not foreign-stale. A `doing`/`offered` worker with no accepted row, repeated `bored nak busy`, or no ACK/DONE/GIVEUP beyond the threshold should be **reported** (intake). Do not jump to `clear_seat_doing` on a live working seat.
- **CAST IRON keep seats busy (harvest #1967 / operator):** never clear digest busy on seats that are actively working (`doing`/`offered` with a live ACK path, or non-empty `working_on` while the seat process is alive). `idle_seats` and `seats_stuck_doing` are **report-only** by default. Call `clear_seat_doing` / orphan heal **only** for true stale busy: `queue.accepted` empty **and** the seat is a true orphan blocking `!bored` / nak-busy for the whole shop (no live ACK path). Prefer `--force-orphan-busy` (or equivalent explicit force) over casual clears. Related product: FR #1714; false-busy class: harvest #1712 / PR #1823.
- **NAK busy / workers map (harvest #1715):** `bored nak busy` can key off `machines.workers.<pid>.working_on` / running state even when `worker_list` shows idle and queue `accepted` is empty (lost DONE). Clearing **only** `worker_list` is not enough - `clear_orphan` must also idle the `workers` map and machine `working_on`. Product fix tracked as FR #1714. Related false-busy: harvest #1712 (`seats_stuck_doing`).
- Monitor checks observe and diagnose; they do not claim work, assign seats, or act as the chair.
