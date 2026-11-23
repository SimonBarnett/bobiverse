# Jeeves monitoring checks

## MONITORING command access (FR #8827)

The MONITORING agent may run the full Jeeves command matrix (`!ignore` / `!focus` / `!assign` / `!sweep` / `!stuck` / `!resync` / …) **to keep the queue moving**. Chair auth: principal kind `monitor` — nick `monitoring` by default (`JEEVES_MONITOR_NICKS`) or a services account in `JEEVES_MONITOR_ACCOUNTS`. Same mutator class as owner/ear; unrelated nicks stay denied.

**How the seat authenticates (no secrets here):**

| Path | When | How |
|---|---|---|
| **Ear relay** | Monitor host has a live `bob-<machine>` ear (usual) | Append `PRIVMSG #bobiverse :!<cmd>` (or `PRIVMSG Jeeves :!<cmd>`) to the ear outbox. Ear principal already has full mutators. |
| **Direct** | Dedicated IRC nick for monitor | Nick in `JEEVES_MONITOR_NICKS` (default `monitoring`) and/or account in `JEEVES_MONITOR_ACCOUNTS` on the chair. SASL/services login is configured on the client host — never paste passwords into docs or intake. |

`bob-worker --mode monitor` itself still has no IRC shop seat; relay or a separate IRC client supplies the nick. Playbook (when to `!ignore` vs intake): `.grok/skills/bobiverse-jeeves-monitor/SKILL.md`. Related tray UI: BOB-43 (#8681).

## intake_allowlist (FR #3117)

`Test-JeevesMonitorIntakeAllowlist.ps1` / `tools/monitor/intake_allowlist.py` probes live `POST /bob/v1/intake` with do-not-file titles for known products (including `SimonBarnett/a-search` and `SimonBarnett/trutex`).

- Denial is **only** HTTP **403** with JSON `error=repo_not_allowed` → EXIT 1 (live ircJeeves allow rule drifted; usually missing Sync/compose after an allow PR). FR #9100: both the returned-response and raised-`HTTPError` paths use that rule.
- Every other non-2xx (Cloudflare `error code: 1010` / HTML WAF 403, empty route-gate 403, 5xx) → probe error, **not** allowlist drift (FR #8861 / #9100). Do **not** Sync for a probe error.
- Probes send `User-Agent: BobiverseIntakeAllowlist/1.0 (+https://github.com/SimonBarnett/bobiverse)` plus `Content-Type` / `Accept` JSON headers so `bob.ntsa.uk` (Cloudflare) does not bot-block Python-urllib's default UA.
- Also asserts on-disk `common/scripts/intake.py` exposes `repo_allowed` / SimonBarnett owner gate (FR #3135) when the file is present.
- Remediation is scoped: Sync/compose guidance only for confirmed denials; probe-error remediation says Do not Sync.
- Overrides: `BOB_INTAKE_URL`, `BOB_INTAKE_REQUIRED_REPOS` (comma list), `BOB_INTAKE_PY`.

## open_pr_stale_base (FR #8333)

`Test-JeevesMonitorOpenPrStaleBase.ps1` / `tools/monitor/open_pr_stale_base.py` flags open pulls whose `base.ref` is not `main`/`master` (class of #8320 stuck on merged `fr-8310-land`). Set `JEEVES_OPEN_PR_STALE_BASE_FIXTURE` to a JSON pull list for offline/ops probes. Product guard: `github-resync` skips orphan `fix(mrb-N)` tips with an explicit non-default base and warns on other non-default open PRs.

## skill_promote_backlog drafts (FR #8477)

`skill_promote_backlog` also EXIT 1 when a focused repo has draft `via-intake`+`skill` leaflets older than `BOB_DRAFT_SKILL_PROMOTE_AGE_H` (default 6 hours) that were not marked ready. DONE/PASS/FAIL/GIVEUP receipt titles are not leaflets.

Operator fallback: `gh pr ready <n>` and retitle to `lesson(<book>):` so resync can offer MRB. Do not offer the pull while it is still a draft (FR #2604).

## open_pr_mrb_missing (FR #8377)

`Test-JeevesMonitorOpenPrMrbMissing.ps1` / `tools/monitor/open_pr_mrb_missing.py` flags open non-draft non-receipt product PRs that have no matching `unaccepted`/`accepted` MRB **or** FIX row (class of #8353: an open, green, mergeable PR that never reached the MRB queue). Set `JEEVES_OPEN_PR_MRB_MISSING_FIXTURE` to a JSON pull list (optionally `{"repo": "owner/name", "pulls": [...]}`) for offline/ops probes.

- Every expected PR with no MRB/FIX row → EXIT 1 (finding), plus a `queue.json missing` note when the queue file is absent.
- A FIX row (ci-fail / conflict / dirty fold) also covers the PR — it is being handled, not stranded.
- Shared classification: `common/scripts/gitclaim.py` `open_pr_expects_mrb_or_fix_row` / `list_open_prs_missing_mrb` (drafts, intake harvest receipts, stacked `fix(mrb-N)` tips, `docs/mrb-*` pins and lesson-of-lesson tips are ignored). A `fix(mrb-N)` on `main`/`master` is expected MRB work (FR #8475); the higher-numbered twin of an open parent is not.

## depends_on (FR #8848)

`Test-JeevesMonitorDependsOn.ps1` / `tools/monitor/depends_on.py` exits 1 when an offered or accepted queue row has a `Depends-on:` ref that is still OPEN in the local queue (chair missed BOB-D3). A skipped row (`status=skipped`, `depends_skipped`, or `skip_reason`) exits 0. No Depends-on rows is a soft-ok. Live runs without `--chair-home` stay soft-ok until `common/scripts/depends_on_parse.py` exists or `gitclaim.py` contains `bob_d3_skip_open`. No GitHub token. Distinct from the hold label and from `fr_digest`.

Chair note for the three gates (digest go-gate vs hold vs Depends-on CLOSED): [fr-digest-vs-hold-vs-depends-on.md](fr-digest-vs-hold-vs-depends-on.md) (BOB-G2 / FR #8838; cites VIS-G3 + BOB-G1 `bob_g1_skip_held_digest`).

## fr_digest (FR #8849)

`Test-JeevesMonitorFrDigest.ps1` / `tools/monitor/fr_digest.py` exits 1 when an offered or accepted child `Depends-on:` a local queue row that still has both labels `fr-digest` and `hold` (chair missed BOB-G1). Removing `hold` (unhold) allows the offer (exit 0). A lone `hold` label is not this check. Live runs without `--chair-home` stay soft-ok until `common/scripts/fr_digest_gate.py` exists or `gitclaim.py` contains `bob_g1_skip_held_digest`. Run after `depends_on`. No GitHub token.

## github_resync_focus (FR #3146)

`Test-JeevesMonitorGithubResyncFocus.ps1` / `tools/monitor/github_resync_focus.py` flags when `focus.repos` is non-empty but the offer queue stays empty (`unaccepted=0`) or `discover_repos` misses focus keys.

- Product: `common/scripts/chair_health.py` `discover_repos` **unions** `focus.repos` (short keys like `a-search` → `SimonBarnett/a-search`).
- Ops: write digest-home `resync-repos.txt` with focused full names and run `!resync` (or wait for the 15m cycle after Sync/compose).
- FR #4725: install and chair start seed/merge `DEFAULT_RESYNC_REPOS` into chair + digest `resync-repos.txt` (includes `SimonBarnett/ce-priority`). Pack copy: `jeeves/defaults/resync-repos.txt`.
- Silent `github_resync ok repos=0` with a live focus list is a finding, not ok.

## workers_last_good_orphan (FR #9145)

`Test-JeevesMonitorWorkersLastGoodOrphan.ps1` / `tools/monitor/workers_last_good_orphan.py` is **token-free** and reads only the local `digest.json`. It EXIT 1 when a machine has `workers_stale` true, empty live `workers` / `worker_list`, and a non-empty `workers_last_good` snapshot (ghost seats that still paint on GET `/bob/v1/report`). Missing digest is EXIT 0 (`digest_present=false`). Unreadable or wrong-shape JSON is EXIT 2. Remediation: `POST /bob/v1/report` `worker-remove` for each nick (or `delete-worker` by pid). Related product: last-good TTL `BOB_DIGEST_LAST_GOOD_MAX_S` (default 1800s) on export/restore.

## ircbob_ear (FR #9144)

`tools/monitor/ircbob_ear.py` is **token-free**. It EXIT 1 when digest machines show `online=false` / status `I am offline`, or `lastSeen` older than 900s (same band as `stale_digest`). On win32 it also reads local `Get-Service ircBob`; when Status is Stopped it tries one `Start-Service` and re-checks (`heal=started|failed`). TipForm `Resolve-BobTrayDigestFailNote` prefers `digest ear-offline:` over `digest unreachable:` when the ear is down or digest shows offline (pure GetResponse failures stay unreachable). Never touches Ergo / BobIrcd. Remote WinRM Start-Service is out of scope.

## Composed drive-root monitor scripts (FR #8860 / #9007 / #9100 / #9309)

A non-chair composed install such as `J:\` does not run chair `Start-Jeeves`, so `tools\monitor` can stay on a pre-fix copy after main moves (class of #8585 / #8650 / FR #9007 / FR #9309). `Start-JeevesMonitor.ps1` and `Invoke-JeevesMonitorCheck.ps1` call `Sync-BobiverseFromRepo.ps1 -Product jeeves -InstallRoot <root>` when they can resolve that script (FR #9007). **FR #9309:** prefer `BobInstallRoot\common\scripts\Sync-BobiverseFromRepo.ps1` (tip, with `sync-monitor-force`) over a stale composed flat copy under `J:\scripts` --- the flat Sync from an old MSI/compose lacked the force path, so checks such as `opencode_seats.py` (FR #8583) never landed even though AGENTS listed them. Sync force-copies `tools\monitor` from tip (`sync-monitor-force`) even when the flat files have a newer mtime; FR #9100 skips when source equals destination and warns on a nonzero Sync exit without blocking monitor start. The rest of jeeves `tools\` stays `/XO` (MRB #6162).

UNC installs such as `\\walrus\Jeeves` need `BOBIVERSE_REPO` pointing at a checkout because Sync discovery uses drive prefixes. Drive-root `J:\` resolves bob via `C:\ai\bob` / `D:\ai\bob` (same as Start-JeevesMonitor), not `Split-Path -Parent` of `J:\` (empty).

Operator: `Sync-BobiverseFromRepo.ps1 -InstallRoot J:\ -Product jeeves` with `$env:BOBIVERSE_REPO` set to a tip checkout (or `-InstallRoot C:\ai\bob\jeeves` on a repo-tree host). After Sync, `tools\monitor\opencode_seats.py` and `scripts\Test-JeevesMonitorOpencodeSeats.ps1` must be present.

## empty-offer playbook (FR #2448 / #2446)

When seats hear `nothing queued` while `queue.json` still has unaccepted rows:

- Operator playbooks: **[empty-offer-playbook.md](empty-offer-playbook.md)** (FR #2448) and **[empty-offer-operator.md](empty-offer-operator.md)** (FR #2446 heal APIs).
- Log fields: `require_machine` / `ledger` / `out-of-focus`; seat-ledger heal when every live pin-machine seat GIVEUP'd; shop workers on pin machines.
- `queue_flow` auto-heals pin+ledger starvation (FR #2446) and raises a finding after **>10m** of pin-only / empty offerable for idle seats (FR #2448).

## idle_seats (FR #1116 / #8536)

`Test-JeevesMonitorIdleSeats.ps1` / `tools/monitor/idle_seats.py` finds idle digest seats only when at least one unaccepted row is **offerable** to a live idle seat (same gates as `offer_focus_top`: needs_human, cooldown, skip labels, machine pin, ledger, UAT/MRB rules).

**FR #8536:** when idle seats exist and `offerable_for_live_seats==0`, the check stays EXIT 0 and sets `healthy_idle_empty_offerable=true` (and `queue_needs_human_only` when every unaccepted row is needs_human). Notes say do not recycle as hung. Digest `queue` also exposes `offerable_count` / `queue_needs_human_only` for TipForm.

**FR #8866 (non-chair):** when neither home has `queue.json`, the check fetches one live `/bob/v1/report` (same missing-queue rule as `queue_flow` FR #8579). It does not need a local `digest.json`. Idle seats come from the report after dropping `workers_stale` machines. `offerable_for_live_seats` is an estimate (`offerable_estimate=true`): pending offer, needs_human, cooldown, and an explicit `require_machine` matched to an idle seat machine. Unverified gates (not applied): focus, ignore, ledger, review-author, FR/MRB shape, free-fuel, inferred pins. Idle seat plus estimate > 0 is EXIT 1 and names each nick. No live idle seats is EXIT 0. A missing, stale, or incomplete report is EXIT 1 (`local queue missing; live report unavailable/stale/incomplete`) with `idle_seats=[]`. A present local queue never fetches.

- Gated-only queue + idle seats → EXIT 0
- Idle seats + offerable row → EXIT 1
- Pin-only empty offer sustained >10m → EXIT 1 (`queue_flow`, FR #2448 / #2446)

## auto_feed (FR #8493)

`tools/monitor/auto_feed.py` treats a missing `auto-feed.json` as configured=false. That stays EXIT 0 when no idle seat has an offerable row. When auto-feed is absent or disabled **and** `idle_seats` would EXIT 1, this check EXIT 1 with the idle and offerable counts and says seats must `!bored` or auto-feed must be enabled. The check does not turn auto-feed on.

Open product PRs with no MRB or FIX row stay on `open_pr_mrb_missing` (FR #8377). This check does not enqueue them.

## chair tree without git (FR #8493)

`needs_human_false_positive` calls `gitclaim.heal_false_needs_human_for_infra_soft` every monitor cycle, so a false `needs_human` from `worktree-create-failed:disk`, `holder_bored`, or `busy` does not persist past the next cycle **when that function is in the live chair tree**. A flat `<ai root>\jeeves` with no `.git` does not fast-forward on `Restart-Service ircJeeves`. Install a sparse git worktree or Apply the latest release; a restart alone leaves the previous `gitclaim.py`. Do not hotpatch the live chair from a worker seat.
## Idle-seat eligibility recovery (FR #6256)

See [idle-seat-recovery.md](idle-seat-recovery.md) for the decision table, evidence freshness, and shop-only `!recycleseat` handoff when author-only MRB deadlock is remediable by a fresh session.

