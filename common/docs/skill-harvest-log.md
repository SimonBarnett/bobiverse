# Skill harvest log

## 2026-10-05 — MRB #2426 FR DONE PASS strip + MRB FAIL url

| Field | Value |
|-------|-------|
| Lesson | FR DONE must be url-only (no PASS/FAIL); shop_listen strips mistaken PASS/FAIL on FR and keeps the PR url so ACC clears. MRB/UAT FAIL with a URL as the next token must set result=FAIL and url=<url>, not glue the URL into result. |
| Evidence | FR #2419 / PR #2426; fix/hostile MRB #2426 |
| Refs | SimonBarnett/bobiverse#2419 SimonBarnett/bobiverse#2426 |

## 2026-10-05 — MRB #2416 crash hook spool on dedupe-comment fail

| Field | Value |
|-------|-------|
| Lesson | Unhandled exe crashes must file or spool: when an open crash-sig twin exists but gh comment fails, spool under LOCALAPPDATA/Bobiverse/crash-spool (or BOB_CRASH_SPOOL) and flush on next install — never drop the report. |
| Evidence | FR #2411 / PR #2416; fix PR #2422; hostile MRB #2416 docs |
| Refs | SimonBarnett/bobiverse#2411 SimonBarnett/bobiverse#2416 SimonBarnett/bobiverse#2422 |

## 2026-10-05 — MRB #2415 jeeves maintenance agent after heal

| Field | Value |
|-------|-------|
| Lesson | After jeeves.exe --heal still exits non-zero, start ONE bob-worker --mode maintenance in first fixed-disk \\ai\\jeeves (or BOB_AI_ROOT); single-instance lock + 30m cooldown; log every spawn/skip; dry-run logs would_spawn without lock/cooldown stamp; dead lock PID must clear before re-spawn; opt out --no-maintenance-agent. |
| Evidence | FR #2412 / PR #2415; hostile MRB #2415 docs follow-up |
| Refs | SimonBarnett/bobiverse#2412 SimonBarnett/bobiverse#2415 |


## 2026-10-05 — MRB #2410 harvest-log C0 strip

| Field | Value |
|-------|-------|
| Lesson | skill-harvest-log.md must stay free of C0 controls (especially backspace) that eat the leading letter on Books book ids; gate with no-C0 + book-name lint tests and drop duplicate consecutive Books lines after repair. |
| Evidence | FR #2408 / PR #2410; hostile MRB #2410 docs follow-up |
| Refs | SimonBarnett/bobiverse#2408 SimonBarnett/bobiverse#2410 |


## 2026-10-05 — skill #2406 PyInstaller UAT static check

| Field | Value |
|-------|-------|
| Lesson | One-file PyInstaller exes false-fail outer-PE Select-String for free-rx/_OUT_FREE_RX; extract bob_worker.pyc or run BoredEmitter free-rx tests / outbox GIVEUP. Literal reason=free is composed at runtime. |
| Evidence | FR #232 ionos MSI verify; skill promote #2406 |
| Refs | SimonBarnett/bobiverse#2406 SimonBarnett/bobiverse#232 |


## 2026-10-05 — MRB #2403 frozen airc.exe Sync/Update

| Field | Value |
|-------|-------|
| Lesson | Hostile tests for kick_frozen_service_start_hooks must assert airc\\airc.exe install-root resolution, BOBIVERSE_NO_UPDATE skip, and Sync-then-Update arg parity with Start-AircConsole -ServiceMode — string-contains alone is not enough. |
| Evidence | MRB #2403 on PR #2403; follow-up docs PR |
| Refs | SimonBarnett/bobiverse#2403 SimonBarnett/bobiverse#2401 |


## 2026-10-05 — MRB #2386 ack-miss nothing-queued clear

| Field | Value |
|-------|-------|
| Lesson | AssignAckMiss.note_inject must parse FROM body before is_nothing_queued (full FROM lines never match); clear on idle so a withdrawn assign does not remind/recycle. |
| Evidence | Hostile MRB #2386 on PR #2386; tip left elif is_nothing_queued: pass |
| Refs | SimonBarnett/bobiverse#2386 SimonBarnett/bobiverse#2383 |


## 2026-10-05 - Merged fix(mrb-N) must not re-offer as MRB (MRB #2376 / FR #2375)

| Lesson | Fix |
|--------|-----|
| After FAIL+fix, merged self-authored `fix(mrb-N)` stayed ACC / unaccepted and was re-offered (author GIVEUP self-MRB) | `mrb_row_offerable` rejects fix titles; closed+merged webhook moves ACC→done `MERGED` and stamps `mrb_done` |
## 2026-10-05 - !bored stale busy after lost DONE (FR #2369 / MRB #2371+#2373)

