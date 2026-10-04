# Skill harvest log

Pre-bobiverse harvest diaries (agentic_build / agentic_irc / bob-design-uat) remain under `docs/archive/*/docs/skill-harvest-log.md` for provenance. Do not treat those paths or product names as live. This file is the live bobiverse index (FR #806).


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

## 2026-10-04 - skill-harvest-log rebase keep-both (FR #1757 / #1750)

| Lesson | Fix |
|--------|-----|
| Harvest PRs that touch skill-harvest-log.md must rebase onto main before MRB merge when parallel promotes landed; one fix PR must keep both dated sections | Documented in harvest-agent-skills + bobiverse-bob-job-mrb. Evidence: MRB #1741 FAIL-fixed via #1750 (TipForm + ionos-pin sections both kept). |
