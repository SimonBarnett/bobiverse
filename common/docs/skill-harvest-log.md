# Skill harvest log

Pre-bobiverse harvest diaries (agentic_build / agentic_irc / bob-design-uat) remain under `docs/archive/*/docs/skill-harvest-log.md` for provenance. Do not treat those paths or product names as live. This file is the live bobiverse index (FR #806).


## 2026-10-04 - TipForm stale worker lines (FR #1553 / harvest #1562)

| Lesson | Fix |
|--------|-----|
| TipForm looks stuck while seats are busy: BobCallback flaps + Get-BobTrayHover hung WinForms poll + lagging worker_list | Sync workers from digest/report on a non-UI timer; never block refresh on hover; roll working_on from worker_list; heal callback with Start-BobCallbackSupervised. Documented in bobiverse-bob + troubleshooting. Product: PR #1576 / #1495 / #1555 |

## 2026-10-04 - Monitor StartPending/idle+ungated -> require_machine=ionos (FR #1550 / harvest #1580)

| Lesson | Fix |
|--------|-----|
| Monitor filings about ircJeeves StartPending or idle seats + ungated offerable were offered to marchhare | gitclaim title/body cues stamp require_machine=ionos (PR #1574). Document in jeeves-monitor + bob-job-fr; put cue words in intake titles. |

## 2026-10-04 - MRB #1696 docs: skill offers are promote FRs (not SKIP_FR/GIVEUP)

| Lesson | Fix |
|--------|-----|
| Stale skills still said chair SKIP_FR / GIVEUP if offered skill intakes, causing live ACK/GIVEUP loops after FR #1682 hotpatch | Rewrite job-fr, bob-worker, harvest, harvest-agent-skills, jeeves-commands, jeeves-monitor: offers are intentional promote FRs; consolidate-by-book; do not GIVEUP |
## 2026-10-04 - FR #1684 skill consolidate → promote PR

| Lesson | Fix |
|--------|-----|
| Open `label:skill` / `harvest:` receipts must become promote PRs (FR #1682 offers them; do not GIVEUP) | Worker consolidates by owner skill book, closes duplicate receipts, opens one `harvest/…` PR; MRB merges. Documented in `harvest-agent-skills`, `harvest`, `bobiverse-bob-worker`, `bobiverse-bob-job-fr` |

## 2026-10-03 - FR #806 archive-richer hand-merge

| Lesson | Fix |
|--------|-----|
| Ten "archive richer" docs flagged in ARCHIVED_REPOS after #802 | Merged useful honesty-box / chair / design-uat / Ergo describe-only content into live files; left verbatim archive copies untouched; dropped stale archived-repo homes and old pack tool names |

## 2026-09-29 — WIN-MPRE8VI4U6U airc/bob/jeeves cutover

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
## 2026-09-30 — TipForm Restart→ircBob; tray never Sync/ff (0.1.10)

| Lesson | Fix |
|--------|-----|
| Tray + service both looked like updaters | Tray Start skips product update; Sync/ff only on Start-Bob |
| TipForm Restart only relaunched UI | TipForm **Restart** → `Start-BobFleetTray -ForceNew` (restarts ircBob + tray); ear-only remains `Restart-BobEar.ps1` (FR #154) |
| Quiet MSI TipForm in session 0 (invisible) | Start-BobTrayInteractive ONLOGON /IT; no session-0 Start-Process |
| Jeeves missing from #win-mpre… | ChanServ !register required for chair_channels |

VERSION → **0.1.10**.

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

## 2026-10-04 - chair "not assigning" vs open GitHub counts (harvest #1581)

| Lesson | Fix / book |
|---|---|
| Large open-issue totals look like chair failure | Mostly skill/harvest (+ needs-human); check ungated_offerable and !bored first |
| Monitor cannot !assign | By design; diagnose queue/bored/gates, do not act as chair |

Books: `jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md`, `jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md`. Canonical #1581; duplicate #1483.
## 2026-10-04 - open-PR MRB survives stale mrb_done on resync (harvest #1613)

| Lesson | Fix / book |
|---|---|
| Premature mrb_done purged open pulls | mrb_already_done(pr_exists) open wins; resync clears stale mrb_done like fr_done (FR #1585 / PR #1606) |

Books: `jeeves/.grok/skills/bobiverse-jeeves/SKILL.md`, troubleshooting, `bobiverse-bob-job-mrb`.