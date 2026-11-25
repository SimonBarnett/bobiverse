---
name: monitor-start
description: >
  First-turn auto-start for the Jeeves MONITORING agent: run token-free checks
  in a loop, report delays via intake, and may run Jeeves commands to keep the queue moving (FR #8827).
  Use when CWD is jeeves, Start Jeeves Monitor, or AGENTS.md says run monitor-start NOW.
---

# monitor-start (FR #954)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap to the intake webhook in the SAME turn.
> 2. Use `scripts\Report-BobiverseIntakeIssue.ps1 -Repo <owner/name>` with what/where/evidence/fix; never put secrets in a filing. Bobiverse filings use `-Repo SimonBarnett/bobiverse`.
> 3. Before finishing a monitoring session run `Invoke-BobiverseHarvest.ps1 -Summary ... -Lesson ...`, then `-Flush`.
> 4. Monitoring observes and reports; may run Jeeves commands **to keep the queue moving** (FR #8827); never touch Ergo, never merge/UAT/VERSION.
> 5. Prefer deterministic fixes. When tested, FR them into the Jeeves token-less service so what we learn becomes
>    chair behaviour without an LLM (`tools\monitor\`, `jeeves/checks/`, `common/scripts`). Skills are interim.
> 6. **CAST IRON â€” interventions â†’ ircJeeves FR (#9627).** Any keep-queue-moving / heal action owes a product FR the
>    same turn so ircJeeves does it without an LLM. FR #8827 is bridge-only.
> 7. **CAST IRON â€” idle + open work is FAIL (#9644).** `idle_seats` EXIT 1 fingerprint `idle_with_open_work` chair-heals
>    (`push_idle` / `offer_to_idle`); not report-only. Same-turn bridge still owes #9627.
> 8. **CAST IRON â€” multi-FR batch needs Digest parent (#9652).** â‰¥2 related FRs in one batch: `fr-digest` Digest first;

> 9. **CAST IRON --- Jeeves on IRC => webhooks up (#9826).** `Start-Service ircJeeves` / `Start-Jeeves.ps1` => same-turn local report 200 + heal; monitor `webhooks_up_with_chair`.
>    children `Depends-on: #<digest>`; same-turn repair if missing; last-child close closes digest (#9552).

**On start, with no user prompt, run this skill NOW.** Do not wait for Simon. Do not only list skills.

Skills live under **`.grok\skills`** (there is **no** top-level `.\skills` directory).

You are the **MONITORING** agent - not the chair, not a worker. May `!ignore` / `!focus` / `!assign` / `!sweep` / â€¦ **to keep the queue moving**; never touch Ergo; never merge/UAT/VERSION.

## First turn (exact sequence)

1. Read `AGENTS.md` and `.grok\skills\bobiverse-jeeves-monitor\SKILL.md`.
2. **FR #9879 bored-push (before the health loop):** ensure `scripts\Ensure-BoredPushNotify.ps1` (Start-JeevesMonitor already starts it). Start or attach a **monitor tool** on `scripts\watch_bored_push_notify.ps1` (1s inbound-transcript poll) **or** `Get-Content -Wait -Tail 0` on `%LOCALAPPDATA%\Bobiverse\monitor\bored-push-events.log`. On each `READY` / `DONE` / `BORED` line: **dispatch the same turn** (ear-relay `!assign` / `Invoke-JeevesMonitorInterveneAssign` / chair outbox) — do **not** wait for the next health tick. Deduplicate notifier PIDs (Ensure keeps one). A 5-minute scheduler must **not** own assign; health-only.
3. Run every token-free check via `scripts\Invoke-JeevesMonitorCheck.ps1 -Check <name>` (or the matching `Test-JeevesMonitor*.ps1`). Prefer scripts over reasoning.
4. For each **exit 1** finding: de-dup open GitHub issues, then file/comment via `scripts\Report-BobiverseIntakeIssue.ps1 -Repo <owner/name>` (usually `SimonBarnett/bobiverse`).
5. Self-harvest after findings: `Invoke-BobiverseHarvest.ps1 -Summary ... -Lesson ...` then `-Flush`.
6. Sleep on a schedule (about **5-15 minutes**) for **health checks only**, then repeat from step 3. Keep the bored-push monitor tool running for the session; never use that sleep as the assign path.

## Checks (required every cycle)

| Check | Script / name | Why |
|---|---|---|
| Health | `health` | ircJeeves / chair home / webhook surface |
| Chair progress | `chair_progress` | FR #9900: /health ok must not hide stale NSSM stdout.log / cmd-trace (digest write != AppStdout progress) |
| Webhooks up with chair | webhooks_up_with_chair | FR #9826 CAST IRON: ircJeeves Running requires local /bob/v1/report HTTP 200; heal BobCallback / optional W3SVC; never Ergo/BobIrcd |
| Idle seats | `idle_seats` | seats idle while ungated work exists â€” EXIT 1 fingerprint `idle_with_open_work` + chair heal / ear-relay (FR #9644 / #9461); never `clear_seat_doing` on live busy seats |
| Queue flow | `queue_flow` | empty offer queue, missing pull URLs, unoffered open issues |
| Focus present | `focus_present` | bobiverse missing from strict focus while unaccepted work exists (FR #1019) |
| Focus redundant items | `focus_redundant_items` | `focus.items` keys under an already-focused repo (FR #1520 per-repo policy) |
| Seats stuck doing | `seats_stuck_doing` | doing/offered stale busy, nak-busy loops, PermissionError log counts (FR #1019). **Report only** unless explicit `--force-orphan-busy` and `accepted` empty (harvest #1967 keep seats busy) |
| OpenCode seats | `opencode_seats` | live GET `/bob/v1/report` flamingo `kind=opencode` stuck age / model_mismatch / week-exhausted while busy (FR #8583). **Report only** â€” digest alone misses remote OpenCode |
| Stale digest | `stale_digest` | digest not updating |
| Orphan last-good workers | `workers_last_good_orphan` | `workers_stale` + empty live workers + non-empty `workers_last_good` (FR #9145; token-free; local digest only) |
| GIVEUP loops | `giveup_loops` | same row repeatedly GIVEUP |
| Stuck accepted | `stuck_accepted` | accepted rows not progressing |
| Auto-feed | `auto_feed` | BobAutoFeed / auto-offer liveness |
| Auto-focus | `auto_focus` | auto-focus / focus.json sanity |
| Skill promote backlog | `skill_promote_backlog` | open skill/harvest receipts with zero `harvest/*` promote PR (FR #1729 / post-#1682) |
| Intake allowlist | `intake_allowlist` | live POST /bob/v1/intake 403 repo_not_allowed vs DEFAULT_ALLOW_REPOS (FR #3117; Sync/compose on **walrus**; ionos deprecated) |
| Github resync focus | `github_resync_focus` | focus.repos set but queue/discover starve (FR #3146; resync-repos.txt / !resync) |
| Open PR stale base | `open_pr_stale_base` | open PRs whose base.ref is not main/master (FR #8333; fixture JEEVES_OPEN_PR_STALE_BASE_FIXTURE) |
| Open PR missing MRB/FIX | `open_pr_mrb_missing` | open non-draft non-receipt PRs with no MRB/FIX queue row (FR #8377; fixture JEEVES_OPEN_PR_MRB_MISSING_FIXTURE) |
| Ticket closure | `ticket_closure` | newly closed issues/PRs on focused repos (FR #6063; report only) |
| Depends-on open | `depends_on` | offered or accepted row whose `Depends-on:` ref is still OPEN (FR #8848 / BOB-D3). Soft-ok when the product skip is not on tip or no Depends-on rows. Distinct from hold and from `fr_digest` (see `bobiverse-jeeves-agent-depends-on`) |
| FR digest hold | `fr_digest` | offered or accepted child whose Depends-on row still has labels `fr-digest` and `hold` (FR #8849 / BOB-G1). Run after `depends_on`. Soft-ok when BOB-G is not on tip |
| Walrus install gate | `walrus_jeeves_install_ready` | FR #9376 Depends-on / Plan-agent gate issues CLOSED before DryRun / `-SiYes` WinRM hotpatch (`Install-JeevesWalrusWinRm.ps1`). Fixture `JEEVES_WALRUS_INSTALL_GATE_FIXTURE`. Does not open WinRM. |
| Redqueen bob-tray install | `redqueen_bob_tray_install_ready` | FR #9419 live `bob-tray.exe` vs green `build-bob-tray.yml` / fixture drift before DryRun / `-Install` local hotpatch (`Install-BobTrayRedqueen.ps1`). Fixture `BOB_TRAY_REDQUEEN_INSTALL_FIXTURE`. Does not mutate the tray. |
| MRB same-machine starve | `mrb_same_machine_starve` | FR #9478 idle same-machine siblings blocked from offerable MRBs with no free cross-machine reviewer (hard #9401 / free= omit). Prefer cross-machine `!assign`; tip soft free-other-machine; install waits on #9475/#9476. |
| Models PUT forward | `models_put_forward` | FR #9585 Weights Save: public `PUT /bob/v1/models` must reach bobcallback (not IIS HTML 404). Remediation: re-run `Install-BobWebhooks.ps1` on walrus so `BobModelsWebhook` uses `^(GET\|HEAD\|POST\|PUT)$` (FR #9273). Fixture `JEEVES_MODELS_PUT_FORWARD_FIXTURE`. |

Exit codes: **0** ok, **1** finding, **2** error. One JSON line on stdout.

After the script checks, if BOB-D / BOB-G product is on tip, open and follow `.grok/skills/bobiverse-jeeves-agent-depends-on/SKILL.md` then `.grok/skills/bobiverse-jeeves-agent-fr-digest/SKILL.md` (go-gate after Depends-on). Until those ship, skip the two checks (missing check name = soft skip / do not EXIT 2).

## Report format (intake)

Title: short delay symptom. Body: what / where / evidence (script JSON / exit) / fix. De-dup first. Never print secrets.


## Non-chair hosts (FR #8579 / #8866 / #9557)

Monitor may run on a worker box (e.g. redqueen) that has no local `~/.jeeves/queue.json`
and no ircJeeves/BobCallback services. Those local probes **soft-pass** when live
`GET https://bob.ntsa.uk/bob/v1/report` is fresh (`ts` within 15m) and annotate
`non_chair_overlay` in the JSON. Prefer the walrus chair host for local service truth.
Start-JeevesMonitor warns when the local queue file is absent; it does not refuse.

**FR #9557:** an empty or stale local ops home (present `queue.json` with zero rows,
or digest that misses live ACC/doing seats) must prefer the live report for
`idle_seats` seat paint, or soft-skip EXIT 0 with `skipped=stale_local_home` when
the report is unusable â€” never EXIT 1 false starve from Admin `~/.jeeves`. Optional
env `JEEVES_MONITOR_DIGEST_HOME` (UNC/shared chair digest) overrides seat-local
`BOB_DIGEST_HOME` for token-free checks.

## Do not

- Wait for a human prompt before the first check cycle
- Touch Ergo / merge / stamp UAT / bump VERSION / claim shop jobs as a worker
- Conclude "no skills" because `.\skills` is missing - use `.grok\skills`

Keep-queue-moving commands (`!ignore` / `!focus` / `!assign` / `!sweep`) are allowed per FR #8827 â€” see `bobiverse-jeeves-monitor` playbook.

- Intake URL: https://bob.ntsa.uk/bob/v1/intake
- Explicit Bobiverse filing target: -Repo SimonBarnett/bobiverse
