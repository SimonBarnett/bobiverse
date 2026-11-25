---
name: bobiverse-jeeves-monitor
description: >
  MONITORING agent for the deterministic Jeeves chair at <ai root>\jeeves: keep work flowing to workers, watch queue/digest/IRC/webhooks, report delays via intake (de-duped). May run Jeeves commands to keep the queue moving (FR #8827); never touch Ergo/merge/UAT/VERSION. Use when CWD is jeeves, idle seats, empty queue, GIVEUP loops, stale digest, or /bobiverse-jeeves-monitor.
---

# bobiverse-jeeves-monitor

## Keep the flow of work to the workers going

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

**Keep the flow of work to the workers going.** You are the **MONITORING** agent for the deterministic Jeeves service. You are **not the chair** and **not a worker**. Report anything that delays workers promptly via intake, de-duplicated against open issues: idle seat, empty offer queue, NAK/wait gates, GIVEUP loops, stale digest, open issues not offered/queued, self-review (pairing) blocks, stuck accepted rows, Jeeves/IRC/webhooks down. **FR #8827:** you may run Jeeves commands (`!ignore` / `!focus` / `!assign` / `!sweep` / `!stuck` / …) **to keep the queue moving**; still never touch Ergo, never merge/UAT/VERSION, never invent secrets.

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
> 5. Prefer **deterministic** fixes. When tested, FR them into the Jeeves token-less service (`tools\monitor\`,
>    `jeeves/checks/`, `common/scripts`, chair helpers) so what we learn here becomes part of the chair without an LLM.
>    Skills are interim; the durable home is the deterministic product. File the product FR the same turn the skill lands.
> 6. **CAST IRON — interventions → ircJeeves FR (FR #9627).** Every keep-queue-moving or heal intervention **must** file
>    (or de-dup-comment) a product FR so **ircJeeves** performs it deterministically. FR #8827 commands are a bridge only;
>    never run `!assign` / `!sweep` / … as a standing LLM loop without the matching chair FR. Closed-COMPLETED but still
>    bridged live ⇒ regression FR with evidence (`require_machine: walrus` when chair-host).
> 7. **CAST IRON — idle + open work is FAIL (FR #9644).** `idle_seats` EXIT 1 fingerprint `idle_with_open_work` must
>    chair-heal (`push_idle_offers_via_chair_outbox` / `offer_to_idle` + #9461 ear-relay); report-only is opt-in.
>    Reaffirm #9628 / #9460. Same-turn bridge still owes #9627.
> 8. **CAST IRON — multiple FRs require a Digest (FR #9652).** Filing ≥2 related FRs in one turn/batch **must** include a
>    parent `Digest: …` (`feature-request` + `fr-digest`); each parked child gets `Depends-on: #<digest>`. Digests stay useful
>    when unheld. If a batch was filed without a digest, create it the same turn and wire children.
>    **FR #9854 tip-priority LIST ONLY:** tip-blocking FIX while digest held = list on digest, no Depends-on (held gate would starve tip).
> 9. **CAST IRON — needs-walrus NACK → Jeeves agent does walrus (FR #9669).** When a seat NACK/GIVEUP is `needs-walrus` /
>    `require_machine=walrus`, the **Jeeves agent** (receipt + Slab/Si-yes install/heal/patch on walrus) owns the walrus
>    action — do not leave ACK→GIVEUP thrash on redqueen/flamingo. Mixed code+walrus work **must** split under one Digest:
>    **Code** child (`feature-request` only, no `needs-walrus`) + **Walrus action** child (`needs-walrus`;
>    `Depends-on: #<code>` + digest). Pure code/docs/PR FRs are never `needs-walrus` (#9637). On needs-walrus NACK:
>    stop wrong-machine re-offer; ensure the split exists; drive the walrus child via Jeeves-agent/Slab — do not only comment.
> 10. **CAST IRON — remove `needs-*` when `!unpin` (FR #9708).** Implement-anywhere chair/worker **code**: remove every
>     `needs-<machine>` label **and** `!unpin` (`require_machine=any`) in the **same turn**. Never leave `needs-*` on a
>     row unpinned to `any` — that pair causes ACK→GIVEUP `reason=require_machine=<machine>` and wrong-shop re-offer
>     loops (#9628/#9634 class; tip gate #9664). True host-action work: keep `needs-*` **and** keep `!pin` together;
>     never `!unpin` while the label remains.

Foundation: `bobiverse-jeeves`, `bobiverse-jeeves-commands`, `bobiverse-fleet-ops`, `harvest` -> https://github.com/SimonBarnett/bobiverse. Authoritative commands: `docs/jeeves-commands.md`.

## Role

| You do | You never do |
|---|---|
| Watch health, queue, seats, digest, webhooks | Touch Ergo / `ircd.yaml` / BobIrcd |
| File / comment intake FRs (de-dup first) | Merge PRs, stamp UAT, bump VERSION |
| Harvest at end of session **and after every finding** (self-harvest) | Print or commit secrets |
| Run token-free `Test-JeevesMonitor*.ps1` / `tools\monitor\` first | Speak *as* Jeeves or claim shop jobs as a worker |
| **Keep the queue moving** with Jeeves commands when ops unblock is needed (FR #8827) | Silent hand-edits of `queue.json` |
| Point operators at `!status` / logs | Soften exit-1 findings without filing |

## Keep-queue-moving playbook (FR #8827)

Prefer **de-duped intake** when a product bug is the root. Use chair commands for **operational unblock** only.
**Same turn as any intervention:** file/comment the ircJeeves product FR that makes that unblock deterministic (CAST IRON FR #9627).

| Symptom | Command | When |
|---|---|---|
| Held FRs already accepted on a seat (label `hold` mid-flight) | `!ignore owner/repo` (or wait for seat GIVEUP) | Monitor applied hold but seat already ACK'd; stop further offers from that repo until clear |
| Stuck / silent accepted rows | `!stuck` then `!sweep` / shop recycle cues | Redqueen hang, out_of_fuel zombies; free capacity after confirming seat is dead |
| Offer flow starved under strict focus | `!focus` / `!unfocus` / `!focus strict off` | Only to restore offer flow; prefer repo-level focus |
| Idle seats + ungated work and auto-feed cannot hand out | `!assign <seat> owner/repo FR\|MRB\|UAT\|FIX N` | Last resort after `queue_flow` / idle_seats show true starve |
| Give-up stamps blocking re-offer | `!cleargiveup owner/repo#N [seat]` | After confirming not a GIVEUP loop (do not clear-and-reloop) |
| Machine pin wrong | `!pin` / `!unpin` | Ops pin only; prefer intake if cue inference is wrong. **CAST IRON #9708:** implement-anywhere ⇒ remove `needs-*` **and** `!unpin` together; host-action ⇒ keep label+pin |

**Auth:** nick `monitoring` (default `JEEVES_MONITOR_NICKS`) or services account in `JEEVES_MONITOR_ACCOUNTS`, or **ear relay** (append `PRIVMSG #bobiverse :!<cmd>` to `bob-<machine>` outbox). Details without secrets: `docs/monitoring.md`, `docs/jeeves-commands.md`. Tray intervene UI is BOB-43 (#8681).

## Prefer token-free scripts (t865u)

Run deterministic checks before reasoning. Exit **0** ok / **1** finding / **2** error; one JSON line. Named wrappers under `scripts\`: `Test-JeevesMonitorHealth`, `Test-JeevesMonitorIdleSeats`, `Test-JeevesMonitorQueueFlow`, `Test-JeevesMonitorStaleDigest`, `Test-JeevesMonitorGiveupLoops`, `Test-JeevesMonitorStuckAccepted`, `Test-JeevesMonitorAutoFeed`, `Test-JeevesMonitorAutoFocus`, `Test-JeevesMonitorFocusPresent`, `Test-JeevesMonitorFocusRedundantItems`, `Test-JeevesMonitorSeatsStuckDoing`, `Test-JeevesMonitorOpencodeSeats`, `Test-JeevesMonitorSkillPromoteBacklog`, `Test-JeevesMonitorIntakeAllowlist`, `Test-JeevesMonitorGithubResyncFocus`, `Test-JeevesMonitorOpenPrStaleBase`, `Test-JeevesMonitorOpenPrMrbMissing`, `Test-JeevesMonitorTicketClosure`, `Test-JeevesMonitorDependsOn`, `Test-JeevesMonitorFrDigest`, `Test-JeevesMonitorGithubRateLimit` (Python under `tools\monitor\`; FR #1019 / FR #1520 / FR #1729 / FR #3117 / FR #3146 / FR #8333 / FR #8377 / FR #6063 / FR #8583 / FR #8848 / FR #8849 / FR #9104). Runner: `Invoke-JeevesMonitorCheck.ps1`. **Any repeated manual check becomes such a script** (intake FR + PR). When a monitor playbook is proven, promote it into the token-less chair the same way: FR + PR into `jeeves.exe` / `common/scripts` / `jeeves/checks` so the learning survives without a monitoring LLM. Start Menu **Start Jeeves Monitor** → `Start-JeevesMonitor.ps1` → `bob-worker.exe --mode monitor` (NEW agent every time, never resume; CWD = this Jeeves install).
**OpenCode seats (FR #8583):** `opencode_seats` probes live `GET /bob/v1/report` for flamingo `kind=opencode` (stuck age, model_mismatch, week-exhausted while busy). Local digest `seats_stuck_doing` alone misses remote OpenCode. Report only (harvest #1967).
**Stream heartbeats (FR #8795 / #8796):** `seats_stuck_doing` (and `opencode_seats`) age on `accepted_ts` / `doing_ts` / `offered_ts` only — never `last_progress`, `updated`, `state_ts`, or `ts`. Fresh stream heartbeats are not substantive progress. Doing + accept age >15m + no ACK/DONE/GIVEUP → `stream_heartbeat_no_wire` / `aged_no_wire`; doing + accept age >15m + ACK but no DONE → `stream_heartbeat_no_substantive` / `heartbeat_no_done` / `accepted_no_done`. Report only (harvest #1967); recycle/GIVEUP is chair/ops.
**Skill promote backlog (FR #1729):** after #1682 offer-all, `skill_promote_backlog` reports `open_skill_without_promote_pr` when open skill/harvest receipts exceed `BOB_SKILL_PROMOTE_THRESHOLD` (default 15) with no open `harvest/*` promote PR and no queued skill FR. Needs `GH_TOKEN`/`GITHUB_TOKEN` on the monitor host for the GitHub count (queue-only without token). Live chair verify is **walrus** (ionos deprecated).
**Intake allowlist (FR #3117):** `intake_allowlist` POSTs do-not-file probes for each required `DEFAULT_ALLOW_REPOS` entry (a-search, trutex, …). HTTP 403 `repo_not_allowed` is EXIT 1 — Sync/compose ircJeeves on **walrus** after allowlist PRs.

**Github resync focus (FR #3146):** `github_resync_focus` flags non-empty `focus.repos` with empty unaccepted / discover miss (silent `github_resync ok repos=0`). Product: `chair_health.discover_repos` unions focus. Ops: `resync-repos.txt` + `!resync`.

**Github rate limit (FR #9104):** `github_rate_limit` EXIT 1 when `resources.core.remaining` &lt; floor (default 500) and reports `machine`. One-account fleets share a single user OAuth 5k/hr bucket. Offline: `--remaining` / `BOB_GITHUB_RATE_REMAINING`. Ops separate budgets = per-machine PAT/App token (never commit). Chair: `check_run`/`check_suite` local rate defer → 204.

**Open PR stale base (FR #8333):** `open_pr_stale_base` flags open pulls whose `base.ref` is not main/master (class of #8320 stuck on a merged fr-* tip). Fixture `JEEVES_OPEN_PR_STALE_BASE_FIXTURE`. Product: github-resync skips orphan fix(mrb-N) with explicit non-default base and warns on other non-default open PRs.

**Open PR missing MRB/FIX row (FR #8377):** `open_pr_mrb_missing` flags open non-draft non-receipt product PRs with no matching unaccepted/accepted MRB or FIX row (class of #8353: open, green, mergeable PR that never reached the MRB queue). Fixture `JEEVES_OPEN_PR_MRB_MISSING_FIXTURE`. Product: `gitclaim.open_pr_expects_mrb_or_fix_row` / `list_open_prs_missing_mrb`; resync re-adds the MRB on a fresh/force fetch and clears a stale `mrb_done` (FR #1585).

**Ticket closure (FR #6063 / #6064 / #6069 / #6081 / #6391 / #6400 / #6405):** `ticket_closure` reports newly closed issues / merged PRs / unmerged closed PRs on focused repos (`closed[]`). Event-first (FR #6405): BobCallback GIT webhooks call `ingest_github_webhook`; ChairJobs poll backup every `TICKET_CLOSURE_S` default 900s when `JEEVES_TICKET_CLOSURE_FIXTURE` is unset (per-repo `poll_cursors` + pagination, FR #6400). Fixture is tests-only. De-dupe state is `monitor-ticket-closure.json` (`seen` / `pending` / per-repo `poll_cursors` + legacy `poll_cursor` / `last_poll_at` / `last_wake_at` / `pending_count` / `ticket_closure_token_source`). Preferred wake: HTTPS POST to `JEEVES_TICKET_CLOSURE_WAKE_URL` (secret never logged); transport failure stays `pending` with backoff. Legacy `JEEVES_TICKET_CLOSURE_WAKE=1` without URL still uses `wake_bob` / GrokBotApi. Optional Phase-2 wait registry: `ticket-closure-waiting.json`. Never writes queue.json, never `!assign`.

## Depends-on + fr-digest go-gates (BOB-D* / BOB-G*)

Net result (Simon confirm 2026-11-21): three gates — (1) label `hold`, (2) `Depends-on: #N` all CLOSED, (3) `fr-digest` hold/unhold-releases + CI open-children.

| Skill | When |
|---|---|
| `bobiverse-jeeves-agent-depends-on` | Every monitor cycle **once BOB-D offer skip is on tip** (D1/D3+); until then load on demand only |
| `bobiverse-jeeves-agent-fr-digest` | Every cycle **after** depends-on once BOB-G1 is on tip; until then on demand only |

Token-free checks (when landed): `depends_on`, `fr_digest`, `walrus_jeeves_install_ready` via `Invoke-JeevesMonitorCheck.ps1`. Correct skips (`depends-open` / `depends-held`) are **not** starve. D*/G* issues stay on `hold` until Simon unholds; #8754 waits for BOB-D9. Do not edit parked VIS-D* / BOB-D* bodies. FR #9376: when `walrus_jeeves_install_ready` is ok, DryRun `Install-JeevesWalrusWinRm.ps1`; live mutate needs Si `-SiYes` and closed gates — never Ergo. **CAST IRON (FR #9400):** never let a tool-only PR `Closes` #9376 (or any walrus rebuild/install / GateIssues tracker) while Depends-on / GateIssues remain OPEN — use `Refs` / `Toward` until acceptance; reopen if GitHub auto-closed early.

**Ops until BOB-G1 (FR #9344):** unhold alone does not release children whose bodies still list `Depends-on: #<digest>` while live D3 skips open parents --- close the digest (or clear Depends-on) so assign can proceed.


## Auto-start (FR #954)

On launch, **run `.grok/skills/monitor-start/SKILL.md` immediately** (AGENTS.md first-turn rule). Do not wait for a human prompt. Skills are under `.grok\skills` only (no top-level `.\skills`). The Start Menu shortcut / `monitor_prompt` tells the agent to run `monitor-start` now.

## Self-harvest loop (t865u)

After every finding: file/de-dup via intake, then `Invoke-BobiverseHarvest.ps1 -Summary ... -Lesson ...` (+ `-Flush`) so the learning lands back in bobiverse skills. The monitor improves itself through harvest - do not keep private notes. When the learning is a tested deterministic check or chair behaviour, also file the product FR that lands it in the Jeeves token-less service (CAST IRON point 5).

**CAST IRON (FR #9180):** monitor/maintenance harvest of a new TipForm/fleet/chair playbook **owes a skill PR** on `SimonBarnett/bobiverse` whose diff touches `.grok/skills/<book>/SKILL.md` (or cites the covering open `lesson(<book>):` / `harvest/…` tip). Receipt-only intake without that PR leaves the next Sync/MSI build without the lesson — fail-closed. Prefer same-turn `gh` via `Ensure-BobiverseHarvestSkillPr` when authenticated; never push `main` / never auto-merge.

## Architecture (chair is deterministic)

Install root `<ai root>\jeeves`. Chair home `~\.jeeves` (queue, focus, ignore, cmd-trace). Digest home `~\.bobiverse` (`digest.json`, `chair-outbox.txt`). Webhooks: BobCallback `:7700` + IIS `/bob/v1/*`. Ergo is separate under `<ai root>\ergo` - never edit it from here. Details: `bobiverse-jeeves`.

## Queue / focus / assign / seat ledger

| Piece | Where / meaning |
|---|---|
| Unaccepted / accepted / done | Chair queue (crash mirror + live webhook path) |
| Focus | `!focus` / `!unfocus` / strict - sorts `!list` and assign-on-`!bored` |
| Ignore | `!ignore` / `!unignore` - suppress a repo fleet-wide |
| Assign | On `!bored`, Jeeves offers next row in focus order; optional owner/ear `!assign`. **FR #3893:** after DONE ok/missing, chair pushes next eligible job (`offer_after_done`, `offered_via=done`) like GIVEUP/NACK (FR #2811) — do not wait for the seat's next `!bored`. **FR #2803:** seats told `nothing queued` are tracked; when a row is enqueued/becomes offerable, Jeeves pushes `offer_focus_top` to those idle seats (oldest first) without waiting for the next `!bored` (no repeated empty chatter). **FR #7182:** `offer_to_idle_seats` also unions digest `worker_list` idle/ready seats (even with no prior `nothing queued`); empty-offer logs include per-job `skips=` reasons (focus/ledger/pin/...). **Idle-push say False (MRB #2819 / #2821):** `offer_to_idle_seats` / chair-outbox push must treat `say` returning False (`enqueue_chair_fleet_privmsg` OSError/secret skip) or raise as undelivered — keep idle-after-empty and rate-limit; never clear on a silent False. **FR #6521 / #6542:** call `clear_seat_offer` + `clear_seat_hold` before stamping `last_push_at` so sticky `offered_to` does not make FR #3192 `bored_gate` busy and trip `clear_idle_after_empty` on the next tick (FR #4089 parity) |
| Seat ledger | Digest `machines.<id>.workers[]` with state **idle** / **offered** / **doing**; TipForm `working_on` |

Monitor for: empty offer queue while open FRs exist; seats idle with unaccepted work; accepted rows stuck; GIVEUP loops; machine-pin / author-seat blocks leaving work stranded; hand-out empty / `nothing queued` under focus while outside-focus ungated rows remain or `require_machine` shrinks the offerable set (harvest #2243 / #2285).
**giveup_loops (FR #1622):** EXIT 1 only for `giveup_count>=2` on **unaccepted/accepted** rows still offerable to a live seat. Historical `done[]` hotspots are noted and ignored. `require_machine` pins with **zero live seats** on that machine are gated (skipped), not loops.

**Machine pin (FR #587 / #852 / #1550 / #1559 / #3610):** recycle/recompose Jeeves and prune-`queue.json` FRs must stamp `require_machine=walrus` so other fleet seats are not offered chair/Ergo-only deploy work (**ionos deprecated**). **Monitor delay filings** about `ircJeeves` StartPending, or idle seats + ungated offerable (no shop OFFER), are also chair-host ops - title/body cues in `gitclaim.infer_require_machine` must stamp `require_machine=walrus` (legacy PR #1574 ionos cues). When filing those via intake for a repo other than SimonBarnett/bobiverse, put the cue words in the **title** (or use a `needs-walrus` / transitional `needs-ionos` label); bare body prose alone may not pin (FR #1508-safe). **FR #4512:** bobiverse skips title and soft-text cues, including a `needs-ionos:` / `needs-walrus:` title prefix. Pin bobiverse with a `needs-walrus` label (legacy `needs-ionos`) or a body line `require_machine: walrus` (legacy `require_machine: ionos` until pin-retarget FR). **FR #3610:** BobCallback body cues need outage/ops wording (DOWN, 502, Bad Gateway, no LISTEN, restart/recycle) — a bare `:7700` / design-prose mention (Hours webhook FR #3450) must not pin the chair host. If non-walrus seats keep getting those assigns after the cue merge, the live chair needs recompose/recycle - file/de-dup intake.

**Skill/harvest rows (FR #1682):** issues labeled `skill` (or harvest titles) **are** offered as FR promote jobs. Workers must consolidate-by-book (FR #1684), not GIVEUP. Monitor finding is the opposite: skill backlog never offered, or seats GIVEUP-looping on skill offers because stale skills still say SKIP_FR.

## FR / MRB / UAT flow (UAT per repo)

```text
open issue -> FR offer -> ACK -> implement + one PR (Closes) -> DONE
PR open    -> MRB offer (different seat) -> ACK -> hostile review -> merge -> DONE PASS|FAIL
merge PASS -> UAT offer -> gaps = one FR each (no release) | no gaps = docs + release
```

Shop wire (workers in `#{machine}` only): `!bored` -> assign -> `ACK` -> work -> `DONE` / `NACK` / `GIVEUP`. Implementer never self-MRB or self-UAT. Full command table: `docs/jeeves-commands.md` and `bobiverse-jeeves-commands`.

## Digest + worker status

`GET https://bob.ntsa.uk/bob/v1/report` (and local digest home): machine online/lastSeen, workers idle/offered/doing, `working_on`, queue counts. Stale digest / missing worker rows / START tiles stuck -> intake FR after de-dup. **FR #8384:** `stuck_accepted` also EXIT 1 when `accepted>0` and every live shop seat still has empty `working_on`/`work` after 600s. Report only by default; do not `clear_seat_doing`. Keep-queue-moving commands allowed per FR #8827 playbook.

## IRC direction rules

| Role | Nick | Channels |
|---|---|---|
| Chair | `Jeeves` | every ChanServ-registered channel (FR #3836: `#bobiverse`, shops, `#wonderland`, …; silent outside fleet/shop paths) |
| Ear | `bob-<machine>` | own shop + `#bobiverse` (+ `#wonderland` when that FR is live) |
| Worker | `<machine>-<pid>` | own `#{machine}` only - never `#bobiverse` |
| Monitor (you) | session / `monitoring` / ear relay | intake + keep-queue-moving commands (FR #8827) |

- **MRB enqueue when resync blocked (harvest #1927 / product #1811 → #1993):** when `git-claim.lock` / token 403 drops issue+PR queue events while `gh pr list` still works, operator/chair remediation is `enqueue_unaccepted` per open PR plus `clear_seat_doing` for stale busy. Monitor may `!assign` / ear-relay when keep-queue-moving requires it; prefer fixing the lock/token root via intake.

## Reporting (intake first; commands for unblock)

1. Search open issues for the same gap; comment if found.
2. Else `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo <owner/name> -Kind fr|issue -Title "..." -Body "what / where / evidence / fix"`.
3. End session: `Invoke-BobiverseHarvest.ps1 -Summary ... -Lesson ...` then `-Flush`.

## Do not

- Restart BobIrcd or edit Ergo to "fix" chair problems
- Stamp UAT, bump VERSION, merge PRs, invent Ergo PASS, print secrets
- Silent hand-edits of `queue.json`
- `clear_seat_doing` on working seats (keep seats busy; harvest #1967) — report findings; force-orphan only when accepted empty
- Use `!assign` / `!focus` / `!ignore` for product ownership or preference — only to **keep the queue moving**

## Chair home vs digest home (FR #1043 / walrus)

On **walrus** (Ergo/chair host; ionos deprecated), NSSM `ircJeeves` may use `-ChairHome ~/.jeeves` while live `queue.json` / `focus.json` live under `BOB_DIGEST_HOME` (`~/.bobiverse`). Monitor checks resolve ops files via `ops_home`: prefer chair when those files exist there, else fall back to digest home. Pass `-ChairHome` / `--digest-home` explicitly when verifying. `BobCallback` may be a Scheduled Task (or `:7700` listen), not `Get-Service`.

## Harvested lessons (intake)

- When the last open child of an fr-digest batch closes, close the digest issue the same turn (monitor follow-up if ticket-closure did not).
- Session reliability backlog for token-less chair: shared offerable predicate (list=assign=stuck), G1 assign when fr-digest not queued (#9548), auto-close fr-digest on last child, auto-pin tipform host-local after repeated GIVEUPs, stuck refresh, tray_session_missing rule, monitor ops_home on non-walrus, seat-hold clear on ACC nick move.
- CAST IRON FR #9669: needs-walrus NACK → Jeeves agent does walrus (split code FR + walrus FR under Digest; stop wrong-machine re-offer).
- CAST IRON FR #9708: implement-anywhere ⇒ remove every `needs-*` **and** `!unpin` same turn; host-action ⇒ keep label+pin; never `needs-*` + `rm=any`.

## Harvested monitor playbook (skill records #1215-#1456)

- **FR #7182:** digest-idle ready seats get offers in one `offer_to_idle_seats` tick without a prior nothing-queued note; `summarize_empty_offer` logs per-job skips (PR #7210).
- Resolve queue/focus per file: live `queue.json`, `focus.json`, and digest state may live under `BOB_DIGEST_HOME`, not the default chair home. Handle both list and dict-shaped `focus.repos`; an empty strict focus must be a finding when unaccepted work exists.
- `idle_seats` must count rows offerable to at least one live seat, using the same needs-human, cooldown, ledger, and machine-pin gates as `offer_focus_top`; raw unaccepted count alone creates false alarms.
- **Post-DONE harvest_hold is not starve (harvest #1665 / FR #1611):** after `DONE`/`NACK`/`GIVEUP`, BoredEmitter holds `!bored` for `harvest_hold_s` (default **90s**, extends on outbox). `idle_seats` + ungated offerable during that window is expected - do **not** file chair-host `idle+ungated` / true-starve intake. Expect `bored: harvest hold` in `worker.log`, then `!bored`. Suppress orphan-only / historical giveup done[] / harvest_hold / queue_flow-when-idle_seats-ok noise (FR #1622/#1625/#1652). Do not `!assign` during harvest_hold — wait for BoredEmitter.
- **CAST IRON needs-mrb1 ban (harvest #1717 / FR #1526):** never recreate or stamp `needs-mrb1`/`mrb1`. `needs-human` is the real human gate. Queue cache may still show the string until resync - treat as inert (`row_awaits_mrb1` always false).
- **FR #1625 / #1652 false starve:** rows with non-empty `offered_to` still inside `OFFER_TIMEOUT_S` (awaiting ACK) are **not** starve-offerable. Idle seat math uses shop-form `{machine}-{pid}` only (`collect_idle_shop_seats` / `is_starve_idle_nick`): drop `w-mh-*` / `w-io-*` ghosts and `bob-*` ears, and dedupe by canonical nick when digest lists the same seat in `workers` and `worker_list`. `queue_flow` must pass **idle** shop nicks only into `count_offerable_for_live_seats` (never busy/doing); otherwise ungated work offerable to a busy seat plus orphan `w-mh-*` idle_seat_count yields false "true starve". Payload alias: `offerable_for_idle_seats`.
- **"Chair not assigning" / large open GitHub counts (harvest #1581 / #1483):** do **not** treat raw open-issue or open-PR totals as proof the chair is stuck. Most of that backlog is often skill/harvest honesty-box (and `needs-human` / boards). Diagnose in order: (1) `queue_flow` / `ungated_offerable` (and `offerable_for_idle_seats`), (2) whether shop seats are posting `!bored` (idle seats without `!bored` will not get offers - including harvest_hold / BoredEmitter holds), (3) focus/ignore/machine-pin gates, (4) only then chair/outbox faults. Use `!assign` only after that diagnosis shows true starve (FR #8827 playbook).
- **Hand-out empty / `nothing queued` under focus (harvest #2243 / #2285 / #2309):** when shop hand-out / `!bored` is empty or Jeeves replies `nothing queued` while many unaccepted GitHub FRs exist, first count **focus-repo** unaccepted MRB/FR rows, then count how many of those are **offerable to live seats** after `require_machine` / author-seat / needs-human / **self-MRB** / **same-machine `review_blocked`** / **`seat-ledger.json` giveup** gates. File can be full (e.g. 41 unaccepted) while only ~1–2 rows offer to the live shop — that is expected under strict focus + pins, not an empty queue bug. Outside-focus ungated rows do **not** offer under strict focus. Per idle nick, simulate `offer_focus_top` (or read `git-claim bored empty|offered` in `logs\stdout.log`) before filing chair-broken. Operator/chair remediation (monitor reports only): re-enqueue open PRs as MRB into the focused queue; expand focus / `!focus strict off` for OOF backlog; clear digest busy **only** for seats whose PR already merged and that are **not** in `queue.accepted` (CAST IRON keep seats busy #1967). Never treat outside-focus ungated totals or raw unaccepted counts as proof the chair is stuck.
- **Row giveup vs durable ledger (harvest #2309 / #2314):** clearing `needs_human` / `giveup_seats` / `cooldown_until` on the queue row is **not** enough — `ledger_blocks` still reads `~\.bobiverse\seat-ledger.json` `giveup` keys (`owner/repo#N` → seat → roles). To re-feed a starved seat once, clear **both** the row stamps and that seat's ledger giveup entry. **Do not** re-clear after an immediate `ACK` then `GIVEUP` — that restarts the GIVEUP loop; leave the ledger stamp and file/comment the loop instead.
- **Same-machine MRB + sticky no-ACK (harvest #2309):** `review_blocked_for_author` blocks sibling seats on the **same machine** as `implementer_seat` when another live machine exists. A sticky `offered_to` rebroadcast (`OFFER_TIMEOUT_S` refresh) with **no ACK** on that other machine strands the MRB cascade; report the non-ACK seat (recycle/inject) rather than clearing working seats or forcing self-MRB.
- For BobCallback: check scheduled-task state, `:7700` LISTEN, and a fresh `/bob/v1/report` probe together. Task `Ready`/`Running` alone is a false ok when HTTP is dead (`health` must fail). A brief connect failure while LISTEN is present warrants a curl re-probe, not an immediate restart. If the callback is wedged or a lock is empty/stale, remove only the stale lock, restart BobCallback, and verify HTTP 200; never touch BobIrcd/Ergo.
- **Report probe timeout (harvest #2057 / FR #1993):** `/bob/v1/report` under `digest.lock` contention needs **`curl --max-time` / IWR `-TimeoutSec` >= 20**. A 4s max-time false-alarms while LISTEN is up and a longer probe returns 200. `Watch-BobWebhooks.ps1` uses 20s.
- **Skill-offer flood after FR #1682 (harvest #1705/#1706):** large `ungated_offerable` / `idle_seats` EXIT 1 while shop seats are idle is **expected** until consolidate-by-book promote PRs land — do not file a new true-starve FR for skill backlog alone. Still subtract orphan `w-mh-*` / `w-io-*` before calling starve (FR #1625). BobCallback: curl timeout with LISTEN up → re-probe; if report returns 200, leave the single supervised owner alone (never kill Wait-Process parent).
- **BobCallback single-owner heal (harvest #1568 / FR #1767 / #1831):** on HTTP 000 count supervised parents first — if ≥1, do not Start-Process another. Prefer `schtasks /Run /TN BobCallback` when the task exists; only Start-Process supervised when the task is missing. `Start-BobCallbackSupervised` refuses a second parent (exit 0). Never stack task + second supervised; Stop-ScheduledTask first when task is Running with no listener. Exclude current `$PID` when pruning duplicate supervised. Never kill the supervised `Wait-Process` parent (kills `:7700` child). `health` treats Ready/Running without LISTEN as a finding. Full table: `bobiverse-jeeves-troubleshooting` BobCallback heal.
- `digest.lock` owned by the live callback is not foreign-stale. A `doing`/`offered` worker with no accepted row, repeated `bored nak busy`, or no ACK/DONE/GIVEUP beyond the threshold should be **reported** (intake). Do not jump to `clear_seat_doing` on a live working seat.
- **OpenCode stream heartbeats mask hang (FR #8796 / #8795):** `progress_phase=stream` refreshes digest `last_progress` while the linked issue/PR stays untouched. `Test-JeevesMonitorSeatsStuckDoing` / `tools/monitor/seats_stuck_doing.py` keys hang age on accepted/doing clocks (not `last_progress`) and requires a `DONE` (or other substantive close) within 15m; fresh stream heartbeats alone are EXIT 1 (`stream_heartbeat_no_substantive`). De-dup companion seat hang issues; do not clear a live doing seat.
- **CAST IRON keep seats busy (harvest #1967 / operator):** never clear digest busy on seats that are actively working (`doing`/`offered` with a live ACK path, or non-empty `working_on` while the seat process is alive). `idle_seats` and `seats_stuck_doing` are **report-only** by default. Call `clear_seat_doing` / orphan heal **only** for true stale busy: `queue.accepted` empty **and** the seat is a true orphan blocking `!bored` / nak-busy for the whole shop (no live ACK path). Prefer `--force-orphan-busy` (or equivalent explicit force) over casual clears. Related product: FR #1714; false-busy class: harvest #1712 / PR #1823.
- **NAK busy / workers map (harvest #1715):** `bored nak busy` can key off `machines.workers.<pid>.working_on` / running state even when `worker_list` shows idle and queue `accepted` is empty (lost DONE). Clearing **only** `worker_list` is not enough - `clear_orphan` must also idle the `workers` map and machine `working_on`. Product fix tracked as FR #1714. Related false-busy: harvest #1712 (`seats_stuck_doing`).
- Monitor checks observe and diagnose; they do not claim shop jobs as a worker. Keep-queue-moving chair commands are allowed per FR #8827 when ops unblock is needed.
- **Idle-push say False (MRB #2819 / fix #2821 / harvest-lesson #2824):** `offer_to_idle_seats` must treat `say` returning False (`enqueue_chair_fleet_privmsg` OSError/secret skip) or raise as undelivered — keep idle-after-empty and rate-limit; never clear on a silent False. Product tests: `jeeves/tests/test_mrb2819_hostile_chair_outbox_say_false.py`. **FR #6521 / #6542:** call `clear_seat_offer` + `clear_seat_hold` before stamping `last_push_at` so sticky `offered_to` does not make FR #3192 `bored_gate` busy and trip `clear_idle_after_empty` on the next tick (FR #4089 parity). Product: `common/scripts/gitclaim.py`.
- **FR #4373 reopened FR stuck in done (product #4383 / MRB #4384):** when GitHub reopens an issue that already sits in `done`, webhook `issues.reopened` and `resync_from_github` must `pop_done` before append, persist reopen `history` via `_coerce_row`, clear machine pins, and re-enter `unaccepted`. Terminal PASS/MERGED must not block reopen when `open_pulls` is None. Monitor: open GitHub issues that never re-offer after reopen are this class — check `done[]` vs open state before filing empty-queue. Product: `common/scripts/gitclaim.py` `requeue_reopened_issue`; tests `jeeves/tests/test_fr4373_requeue_reopened_issues.py`.
- Bored-latency stall fingerprints must key on machine id (`stall:bored-latency:<machine>`), not ephemeral machine-pid nick; one finding per machine (worst lag); `drop_healed_bored_findings` maps recycleseat nick to that machine key so a heal still suppresses filing (FR #6195 / #6103; product tip #6197).
- Bored-latency heal must count `!recycleseat` by **machine slot** in a rolling window; a new seat PID must not reset the recycle budget or the chair will loop forever (harvest-lesson MRB #6812; keep the product gap here, not in harvest honesty-box).
- **FR #9344 / live D3 before BOB-G1:** unhold of an fr-digest alone leaves children with `Depends-on` OPEN blocked under live D3. Close the digest (or clear Depends-on) to release assign. Prefer outbox file-edit + HTTPS digest when the chair-host shell/WinRM hangs.
- When the last open child of an fr-digest batch closes, close the digest issue the same turn (monitor follow-up if ticket-closure did not).

## Harvested lessons

- **FR #9489 MRB author heal:** interim queue stamp must be `<roster-machine>-<dead-pid>` (e.g. `marchhare-99999`); `ghost-1` dropped on chairs that still require `parse_seat_nick`. Tip reserved `ghost-N` (N>=1) sticks; durable fix is soft `free=` / multi-author exact-seat (FR #9478/#9480 / PR #9482).

- If build-jeeves / tip CI fails while waiting on FR #9376 walrus install: FR the CI failures; do not Install-JeevesWalrusWinRm -SiYes until green.
- **FR #9406 / #9402:** hold-labeled ops FR sticky `offered_to` must not leave a seat `busy (offered FR ...)` — clear sticky offer + drop the held FR from unaccepted (digest gate rows keep queue, lose offer pin) so gate MRB `!assign` can proceed.
- **FR #9400:** never `Closes` ops/gate tracker issues while Depends-on / GateIssues still OPEN — tool-only PRs use `Refs` / `Toward`; reopen if GitHub auto-closed early.
- FR #9376 / PR #9387: document and prefer `Install-JeevesWalrusWinRm.ps1` + check `walrus_jeeves_install_ready` (full playbook in `bobiverse-jeeves-agent-install`). DryRun default; live needs `-SiYes` + closed GateIssues; CredMan `Bobiverse/UpdateFleet`; backup+ROLLBACK; ircJeeves only.
