# Skill harvest log

Pre-bobiverse harvest diaries (agentic_build / agentic_irc / bob-design-uat) remain under `docs/archive/*/docs/skill-harvest-log.md` for provenance. Do not treat those paths or product names as live. This file is the live bobiverse index (FR #806).


## 2026-10-04 - Harvest intake links existing PR (FR #1812)

| Lesson | Fix |
|--------|-----|
| kind=harvest/skill with no files but body/title cites pull/N filed a second skill issue (filed_issue_fallback) and queued duplicate FR work | intake links existing PR (`linked_existing_pr`); log draft_pr_error; skip_fr `harvest_pr_summary` for via-intake+skill PR-opened receipts; harvest `-ExistingPrUrl` |
## 2026-10-04 - Body-line require_machine pin (FR #1824 / #1843)

| Lesson | Fix |
|--------|-----|
| Dedicated body line `require_machine: ionos` was ignored (FR #1508 blocked inline evidence); flamingo got ionos-only offers | Honor MULTILINE `^require_machine[:=]` pin lines in body cues; keep inline evidence unpinned |

## 2026-10-04 - BobCallback multi-supervisor refuse (FR #1767 / #1831)

| Lesson | Fix |
|--------|-----|
| Two Start-BobCallbackSupervised parents fight digest.lock → public INTAKE 502 | Wrapper refuses second parent; Start-Jeeves/Register count parents and prefer schtasks /Run; health treats Ready without LISTEN as finding |

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

## 2026-09-29 ├â┬ó├óΓÇÜ┬¼├óΓé¼┬¥ WIN-MPRE8VI4U6U airc/bob/jeeves cutover

Harvested into `.grok/skills/bobiverse-{jeeves,bob,airc}` + `docs/post-install.md` + install scripts:

| Lesson | Fix |
|--------|-----|
| `Start-Jeeves` / `--channel` + PowerShell `#` comment | `irc_agent.py`: `--channel` optional when `--chair` |
| MSI LocalSystem ChairHome ├â┬ó├óΓé¼┬á├óΓé¼Γäó `C:\Users\Default\├â╞Æ├é┬ó├â┬ó├óΓé¼┼í├é┬¼├âΓÇÜ├é┬ª` | `Install-Jeeves`: prefer Admin chair or `home-jeeves` |
| Legacy `BobJeeves` + `ircJeeves` both Running | `Disable-BobiverseLegacyBobJeeves` on install |
| `CryptUnprotectData` with LocalSystem + Admin identity | post-install + skill: ObjectName / park identity interim |
| Crash-loop stderr flooding airc console | NSSM AppStdout/AppStderr ├â┬ó├óΓé¼┬á├óΓé¼Γäó `C:\ai\jeeves\logs\` |
| Leftover `AircConsole` beside bobiverse `Airc` | `Install-Airc` **removes** `AircConsole` from SCM |
| Legacy `BobJeeves` left Stopped/Disabled in services.msc | `Remove-BobiverseLegacyService` deletes SCM entry (tree kept) |
| Remote ops via bob outbox PRIVMSG to `*_console` | bobiverse-bob / bobiverse-airc skills |
| Duplicate MSI tray vs Watch-BobTray | already 0.1.5 (#14); documented again |

VERSION ├â┬ó├óΓé¼┬á├óΓé¼Γäó **0.1.6** (pack when shipping).

## 2026-09-30 ├â┬ó├óΓÇÜ┬¼├óΓé¼┬¥ DEV1 TipForm companion durable start

Harvested into .grok/skills/bobiverse-bob + docs/post-install.md + tray launcher:

| Lesson | Fix |
|--------|-----|
| Tray logs `tray up` then dies when started from Grok agent shell | `Start-BobFleetTray` uses WMI `Win32_Process.Create` (job-object breakaway) |
| Broad seat-wrapper `match Watch-BobTray` kills diagnosing shells | Kill filter requires `-File ├â╞Æ├é┬ó├â┬ó├óΓé¼┼í├é┬¼├âΓÇÜ├é┬ªWatch-BobTray.ps1` / `_Watch-BobTray-*.ps1` |
| Product is service + companion, not BobFleet task | HKCU `Run\BobiverseTray`; disable `BobFleet-<id>` |
| LocalSystem skipped update-check | `Start-Bob` no longer forces `BOBIVERSE_NO_UPDATE`; `Check-BobiverseUpdate` resolves `gh` + Releases API |
| TipForm recycle JIT `PipelineStoppedException` | CatchException before Controls; swallow on ticks (agentic_build Watch-BobTray) |
| Version visible on card | TipForm footer `bob {ver}` |

VERSION ├â┬ó├óΓé¼┬á├óΓé¼Γäó **0.1.8** (pack when shipping).

## 2026-09-30 ├â┬ó├óΓÇÜ┬¼├óΓé¼┬¥ Jeeves webhooks + digest roster + start ff-only (0.1.9)

| Lesson | Fix |
|--------|-----|
| Digest machines must be ChanServ shops only | `bobreport` roster gate + prune unregistered; period roll replaces lesser pcent |
| Intake/jira on ionos | `bobcallback` `/bob/v1/intake` + `/bob/v1/jira`; durable `webhook_queue`; announce `#bobiverse` |
| Harvest without GitHub | shared `.grok/skills/harvest` in every MSI; intake `kind` default `issue` |
| Product MSI books split | Pack stages per-product docs/skills/AGENTS; jeeves has no bob seat/TipForm |
| Start-time update | `Sync-BobiverseFromRepo` ff-only clone ├â┬ó├óΓé¼┬á├óΓé¼Γäó sync install tree; MSI update is fallback |
| Install start failures | `Report-BobiverseIntakeIssue` from Install-Jeeves/Bob/Airc |

VERSION ├â┬ó├óΓé¼┬á├óΓé¼Γäó **0.1.9**.
## 2026-09-30 ├â┬ó├óΓÇÜ┬¼├óΓé¼┬¥ TipForm Restart├â┬ó├óΓé¼┬á├óΓé¼ΓäóircBob; tray never Sync/ff (0.1.10)

| Lesson | Fix |
|--------|-----|
| Tray + service both looked like updaters | Tray Start skips product update; Sync/ff only on Start-Bob |
| TipForm Restart only relaunched UI | TipForm **Restart** ├â┬ó├óΓé¼┬á├óΓé¼Γäó `Start-BobFleetTray -ForceNew` (restarts ircBob + tray); ear-only remains `Restart-BobEar.ps1` (FR #154) |
| Quiet MSI TipForm in session 0 (invisible) | Start-BobTrayInteractive ONLOGON /IT; no session-0 Start-Process |
| Jeeves missing from #win-mpre... | ChanServ !register required for chair_channels |

VERSION ├â┬ó├óΓé¼┬á├óΓé¼Γäó **0.1.10**.

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

Books: obiverse-bob-worker, obiverse-bob-troubleshooting.