| Lesson | Fix |
|--------|-----|
| Digest `doing` after lost DONE made `bored_gate` nak-busy forever (6h fleet stall) | `release_stale_busy` on busy: drop ACC older than `BUSY_STALE_S` (or absent), clear digest doing, stamp `STALE_BUSY`; recent ACC still busy |
## 2026-10-05 - Airc NSSM DisplayName / Default home (FR #2355)

| Lesson | Fix |
|--------|-----|
| Live DisplayName stayed literal #{machine}; AppParameters ConsoleHome under Users\Default survived upgrades via FR #1552 identity restore | Expand DisplayName with MachineId (FR #1546); remap Default ConsoleHome to <install>\home after prior-identity restore; identity-reconcile must not restore Default homes |
## 2026-10-05 - Scratch --home must not merge agentic-irc (MRB #2357 / FR #2350)

| Lesson | Fix |
|--------|-----|
| bob-ear `--home` scratch under `%TEMP%` still merged `~/.agentic-irc-bobiverse` (queue/secrets/*.legacy) | `home_allows_legacy_migrate` gates auto-migrate to canonical basenames; opt-in `BOB_MIGRATE_LEGACY`; opt-out `BOB_HOME_NO_MIGRATE`; `old_homes=` still intentional |
## 2026-10-05 - Release must ship airc+jeeves MSI too (FR #2354)

| Lesson | Fix |
|--------|-----|
| VERSION bump / UAT release uploaded only `bob-<ver>.msi`; airc Check returned `no-matching-asset` while InstallRoot VERSION already at the tag | Always `Pack-BobiverseRelease -Product all` and upload each product `.msi` + `.msi.sha256`; gate with `Assert-BobiverseReleaseAssets.ps1` before DONE |
## 2026-10-05 - Queue body[:500] must keep require_machine pins (MRB #2319 / FR #2312)

| Lesson | Fix |
|--------|-----|
| Enqueue stored `body[:500]`, dropping a trailing dedicated `require_machine:` / `=` pin (e.g. #1714 past char 500), so `require_machine` stayed null and non-matching seats got the offer | `gitclaim._body_for_queue` appends missing pin lines after the truncate window; hard-pin `bobiverse#1714` -> ionos; stamp on append. Hostile: equals-form, blank-line, row-only refresh, ce-priority pin |
## 2026-10-04 - Skills-only promote from worktree (harvest #2318)

| Lesson | Fix |
|--------|-----|
| Promote Jeeves maintenance skills while install main tip is dirty with local gitclaim/callback experiments | Worktree from `origin/main`; skills/docs only; leave dirty product scripts uncommitted on the install tip. Sibling playbook PR #2317 |

Books: harvest-agent-skills.

## 2026-10-04 - Jeeves silent to operator / unverified WHOIS (harvest #2179)

| Lesson | Fix |
|--------|-----|
| Operator sees Jeeves "not responding" while shop still assigns | Check `chan-privs` for unverified WHOIS on the operator nick; `Restart-Service ircJeeves` to refresh; do not restart BobIrcd; leave worker seats alone |

Books: bobiverse-jeeves-troubleshooting.

## 2026-10-04 - Harvest promote MRB merge order (harvest #2296)

| Lesson | Fix |
|--------|-----|
| MRB of a harvest promote: merge skill PR first, then one `docs/mrb-N` hostile-test PR from new main; verify `Closes` closed the skill issue before DONE PASS | Documented in bobiverse-bob-job-mrb. Example: #2289 then docs #2295 |

Books: bobiverse-bob-job-mrb.

## 2026-10-04 - nothing queued = focus + require_machine gate (harvest #2285)

| Lesson | Fix |
|--------|-----|
| Jeeves `nothing queued` / empty hand-out while dozens of unaccepted FRs exist | Count focus-repo unaccepted vs offerable-to-live-seats after `require_machine` / author-seat gates; file often full, offer set tiny under strict focus. Extends #2243. Documented in bobiverse-jeeves-monitor + bob-job-irc |

Books: bobiverse-jeeves-monitor, bobiverse-bob-job-irc.

## 2026-10-04 - Ear channel_list DIGEST_ID_FOLD (harvest #2280 / MRB #2262 / #2279)

| Lesson | Fix |
|--------|-----|
| Ear channel_list helpers must fold DIGEST_ID_FOLD aliases (ionos->win-mpre8vi4u6u, dev1->ce-priority-dev1) so Start-Bob / tests never target #ionos | inbound_transcript.canonical_machine_id via bobreport.fold_machine_id; FLEET_EAR_MACHINES uses canonical ids. Product fix PR #2279 |

Books: bobiverse-bob, bob/docs/bob-ear.md, inbound_transcript.

## 2026-10-04 - CONFLICTING fix PR re-merge before REST (harvest #2274)

| Lesson | Fix |
|--------|-----|
| Harvest/MRB fix PRs CONFLICTING on `skill-harvest-log.md`: one fix PR from `origin/main` keep-both; if that fix PR itself conflicts with newer main before merge, merge `origin/main` keep-both into the fix tip **again** before REST/`gh pr merge` | Documented in `bobiverse-bob-job-mrb` + `harvest-agent-skills`. Example: MRB #2241 â†’ #2272 (`64e09e1` keep-both then merge) |

Books: bobiverse-bob-job-mrb, harvest-agent-skills.

## 2026-10-04 - twin-DONE harvest loop skip (FR #2237)

| Lesson | Fix |
|--------|-----|
| Harvest of twin/already-fixed DONE sessions re-files skill twins that Jeeves re-offers as FR (nested stack) | `Invoke-BobiverseHarvest` skips twin-DONE-only summaries (like FR #936 GIVEUP loop); harvest skill documents skip |

## 2026-10-04 - jeeves.exe chair+HTTP foundation (FR #1993)

| Lesson | Fix |
|--------|-----|
| Dual BobCallback/chair processes fight git-claim.lock / digest.lock | WP0 spec `jeeves/docs/jeeves-exe-self-heal.md`; WP1 `jeeves_main` + in-proc RLock + instance mutex; append WP2+ on living #1993 with Refs only (never Closes / never twin WPs) |

Books: `jeeves_main`, `jeeves_locks`, bobiverse-jeeves. Living FR: #1993.


## 2026-10-04 - Hand-out empty under focus (harvest #2243)

| Lesson | Fix |
|--------|-----|
| !bored / hand-out empty while many ungated FRs exist outside focus | Count focus-repo unaccepted MRB/FR first; outside-focus ungated rows do not offer under strict focus; re-enqueue open PRs as MRB; clear digest busy only for merged PRs not in accepted (keep seats busy #1967) |

Books: `bobiverse-jeeves-monitor`.


## 2026-10-04 - Living ionos architecture FR (harvest #1989 / FR #1993)

| Lesson | Fix |
|--------|-----|
| Approved chair+HTTP / self-test plans for ionos | One bobiverse FR with require_machine: ionos; append WP evidence to the same body; do not twin FRs |

Books: bobiverse-jeeves. Living FR: #1993.

## 2026-10-04 - BobCallback report probe >=20s (harvest #2057 / FR #1993)

| Lesson | Fix |
|--------|-----|
| curl/IWR max-time 4s false-alarms under digest.lock while LISTEN+longer probe is 200 | Use --max-time / -TimeoutSec >= 20 for /bob/v1/report; Watch-BobWebhooks.ps1 = 20s |

Books: bobiverse-jeeves-monitor, bobiverse-jeeves-troubleshooting. Living architecture FR #1993.

## 2026-10-04 - Intake linked_existing_pr (FR #1812 / harvest #2013)

| Lesson | Fix |
|--------|-----|
| Harvest/skill intake with a pull URL must not open a second skill issue | linked_existing_pr + draft_pr_error logging; skip_fr harvest_pr_summary for via-intake+skill PR-opened receipts. Product PR #2012 |

Books: harvest, harvest-agent-skills.

## 2026-10-04 - living FR re-file when intake is harvest-only (harvest #2001)

| Lesson | Fix |
|--------|-----|
| If intake FR vanishes into harvest-only receipts, re-file with gh issue create --label feature-request and treat that number as the living FR | Documented in harvest + harvest-agent-skills. Example living FR: #1993 jeeves.exe. |

## 2026-10-04 - Quiet MSI Node soft-fail under SYSTEM (FR #1825 / harvest #2020)

| Lesson | Fix |
|--------|-----|
| Per-user WindowsApps winget fails under LocalSystem; node hard-fail -> msiexec 1603 | Prefer pinned nodejs.org x64 MSI (ALLUSERS=1); soft-fail git/python/node with WARN; product PR #2019 |

Books: bobiverse-fleet-ops, common/docs/post-install.md.

## 2026-10-04 - intake/BobCallback/ARR 502 ops pin ionos (FR #1899)

| Lesson | Fix / book |
|---|---|
| Chair offered intake 502 / BobCallback / ARR reverse-proxy FRs to flamingo | Stamp require_machine=ionos from title/body cues (intake+502, BobCallback+:7700, ARR/reverse-proxy+/bob/v1) |

Books: `common/scripts/gitclaim.py`. Related body-line pin: FR #1824.
Pre-bobiverse harvest diaries (agentic_build / agentic_irc / bob-design-uat) remain under `docs/archive/*/docs/skill-harvest-log.md` for provenance. Do not treat those paths or product names as live. This file is the live bobiverse index (FR #806).


## 2026-10-04 - Keep seats busy / no casual clear_seat_doing (harvest #1967)

| Lesson | Fix |
|--------|-----|
| Operator: stop clearing digest busy on working seats; only clear true stale busy (accepted empty + orphan blocking !bored) | CAST IRON in bobiverse-jeeves-monitor + monitor-start report-only defaults; seats_stuck_doing remediation requires --force-orphan-busy |

## 2026-10-04 - seats_stuck_doing false busy after DONE (harvest #1712)

| Lesson | Fix / book |
|---|---|
| digest doing + accepted empty after DONE | Stale working_on; do not !assign or kill seat |
| Remediation | Report-only by default (see #1967 keep seats busy); force-orphan clear only when accepted empty |

Books: `bobiverse-jeeves-monitor`, TipForm note in `bobiverse-bob`. Twin #1713.

## 2026-10-04 - skill-harvest-log rebase keep-both (FR #1757 / #1750)

| Lesson | Fix |
|--------|-----|
| Harvest PRs that touch skill-harvest-log.md must rebase onto main before MRB merge when parallel promotes landed; one fix PR must keep both dated sections | Documented in harvest-agent-skills + bobiverse-bob-job-mrb. Evidence: MRB #1741 FAIL-fixed via #1750 (TipForm + ionos-pin sections both kept). |

## 2026-10-04 - job-uat drop needs-mrb1 GIVEUP gate (FR #1830)

| Lesson | Fix |
|--------|-----|
| Harvested UAT gates must not teach ACK/GIVEUP wait-for-needs-mrb1 | bobiverse-bob-job-uat: CAST IRON ban; human gate is needs-human only (with #1717/#1526). |

## 2026-10-04 - Harvest intake links existing PR (FR #1812)

| Lesson | Fix |
|--------|-----|
| kind=harvest/skill with no files but body/title cites pull/N filed a second skill issue (filed_issue_fallback) and queued duplicate FR work | intake links existing PR (`linked_existing_pr`); log draft_pr_error; skip_fr `harvest_pr_summary` for via-intake+skill PR-opened receipts; harvest `-ExistingPrUrl` |
## 2026-10-04 - Body-line require_machine pin (FR #1824 / #1843)

| Lesson | Fix |
|--------|-----|
| Dedicated body line `require_machine: ionos` was ignored (FR #1508 blocked inline evidence); flamingo got ionos-only offers | Honor MULTILINE `^require_machine[:=]` pin lines in body cues; keep inline evidence unpinned |

## 2026-10-04 - Fix-PR race after DONE PASS (harvest #1981 / MRB #1847)

| Lesson | Fix |
|--------|-----|
| Fix PR can race CONFLICTING and close unmerged after DONE PASS | Immediately open a land PR from the known-good tip onto current main; merge; verify origin/main has the lesson before ending |

Books: bobiverse-bob-job-mrb. Example land: PR #1979 after #1977 race.

## 2026-10-04 - BobCallback multi-supervisor refuse (FR #1767 / #1831)

| Lesson | Fix |
|--------|-----|
| Two Start-BobCallbackSupervised parents fight digest.lock â†’ public INTAKE 502 | Wrapper refuses second parent; Start-Jeeves/Register count parents and prefer schtasks /Run; health treats Ready without LISTEN as finding |

## 2026-10-04 - Honor require_machine stamps with ACK/GIVEUP (harvest #1688)

| Lesson | Fix |
|--------|-----|
| Chair offered require_machine=ionos work to marchhare/flamingo; seats must not attempt it | ACK then GIVEUP with require_machine=<mid> in the reason; file intake for wrong-shop offers (class of #1687). Documented in bob-job-fr + bob-job-irc. |

## 2026-10-04 - Agent-folder path rewrite lookbehind + Pack BOM (FR #1704 / harvest #1711)

| Lesson | Fix |
|--------|-----|
| Sync-BobiverseAgentFolders must regex-rewrite only bare .\scripts\ ((?<!\.) lookbehind); plain Replace triples dots in ..\scripts\. Double-encoded UTF-8 BOM makes WinPS 5.1 refuse Pack-BobiverseRelease.ps1 | Documented in `bobiverse-fleet-ops`. Product: PR #1709 / nits #1710 |

## 2026-10-04 - Never Closes skill harvest from unrelated PR (harvest #1674)

| Lesson | Fix |
|--------|-----|
| Never Closes a label:skill harvest issue from an unrelated docs/vendor PR; use Refs and close the harvest record separately when lessons are already on main | Documented in job-fr, job-mrb, harvest-agent-skills. MRB #1660 FAIL-fixed via #1670 |
## 2026-10-04 - tray SkipTidy autostart + ACCEPTABLE partial-FR drift (harvest #1663)

| Lesson | Fix / book |
|---|---|
| ONLOGON/shortcuts kill seats | Autostart uses -ForceNew -SkipTidy; TipForm Restart still tidies (FR #1636 / PR #1645) |
| Partial FR with follow-ups | ACCEPTABLE drift for MRB PASS when follow-up issues are explicit |

Books: `bobiverse-bob`, troubleshooting, `bobiverse-bob-job-mrb`. Twin #1681 (watchdog SkipTidy).
## 2026-10-04 - Post-DONE harvest_hold is not starve (harvest #1665)

| Lesson | Fix |
|--------|-----|
| idle+ungated during BoredEmitter harvest_hold (~90s after DONE) is not true starve; expect !bored after hold; suppress orphan/giveup/queue_flow false alarms | Documented in `bobiverse-jeeves-monitor` + `bobiverse-bob-worker`. Related false-starve gates: FR #1622/#1625/#1652 / PR #1654 |

## 2026-10-04 - Conflict-marker CAST IRON before merge (FR #1634 / harvest #1657)

| Lesson | Fix |
|--------|-----|
| Run check_conflict_markers.py before every gh pr merge; merge origin/main into behind FR branches first; close harvest twins as not planned; Duplicates closed body nit OK without a fix PR when tests green | Documented in `bobiverse-bob-job-mrb` + FR pointer. Product/CI: PR #1640. Overlaps harvest #1647 behind-main/nits notes. |

## 2026-10-04 - MRB behind-main + body/docs nits (harvest #1647)

| Lesson | Fix / book |
|---|---|
| PR head behind main | Merge origin/main into FR branch before gh pr merge |
| Additive hostile tests | Land on docs/mrb-N, never push onto PR under review |
| Body/docs-only nits + green tests | PASS without separate fix PR; close harvest twins as not planned |

Book: `bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md`.

## 2026-10-04 - Get-Asset fail-closed + Airc Fleet ServiceMode (FR #1545 / harvest #1590)

| Lesson | Fix |
|--------|-----|
| Never splat via PowerShell automatic $args in wrappers; Get-Asset must fail-closed (timeout/curl) so Apply can Set-Failure download-failed and release the mutex | Documented in `bobiverse-fleet-ops` + `bobiverse-airc`. Product: PR #1561 / nits #1588 |

## 2026-10-04 - Skill diff orphan continuation FAIL (harvest #1616)

| Lesson | Fix |
|--------|-----|
| Hostile-read skill diffs line-by-line: a mid-bullet insert that leaves orphan continuation text is an MRB FAIL even when code is green | Documented in bobiverse-bob-job-mrb. Product restore: PR #1610 after #1608 |

## 2026-10-04 - CONFLICTING/superseded MRB FAIL (harvest #1609)

| Lesson | Fix |
|--------|-----|
| MRB of CONFLICTING PR when twin FR already closed by another merge: FAIL board, close the duplicate PR, DONE FAIL; do not force-merge. CONFLICTING with open acceptance still uses one fix/rebase PR. | Documented in bobiverse-bob-job-mrb + troubleshooting row in bobiverse-bob-job-irc. Absorbs #1756/#1736/#1730 twins. |

## 2026-10-04 - FR #1546 / PR #1560 Airc ReplyFile + console logs (harvest #1567)

| Lesson | Fix |
|--------|-----|
| `Invoke-AircRemote -ReplyFile` needs ear capture of `*_console` Query lines to `home/airc-replies.jsonl` plus helper poll until DONE; NSSM AppStdout under install logs with timestamps and keepalive rate-limit | Promoted into `airc/.grok/skills/bobiverse-airc`, `bobiverse-airc-troubleshooting`, and `bob/.grok/skills/bobiverse-bob-commands` (code already on main via PR #1560) |

## 2026-10-04 - StrictMode @() before .Count (FR #1664 / harvest #1689)

| Lesson | Fix |
|--------|-----|
| PowerShell StrictMode: Sort-Object/Where-Object of one item is a scalar - wrap with @() before .Count; leave separate FreeGB capacity FRs open | Documented in `bobiverse-fleet-ops` + `bobiverse-bob-job-fr`. Product: PR #1672. Related soft-cap conflict playbook: harvest #1694 |
## 2026-10-04 - Never stamp needs-mrb1 (harvest #1717 / FR #1526)

| Lesson | Fix |
|--------|-----|
| CAST IRON: do not create, stamp, or apply needs-mrb1/mrb1. needs-human is the real human gate. Leftover label on the repo is inert for offers | Updated harvest + job-fr + jeeves-monitor. Product already on main via PR #1526 |

## 2026-10-04 - Self-MRB GIVEUP wire (harvest #1603)

| Lesson | Fix |
|--------|-----|
| Never self-MRB a PR this seat opened; GIVEUP with self-MRB reason so another seat can hostile-review (and rebase if DIRTY) | Documented wire in bobiverse-bob-job-mrb + bobiverse-bob-job-irc. NACK only if spotted before ACK/work. |

## 2026-10-04 - TipForm stale worker lines (FR #1553 / harvest #1562)

| Lesson | Fix |
|--------|-----|
| TipForm looks stuck while seats are busy: BobCallback flaps + Get-BobTrayHover hung WinForms poll + lagging worker_list | Sync workers from digest/report on a non-UI timer; never block refresh on hover; roll working_on from worker_list; heal callback with Start-BobCallbackSupervised. Documented in bobiverse-bob + troubleshooting. Product: PR #1576 / #1495 / #1555 |

## 2026-10-04 - Monitor StartPending/idle+ungated -> require_machine=ionos (FR #1550 / harvest #1580)

| Lesson | Fix |
|--------|-----|
| Monitor filings about ircJeeves StartPending or idle seats + ungated offerable were offered to marchhare | gitclaim title/body cues stamp require_machine=ionos (PR #1574). Document in jeeves-monitor + bob-job-fr; put cue words in intake titles. |

## 2026-10-04 - Skill-offer idle_seats expected + callback timeout recover (harvest #1705)

| Lesson | Fix |
|--------|-----|
| BobCallback curl timeout with LISTEN can recover 200 without restart; skill flood in ungated_offerable after FR #1682 is expected until consolidate PRs land; exclude w-mh-* from idle_seats | Folded into jeeves-monitor + troubleshooting (with #1568 heal cluster). |
## 2026-10-04 - MRB #1696 docs: skill offers are promote FRs (not SKIP_FR/GIVEUP)

| Lesson | Fix |
|--------|-----|
| Stale skills still said chair SKIP_FR / GIVEUP if offered skill intakes, causing live ACK/GIVEUP loops after FR #1682 hotpatch | Rewrite job-fr, bob-worker, harvest, harvest-agent-skills, jeeves-commands, jeeves-monitor: offers are intentional promote FRs; consolidate-by-book; do not GIVEUP |
## 2026-10-04 - FR #1684 skill consolidate -> promote PR

| Lesson | Fix |
|--------|-----|
| Open `label:skill` / `harvest:` receipts must become promote PRs (FR #1682 offers them; do not GIVEUP) | Worker consolidates by owner skill book, closes duplicate receipts, opens one `harvest/...` PR; MRB merges. Documented in `harvest-agent-skills`, `harvest`, `bobiverse-bob-worker`, `bobiverse-bob-job-fr` |

## 2026-10-03 - FR #806 archive-richer hand-merge

| Lesson | Fix |
|--------|-----|
| Ten "archive richer" docs flagged in ARCHIVED_REPOS after #802 | Merged useful honesty-box / chair / design-uat / Ergo describe-only content into live files; left verbatim archive copies untouched; dropped stale archived-repo homes and old pack tool names |

## 2026-09-29 â€” WIN-MPRE8VI4U6U airc/bob/jeeves cutover

Harvested into `.grok/skills/bobiverse-{jeeves,bob,airc}` + `docs/post-install.md` + install scripts:

| Lesson | Fix |
|--------|-----|
| `Start-Jeeves` / `--channel` + PowerShell `#` comment | `irc_agent.py`: `--channel` optional when `--chair` |
| MSI LocalSystem ChairHome â†’ `C:\Users\Default\â€¦` | `Install-Jeeves`: prefer Admin chair or `home-jeeves` |
| Legacy `BobJeeves` + `ircJeeves` both Running | `Disable-BobiverseLegacyBobJeeves` on install |
| `CryptUnprotectData` with LocalSystem + Admin identity | post-install + skill: ObjectName / park identity interim |
| Crash-loop stderr flooding airc console | NSSM AppStdout/AppStderr â†’ `C:\ai\jeeves\logs\` |
| Leftover `AircConsole` beside bobiverse `Airc` | `Install-Airc` **removes** `AircConsole` from SCM |
| Legacy `BobJeeves` left Stopped/Disabled in services.msc | `Remove-BobiverseLegacyService` deletes SCM entry (tree kept) |
| Remote ops via bob outbox PRIVMSG to `*_console` | bobiverse-bob / bobiverse-airc skills |
| Duplicate MSI tray vs Watch-BobTray | already 0.1.5 (#14); documented again |

VERSION â†’ **0.1.6** (pack when shipping).

## 2026-09-30 â€” DEV1 TipForm companion durable start

Harvested into .grok/skills/bobiverse-bob + docs/post-install.md + tray launcher:

| Lesson | Fix |
|--------|-----|
| Tray logs `tray up` then dies when started from Grok agent shell | `Start-BobFleetTray` uses WMI `Win32_Process.Create` (job-object breakaway) |
| Broad seat-wrapper `match Watch-BobTray` kills diagnosing shells | Kill filter requires `-File â€¦Watch-BobTray.ps1` / `_Watch-BobTray-*.ps1` |
| Product is service + companion, not BobFleet task | HKCU `Run\BobiverseTray`; disable `BobFleet-<id>` |
| LocalSystem skipped update-check | `Start-Bob` no longer forces `BOBIVERSE_NO_UPDATE`; `Check-BobiverseUpdate` resolves `gh` + Releases API |
| TipForm recycle JIT `PipelineStoppedException` | CatchException before Controls; swallow on ticks (agentic_build Watch-BobTray) |
| Version visible on card | TipForm footer `bob {ver}` |

VERSION â†’ **0.1.8** (pack when shipping).

## 2026-09-30 â€” Jeeves webhooks + digest roster + start ff-only (0.1.9)

| Lesson | Fix |
|--------|-----|
| Digest machines must be ChanServ shops only | `bobreport` roster gate + prune unregistered; period roll replaces lesser pcent |
| Intake/jira on ionos | `bobcallback` `/bob/v1/intake` + `/bob/v1/jira`; durable `webhook_queue`; announce `#bobiverse` |
| Harvest without GitHub | shared `.grok/skills/harvest` in every MSI; intake `kind` default `issue` |
| Product MSI books split | Pack stages per-product docs/skills/AGENTS; jeeves has no bob seat/TipForm |
| Start-time update | `Sync-BobiverseFromRepo` ff-only clone â†’ sync install tree; MSI update is fallback |
| Install start failures | `Report-BobiverseIntakeIssue` from Install-Jeeves/Bob/Airc |

VERSION â†’ **0.1.9**.
## 2026-09-30 â€” TipForm Restartâ†’ircBob; tray never Sync/ff (0.1.10)

| Lesson | Fix |
|--------|-----|
| Tray + service both looked like updaters | Tray Start skips product update; Sync/ff only on Start-Bob |
| TipForm Restart only relaunched UI | TipForm **Restart** â†’ `Start-BobFleetTray -ForceNew` (restarts ircBob + tray); ear-only remains `Restart-BobEar.ps1` (FR #154) |
| Quiet MSI TipForm in session 0 (invisible) | Start-BobTrayInteractive ONLOGON /IT; no session-0 Start-Process |
| Jeeves missing from #win-mpreâ€¦ | ChanServ !register required for chair_channels |

VERSION â†’ **0.1.10**.

## 2026-10-02 - chair commands, Start Menu, agent-start layer (PR #83)

| Lesson | Fix |
|---|---|
| `+h` re-granted every 30-60 s | Not a ChanServ fight: the ear was killed by the watcher (no `--host` on its command line) and rejoined. Service now bakes `-IrcHost`; chan_privs hard cap 3 grants / 10 min |
| `!recycle` had no authorization | `chair_commands.py` owner/ear auth, 120 s cooldown, `dry-run` |
| Start Menu had scattered duplicates | One `Programs\Bobiverse` folder, `Install-BobiverseStartMenu` dedupes, systray icon everywhere |
| ergo.exe hardlink broken by upgrade (#70) | Component Permanent+NeverOverwrite, `Repair-BobiverseErgoHardlink` |
| Agents did not know to file what they learned | CAST IRON RULE in AGENTS/skills, `Invoke-BobiverseHarvest.ps1` |

## 2026-10-02 - Bobiverse 0.1.20 release (PRs #83, #146, #152, #196)

| Release area | Included work |
|---|---|
| Chair parity and fleet operations (#83) | Restored gh-Jeeves commands, ear authorization, ChanServ privilege caps, explicit IRC host handling, Ergo hardlink-safe MSI upgrades, Start Menu integration, and the agent-start/harvest layer. |
| Worker status (#146) | Shows short worker status on assign/ACK and returns seats to idle on DONE/NACK/GIVEUP. |
| Remote workers (#152) | Adds authorized `!startworker`, a two-worker-per-machine cap, Jeeves-only worker input, NACK cooldown/re-bore behavior, and the UAT release flow. |
| Combined release (#196) | Consolidates the remaining 0.1.20 fixes and documentation across intake, chair/outbox, relay persistence, digest/reporting, airc remote control and durable jobs, tray packaging, sparse checkout, NSSM safety, and cursor-pool stamping. |

VERSION -> **0.1.20** (packaged MSIs and release archives).

## 2026-10-04 - CONFLICTING/superseded MRB FAIL (harvest #1609)

| Lesson | Fix |
|--------|-----|
| MRB of CONFLICTING PR when twin FR already closed by another merge: FAIL board, close the duplicate PR, DONE FAIL; do not force-merge. CONFLICTING with open acceptance still uses one fix/rebase PR. | Documented in bobiverse-bob-job-mrb + troubleshooting row in bobiverse-bob-job-irc. Absorbs #1756/#1736/#1730 twins. |

## 2026-10-04 - FR #1546 / PR #1560 Airc ReplyFile + console logs (harvest #1567)

| Lesson | Fix |
|--------|-----|
| `Invoke-AircRemote -ReplyFile` needs ear capture of `*_console` Query lines to `home/airc-replies.jsonl` plus helper poll until DONE; NSSM AppStdout under install logs with timestamps and keepalive rate-limit | Promoted into `airc/.grok/skills/bobiverse-airc`, `bobiverse-airc-troubleshooting`, and `bob/.grok/skills/bobiverse-bob-commands` (code already on main via PR #1560) |

## 2026-10-04 - Self-MRB GIVEUP wire (harvest #1603)

| Lesson | Fix |
|--------|-----|
| Never self-MRB a PR this seat opened; GIVEUP with self-MRB reason so another seat can hostile-review (and rebase if DIRTY) | Documented wire in bobiverse-bob-job-mrb + bobiverse-bob-job-irc. NACK only if spotted before ACK/work. |

## 2026-10-04 - TipForm stale worker lines (FR #1553 / harvest #1562)

| Lesson | Fix |
|--------|-----|
| TipForm looks stuck while seats are busy: BobCallback flaps + Get-BobTrayHover hung WinForms poll + lagging worker_list | Sync workers from digest/report on a non-UI timer; never block refresh on hover; roll working_on from worker_list; heal callback with Start-BobCallbackSupervised. Documented in bobiverse-bob + troubleshooting. Product: PR #1576 / #1495 / #1555 |

## 2026-10-04 - Monitor StartPending/idle+ungated -> require_machine=ionos (FR #1550 / harvest #1580)

| Lesson | Fix |
|--------|-----|
| Monitor filings about ircJeeves StartPending or idle seats + ungated offerable were offered to marchhare | gitclaim title/body cues stamp require_machine=ionos (PR #1574). Document in jeeves-monitor + bob-job-fr; put cue words in intake titles. |

## 2026-10-04 - Skill-offer idle_seats expected + callback timeout recover (harvest #1705)

| Lesson | Fix |
|--------|-----|
| BobCallback curl timeout with LISTEN can recover 200 without restart; skill flood in ungated_offerable after FR #1682 is expected until consolidate PRs land; exclude w-mh-* from idle_seats | Folded into jeeves-monitor + troubleshooting (with #1568 heal cluster). |

## 2026-10-04 - bob product vision path (harvest #1632 / FR #1615)

| Lesson | Fix / book |
|---|---|
| bob MRB/UAT vision-first | Read `bob/VISION.md`; fleet umbrella stays `common/docs/vision.md` |

Books: `bobiverse-bob-job-mrb`, `bobiverse-bob-job-uat`, `bobiverse-bob`. Twin #1639.

## 2026-10-04 - external-kill parent cache + deferred bin delete (harvest #1678)

| Lesson | Fix / book |
|---|---|
| parent_of after proc.wait() empty | Capture create-parent at start_agent (FR #1643 / PR #1658) |
| Locked hashed bob-worker bin | Defer delete via exclusive-open; not a cleanup bug |

Books: bobiverse-bob-worker, bobiverse-bob-troubleshooting.

## 2026-10-04 - MRB enqueue when resync blocked (harvest #1927)

| Lesson | Fix |
|--------|-----|
| When open PRs are missing from the MRB queue because git-claim.lock / token 403 blocked resync: enqueue_unaccepted via gh pr list; clear_seat_doing stale busy | Documented in jeeves-troubleshooting + jeeves-monitor. Product root #1811 â†’ #1993. |

## 2026-10-04 - nothing queued under strict focus + ledger giveup (harvest #2309 / #2314)

| Lesson | Fix / book |
|--------|------------|
| `nothing queued` / `bored empty` while queue.json has dozens of unaccepted rows | Diff unaccepted vs in-focus vs `offer_focus_top` per nick: strict OOF, self-MRB, same-machine `review_blocked`, `require_machine`, and `seat-ledger.json` giveups. |
| Clearing only queue `giveup_seats`/`needs_human` leaves seat empty | Also clear that seat under durable `seat-ledger.json` giveup keys. |
| Immediate ACK then GIVEUP after ledger clear | Do **not** re-clear ledger â€” that feeds a GIVEUP loop; leave stamp and file the loop. |
| Sticky MRB `offered_to` rebroadcast with no ACK | Other-machine non-ACK blocks same-machine siblings via `review_blocked`; report/recycle that seat. |

Books: `bobiverse-jeeves-monitor`, `bobiverse-jeeves-troubleshooting`. Issues: #2309, #2314; living FR #1993 append.
