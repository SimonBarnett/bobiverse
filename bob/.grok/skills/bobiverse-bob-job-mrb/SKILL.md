---
name: bobiverse-bob-job-mrb
description: >
  The single skill for MRB jobs - process diagram from Jeeves assign through ACK, vision-first tests-first hostile review and drift check, docs review, one docs or fix PR and merge to DONE; steps, evidence required, who owns what (the originating agent owns the hostile MRB).
---

# bobiverse bob - MRB job (hostile review)

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

**Job type `MRB`** (Material Review Board) - hostile, tests-first review of a pull request against the FR and the repo vision. Wire format and timing: `bobiverse-bob-job-irc`. The MRB is done by a **different seat or a fresh session** than the one that wrote the PR; the originating agent owns the review. An assigned MRB job authorises you to merge **that PR** (and its one docs/fix PR) - nothing else.


## FR #3948 - hand off after push; never poll CI (durable)

> **CAST IRON - overrides any merge / behind-main / "never merge red" wording elsewhere in this skill that tells a seat to wait on CI or loop merging main in.**
>
> 1. Do the hostile review, local tests, docs review and **your own pushes** exactly as before.
> 2. **Never poll or watch CI to completion** (no `gh pr checks --watch`, no `gh run watch`, no sleep/re-check loops on checks or mergeability). **Never loop merging `origin/main` in.** DONE goes out within about 1 minute of your last push.
> 3. **Fold only when needed (FR #4649):** fold `origin/main` (`gh pr update-branch` or one local merge + `check_conflict_markers.py` + local tests + push) only when the PR is `CONFLICTING` / mergeStateStatus `DIRTY`, or CI failed on something already fixed on main (cite that main commit or PR on the board). Never fold just because the PR is behind. If the repo has no required up-to-date check, PASS at the current head SHA and arm `--auto`. A later behind count is not another fold.
> 4. **PASS:** post the MRB board (`## MRB board` + `**Verdict:** PASS`) and include the **head SHA** (`gh pr view <n> --repo <owner/repo> --json headRefOid -q .headRefOid`), e.g. `MRB PASS @ <sha>`.
> 5. **Hold check (FR #3928):** if the PR has a hold label (`on-hold` / `hold` / `do-not-merge` / `wip`) or an owner/maintainer hold comment, do **NOT** merge and do **NOT** enable auto-merge. Post PASS, comment `MRB PASS - held, not merged (hold: ...)`, then DONE.
> 6. **Not held:** run `python common/scripts/mrb_merge_gate.py <owner/repo> <pr>` (exit 0; FR #4112: uses `GH_TOKEN`/`GITHUB_TOKEN` or falls back to `gh auth token`). FR #4467: HTTP 403/429 on the comment list is retried, then exit 3 (comments unknown; not an owner hold; not merge refused). If this seat just posted the PASS board, continue with auto-merge or merge-on-green pending; do not treat exit 3 as a hold or a refused merge. Check `gh api repos/<owner/repo> --jq .allow_auto_merge`.
>    - `true`: `gh pr merge <n> --repo <owner/repo> --auto --merge` for the PR (and the one docs/fix PR if you opened one), then DONE **immediately**. Do not wait for the merge. If auto-merge is already armed as SQUASH, leave it; do not disable and re-arm just to flip the method (FR #4492).
>    - `false`, or `--auto` errors: do **not** run a plain `gh pr merge` and do not wait. Comment `merge-on-green pending` (with the head SHA). Jeeves `mrb_merge_on_green` merges when checks are green on that SHA, or re-queues on CI red / SHA change. Then DONE.
> 7. **Issue closure:** with a pending (auto-)merge the originating issue stays open until merge; DONE after verifying it is linked via `closingIssuesReferences` (`Closes owner/repo#N`). Do not close it by hand before the merge.
> 8. **FAIL:** existing flow - exactly ONE separate fix PR, leave the originating issue open, board, DONE FAIL. The no-poll rule still applies (hand the fix PR off the same way). **FR #4718:** if DONE FAIL lands with no linked mrb-N-fix / fix(mrb-N) open, Jeeves queues one FIX for that head (resync does the same); the seat that FAILed is not offered that MRB again; `!assign ... FIX` accepts the PR even when CI is green. **FR #5142:** a FIX seat that finds a companion `fix(mrb-N)` / `mrb-N-fix` PR must fast-forward the assigned original tip (`git push origin HEAD:<assigned-head-ref>`) so that one PR carries the fix, then close the companion as duplicate of the tip push. Do not leave two open PRs for the same FAIL.
> 9. DONE wire: `DONE MRB owner/repo#N PASS|FAIL <assigned-pr-url>` as its own short command. Optional FR #5317 counters may follow the URL: `cr_findings=<n> confirmed=<n> fp=<n>` (shop_listen keeps the URL). Do not put other text after the URL.
> 10. **CI wait (FR #4466):** github-resync must not re-queue an open PR whose auto-merge is on and whose head SHA still matches the PASS sha in the merge-on-green ledger. A head SHA change, or auto-merge turned off, puts the MRB back. Rows already queued for that waiting PR are pruned on the next resync. FR #4661: when the merge-on-green ledger missed the PASS SHA (DONE/resync race), done[] MRB PASS plus auto-merge on the tip still counts as ci-wait; never re-offer that MRB to the seat that already DONE PASS on it, and duplicate-after-done clears the hold and drops the phantom unaccepted row.


## Process

```mermaid
flowchart TD
  A["Jeeves assign: nick: MRB owner/repo#N url"] --> B["ACK MRB owner/repo#N (outbox, at once)"]
  B --> C["git worktree under %TEMP% (never gh pr checkout from install); read PR"]
  C --> D["Find the vision: VISION.md, brief, README, CAST IRON rules; quote 1-2 lines"]
  D --> E["Add NEW tests for the PR BEFORE the verdict"]
  E --> F["Run existing + new tests; hostile review; drift check; UTF-8/no-BOM check"]
  F -->|"tests or drift FAIL"| G["Exactly ONE separate fix PR"]
  G --> L
  F -->|PASS| I["Review README/skills/docs/mermaid for stale text"]
  I -->|stale| J["ONE separate docs/mrb-N PR"]
  I -->|ok| L["Post the MRB board PASS first (FR #3928)"]
  J --> L
  L --> G2["mrb_merge_gate: no owner hold + PASS board present"]
  G2 --> H["PASS @ head SHA; never fold just because the PR is behind; never poll CI (FR #3948 / FR #4649)"]
  H --> H2{"held?"}
  H2 -->|yes| H3["Comment held, not merged"]
  H2 -->|no| H4["gh pr merge --auto OR merge-on-green pending"]
  H3 --> M["Verify Closes link / issue state (pending merge OK)"]
  H4 --> M
  M -->|"not linked"| M2["Fix Closes link on the PR body"]
  M -->|"linked or closed"| P["DONE at once; Jeeves/GitHub merges on green"]
  M2 --> P
  P --> N["DONE MRB owner/repo#N PASS-or-FAIL pr-url  (nothing after the url)"]
  N --> O["Program posts !bored - next job"]
  B -. cannot or blocked .-> X["NACK / GIVEUP MRB owner/repo#N + reason on its own line"]
```

## Steps

> **FR #3948 applies to steps 6-10:** no CI polling, never fold just because the PR is behind (FR #4649), PASS with head SHA, then auto-merge (or `merge-on-green pending`) and DONE at once - see the FR #3948 section above.

## FR #5317 - CodeRabbit verify-first (token-saving)

When the assign line or PR has a CodeRabbit walkthrough / inline comments on the current head:

1. Read the walkthrough and unresolved inline findings first.
2. Mark each finding **confirmed** (fix or require a fix), **false positive** (reply `@coderabbitai` with one line so it learns), or **out of scope**.
3. Then do only the fleet checks CodeRabbit cannot: vision and drift against the product VISION.md, tests-first evidence, and docs review. Do not redo a line-by-line review.
4. On DONE, append `cr_findings=<n> confirmed=<n> fp=<n>` after the PR URL.

CodeRabbit / Copilot / extra fleet stages are **off by default** on the chair (`BOB_FUEL_CODERABBIT`, `BOB_FUEL_COPILOT`, `BOB_FUEL_FLEET`). Missing review never blocks merge; Jeeves may offer `coderabbit=timeout` after the wait window.

1. **ACK.** 2. Check out the PR in a **job worktree** (**FR #4988:** `Get-BobiverseJobWorktreePath -Repo owner/name -Job mrb-N` → default `<data drive>\ai\worktrees\<repo>\mrb-N`; override `BOB_JOB_WORKTREE_BASE` or `BOB_BRIDGE_HOME\worktrees`; never a drive root; `%TEMP%\…` only as a last resort). `git -C <product-clone> fetch` + `worktree add` of the PR head. **CAST IRON (FR #4925):** never run `gh pr checkout <n> --repo <other>` from the bob install root (`C:\ai\bob`, `bob\worker`, or any cwd whose `git remote` is `SimonBarnett/bobiverse` while `--repo` names a different product). That switches the install sparse work tree off `main` onto an `intake/...` branch. Optional guard: `Assert-BobiverseForeignPrCheckout.ps1 -Repo owner/name` (exit 2 = refuse). Read the intent, the FR and every changed file. Before `git worktree add`, if `Get-PSDrive C` FreeGB is under 2, run `..\scripts\Clear-BobiverseJobWorktrees.ps1 -RepoRoot <ai root>\bob` (FR #877; Clear also reclaims under the FR #4988 base and keeps dirty/unpushed trees). **Immediately after** `worktree add`, write `.bobiverse-seat` (`{"nick":"<seat>","pid":$PID}`) at the tree root (FR #3641) so soft-cap / sibling Clear cannot wipe a mid-MRB tree. **CAST IRON (FR #2727 / FR #3641):** never hand-delete / `Remove-Item` paths Clear did not select; if FreeGB stays under 2 after Clear, file an intake disk issue and put the MRB tree on a roomy drive (or GIVEUP) — do not invent a `C:\ai\*` delete list. After DONE, prune again with `-KeepPath` omitted so the MRB tree can go. 3. **Vision first**: read `VISION.md`/brief/README/AGENTS and quote 1-2 lines the PR is judged against. For **bob** ear/worker/tray changes prefer **`bob/VISION.md`** (FR #1615 / harvest #1632); for **airc** console changes prefer **`airc/VISION.md`** (FR #4158); for **jeeves** chair/gitclaim changes prefer **`jeeves/VISION.md`** (FR #5090); the fleet umbrella stays `common/docs/vision.md` --- do not treat the umbrella as the bob, airc, or jeeves product vision.
No vision found: record "no vision source found", review against README + FR, and file ONE FR asking for a `VISION.md`. If the PR shows the vision itself should change, do not edit it - file an FR tagged `vision` for the owner.
4. **Tests before verdict**: add the new tests the PR needs, then run existing + new. **FR #2655 (airc PRs):** before PASS, run the full `airc/tests` suite (not only the new FR file) — signature changes like `send_privmsg(..., flood=)` break 2-arg monkeypatch stubs elsewhere. 5. Hostile review + **drift check** (separate verdict line): serves the stated vision? contradicts CAST IRON / earlier decisions? scope creep? under-delivery (letter, not intent; code never wired)? Drift is a FAIL like a red test. **ACCEPTABLE drift (harvest #1663):** a partial FR that lands the core acceptance and files explicit follow-up issues for the remainder (e.g. SkipTidy autostart PASS while TipForm Restart still tidies; leftover #1642/#1643) may PASS — say so on the drift line; do not FAIL solely for intentional scoped follow-ups.
6. Encoding: changed *.md are UTF-8 without BOM (no mojibake). **CAST IRON (FR #3935):** WinPS 5.1: never Get-Content -Raw (or Set-Content -Encoding utf8) round-trip of UTF-8 SKILL.md / docs; em-dashes (U+2014) mojibake. Edit with Python open(..., encoding="utf-8") / Path.write_text(..., encoding="utf-8"); prefer ASCII --- in new prose when possible (FR #3935). **CAST IRON (FR #1634):** before every gh pr merge, run python common/scripts/check_conflict_markers.py --root <worktree> (or rely on the check-conflict-markers CI workflow) and **refuse merge** if any <<<<<<< / ======= / >>>>>>> conflict markers remain in the tip. **Fold rule (FR #4649):** never fold just because the PR is behind. Fold `origin/main` only when the PR is CONFLICTING / DIRTY, or CI failed on something already fixed on main (cite that main commit or PR). Then re-run conflict-marker + tests **before** gh pr merge. **Separate clone (FR #4647):** a job tree that is its own clone does not see a fetch run in another clone. Before a fold that FR #4649 allows, run `git fetch origin` inside that job tree and merge that tree's `origin/main`. Do not fold a stale `origin/main` taken from a different clone. **CAST IRON (FR #3928):** never merge a PR that is on hold, and never merge without a posted MRB PASS board. After ACK, if labels `on-hold` / `hold` / `do-not-merge` / `wip` or an OWNER/MEMBER/COLLABORATOR comment matches `on hold` / `must not merge` / `do not merge` (and is not later cleared with `hold lifted` / `ok to merge`), **NACK or GIVEUP** with reason `on-hold` — do not review-to-merge. Before every `gh pr merge`, post the MRB board with `**Verdict:** PASS` first, then run `python common/scripts/mrb_merge_gate.py <owner/repo> <pr>` (exit 0 required; exit 2 = refuse; exit 3 = comments unknown after HTTP 403/429 retries, not a hold and not merge refused - if this seat just posted the PASS board, continue; FR #4467; FR #4112: env `GH_TOKEN`/`GITHUB_TOKEN` or `gh auth token` fallback). Chair also skips enqueue/offer when hold text/labels are stamped on the row. **FR #4545:** pr_hold_reason still treats hold labels and title cues as holds. PR body text matches only a line-anchored On hold: or HOLD: stamp. Free harvest-lesson prose such as "do not merge the thinner duplicate" must not skip enqueue. **FR #4041:** `mrb_merge_gate` skips `## MRB board` / `**Verdict:**` comments when scanning owner hold text (boards posted via `gh` look OWNER and often discuss hold labels). ****FR #4487:** the same skip covers a `## MRB hand-back` comment (self-MRB GIVEUP that says this seat must not merge). A later real owner hold still refuses. A hand-back does not clear an earlier real hold. **FR #4500:** a later comment that only restates the gate refusal (held, not merged, and mrb_merge_gate.py exit 2) is not a new owner hold. It does not clear an earlier real hold. 7. **PASS** -> review docs/skills/usage text for staleness; if stale open exactly ONE **separate** docs/mrb-<N>-... PR (never push onto the PR under review). Then hand off per **FR #3948** (PASS @ head SHA, never fold just because the PR is behind (FR #4649), `gh pr merge --auto` or `merge-on-green pending`, DONE within ~1 minute - never poll CI). Additive hostile tests that are not product fixes belong on that docs/mrb-N PR. **Body/docs-only nits** (e.g. missing Duplicates closed: line) while tests are green: PASS and merge without a separate **fix** PR — put wording nits on the docs PR or edit the PR body; close harvest twins as not planned (Duplicate of #N / fixed by PR #M).
**Harvest promote order (harvest #2296 / MRB #2289):** merge the **skill/promote PR first**, then open the one `docs/mrb-N` hostile-test PR **from the new `origin/main` tip** (not from the pre-merge promote tip). Before **DONE PASS**, verify `gh issue view` that `Closes` actually closed the skill issue (or close it with a comment). Example: #2289 then docs #2295.
**FAIL** -> exactly ONE separate fix PR, then merge original + fix (not several fix PRs). Never merge UNSTABLE/red. 8. Post the MRB board. **Issue closure (t826u):** the assigned MRB authorises you to merge that PR (and its one docs/fix PR). On merge, the PR's **`Closes <owner>/<repo>#N`** line closes the originating issue - confirm that line is in the PR body (add it by editing the body if the FR author missed it; a fix/docs PR gets `Refs`, never a second `Closes`). If you are **not authorised to merge**, still confirm the `Closes` link so the issue closes when the owner merges, and say so on the board.
After the merge check `gh issue view N --repo <owner>/<repo> --json state`: if it is still open (PR merged into a non-default branch, or the link was missing) **close it yourself with a comment** (`gh issue close N --comment "Closed by <PR url> (merged into <branch>). MRB: <verdict>"`). **FR #791:** `gh issue close` does not accept `--body-file` (unknown flag) — use `-c` / `--comment` only. A FAIL that ends without a merge leaves the issue open.
9. Hand off: there is no per-PR UAT - Jeeves queues ONE repo-level UAT once every issue is closed and every PR is merged. 10. **DONE (own command)** - only after the issue is verified closed, or (not merged yet) verified linked via `closingIssuesReferences`. Order after the board/merge: append DONE/NACK/GIVEUP as its own short command (never check the outbox first; FR #2876), **then** harvest/prune — never chain DONE inside a long board/merge/harvest tool call.

## Duplicates: verify and close them (t857u)

Harvest receipt rule: any receipt whose title or body says DONE, twin, duplicate, filed, or merged is closed by the worker/MRB as soon as it is filed; a receipt is never left open.

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

The PR body must carry a **`Duplicates closed:`** line (or `none (searched: ...)`). During the review search the open issues again for duplicates of what the PR fixes;
any still open that the implementer missed: comment **`Duplicate of #N / fixed by PR #M`** and close as not planned
(`gh issue close <dup> --repo <owner>/<repo> --reason "not planned" --comment "Duplicate of #N / fixed by PR #M"`), and add it to the board. A real extra issue the PR
fixes needs its own full-form `Closes <owner>/<repo>#D` line. A PR with no `Duplicates closed:` line is a review nit; a PR that leaves an obvious open duplicate is a FAIL
once the implementer cannot be reached. Never close `needs-human` / `board` issues as duplicates.


## Pytest / sparse worktrees (FR #963)

Skill-intake consolidation: when a worker takes an FR from skill intake (label:skill / harvest), it must close all open issues for that skill book (every harvest/skill issue targeting the same book), open one consolidated PR for them, and cite every issue it closes (Closes #N for each); no per-issue PRs for the same skill book; the worker closes the issues itself as part of DONE.

`repo_layout` lives in `common/scripts/repo_layout.py`. Prefer `git sparse-checkout disable` in the MRB temp tree. **CAST IRON (FR #4029 / MRB #4035):** disable sparse **once** after add + `.bobiverse-seat`; never re-run on an already-full tree (can detach `.git` / wipe uncommitted work). Partial sparse sets must include `common/scripts`; do not rely on `PYTHONPATH=common/tests`. Service `*/tests/conftest.py` puts `common/scripts` on `sys.path`.

**bob_worker tip shadow (FR #2782 / MRB #2789):** when pytest-importing `bob_worker` from a job worktree, run pytest with cwd set to that worktree and put `<wt>\bob\scripts` first on `PYTHONPATH`. The install flat copy `<ai root>\bob\worker\bob_worker.py` otherwise shadows the tip module and makes tip tests look like main failures. Seat cwd alone is not enough if the flat install copy is found first.

## Evidence required (the MRB board comment on the PR/issue)

* **Verdict** `PASS`/`FAIL`, plus the **drift verdict** line and the quoted vision line(s). * Tests: which new tests you added, the exact commands run, pass/fail counts, any flaky/skipped.
* Hostile findings (numbered, with file:line) and how each was resolved (or why it is acceptable). * Docs verdict (stale or not; link to the docs PR if any). * Merge result (SHAs/PR links), and **what could not be tested live**. * No secrets or private hosts.

## Who owns what

| Who | Owns |
|---|---|
| The originating agent | the hostile MRB and its verdict, the merge decision, then the UAT hand-off (`bobiverse-bob-job-uat`). |
| The implementer | the PR under review - they never review or merge their own PR; findings go back as the one fix PR (written by the MRB seat). |
| Jeeves | queue and busy/idle bookkeeping; announces merges. |
| The owner (Simon) | the vision; releases and version bumps (not part of an MRB). |

## Rules

* **A successful MRB closes the originating issue**: merge -> `Closes` auto-closes it; otherwise you close it with a comment (never leave a merged PR's issue open, never close it for a FAIL that did not merge). * Different seat/session than the author. One docs PR at most; one fix PR at most. No release, no version bump, no Ergo changes, no secrets, PowerShell only.
* **Never merge conflict markers (FR #1634):** tip must be clean of `<<<<<<<` / `=======` / `>>>>>>>`; use `common/scripts/check_conflict_markers.py`. Fold `origin/main` only when CONFLICTING/DIRTY or CI failed on a main-fixed issue (FR #4649); never fold just because the PR is behind; harvest twins close as not planned. * **Never merge on hold / without PASS board (FR #3928):** owner hold label or comment blocks offer and merge; post `## MRB board` with `**Verdict:** PASS` before any merge path; run `common/scripts/mrb_merge_gate.py`. * **Never poll CI after push (FR #3948 / FR #4649):** PASS with head SHA, never fold just because the PR is behind, then `gh pr merge --auto` or comment `merge-on-green pending`; Jeeves `mrb_merge_on_green` merges on green / re-queues on red or SHA change; held PRs are never auto-merged. DONE within about 1 minute of the last push. * Report which agent and model did the review. * CAST IRON harvest rule at the top: file every issue/FR/bug you find in the same turn - findings that are not part of this PR become new intake items.


## CONFLICTING / superseded MRB (harvest #1609)

**CONFLICTING alone is not an automatic FAIL.** If this PR is still the unique fix: merge `origin/main` into the tip, resolve markers, re-run tests + `check_conflict_markers.py`, then continue the normal PASS/FAIL review.

**skill-harvest-log.md (FR #1757 / #1750 / harvest #2274):** harvest/promote PRs that append dated sections to common/docs/skill-harvest-log.md race each other. Rebase onto main before merge; when both sides added sections, **keep both dated sections** in the one fix/rebase PR (MRB #1741 -> #1750). Dropping the other promote's section is a FAIL. If the **fix PR itself** goes CONFLICTING against newer `main` before you REST/`gh pr merge`, merge `origin/main` into the fix tip and **keep-both again**, then re-check markers/tests, then merge (do not REST-merge a dirty tip). Example: MRB #2241 → fix #2272.

When the assigned PR is already **closed**, or a **duplicate/superseded** of work already on main (twin FR closed by another merge) — including when that duplicate head is also CONFLICTING:

1. Confirm the superseding merge: `gh pr view` / `gh issue view` — lessons and originating issues already landed (`Closes` / merged PR URLs).
2. Do **not** force-merge, rebase-to-revive, or re-open the duplicate head.
3. Post an MRB board with verdict **FAIL** (or FAIL-superseded): cite the merged PR(s) that already satisfy acceptance.
4. Close the duplicate/conflicting PR with a comment pointing at the superseding merge.
5. If the originating issue is still open only because this duplicate never merged, close it citing the merged fix URLs (not this PR).
6. **Wire:** product / unique-acceptance FAIL → `DONE MRB owner/repo#N FAIL <assigned-pr-url>`. **Harvest-lesson FAIL-supersede / CLOSED / MOVED / Duplicate / not-useful** → `DONE MRB owner/repo#N PASS <assigned-pr-url>` (FR #4800 / FR #3317). `DONE FAIL` on those tips makes Jeeves enqueue FIX (FR #4718).

**Harvest-lesson twins:** the same rule applies when two `lesson(<book>):` / `harvest-lesson` tips carry the same playbook — FAIL-superseded the later one; never merge the misplaced raw duplicate tip into `harvest` when the playbook belongs (or already landed) in `bobiverse-bob-job-mrb` (MRB #2741 / #2747 / #2750). Wrong-**repo** tips follow **Harvest-lesson intake PRs** step 0 (re-file / MOVED / hold-open) — never FAIL-close without a skill-book link (FR #3299).

**CAST IRON twin-close filter (FR #3414 / FR #3803):** when batch-closing open harvest-lesson tips, match **exact lesson title / tip title needle** only. Prefer PowerShell **exact title equality** (`-eq`) or **`.StartsWith($fullTitlePrefix)`** of the full `lesson(<book>): …` title (or the exact Harvested-lessons bullet). Never use PowerShell `-match` (regex) for twin selection, and never a short shared substring such as `lessons that already live` that appears in many tips (MRB #3792 / FR #3803 swept unrelated open tips). Never use a broad `Phase-2|normalize|stack` (or similar) regex (MRB #3366). Helper: `common/scripts/bobiverse_exact_title.py` (`is_exact_harvest_twin_title` / `select_exact_title_twins`). Close comments must cite **that tip's own durable product/skill PR** (or skill-book location on main) — cite the assigned MRB number only when the tip is an **exact twin** of the assigned head. Wrong-book tips may still close as not planned, but each comment's Duplicate/supersede citation must be accurate.

**CAST IRON already covers it (MRB #2732 / #2783):** if the same skill book already has a CAST IRON / product paragraph covering the lesson (for example FR #2727 Clear `removed=0`), FAIL-supersede and close as not planned — do not merge a weaker `## Harvested lessons` duplicate. Cite the skill-book location on main (step 0).

Self-MRB remains a separate hand-back (GIVEUP / NACK); this section is for hostile review of a head that lost the race to main.

## Fix-PR race after DONE (harvest #1981 / MRB #1847)

After you **DONE PASS** a FAIL-fixed MRB, the one fix PR can still race **CONFLICTING** and be closed **unmerged** (parallel main moves). Before ending the seat:

1. Confirm the fix tip actually landed: `git fetch origin main` and `git show origin/main:<path>` / pytest for the lesson markers.
2. If the fix PR is closed unmerged or main lacks the lesson, immediately open a **land PR** from the known-good tip (or cherry-pick the fix commit tree) onto current `main`, merge it, and verify `origin/main` again.
3. Post a short follow-up board comment on the assigned PR citing the land PR URL.
4. Do **not** force-push an empty main tip onto the fix branch; do **not** close originating issues until the lesson is on `main`.
5. When a harvest tip is CONFLICTING, branch from current `origin/main`, add only the lesson and its hostile pin, then `force-with-lease`. Never `git reset --soft origin/main` on a dirty tip (FR #4494).

## Self-MRB (harvest #1603 / MRB #1578)

Never hostile-review or merge a PR **this seat opened** (same nick/session/worktree author). A green local pytest run is not a non-author MRB.

**FR #2604 / MRB #2607 (exact-seat):** chair `review_blocked_for_author` blocks **MRB** only for the exact author/implementer seat. A sibling seat on the same machine may take the MRB even when another machine looks live (UAT keeps the sibling-when-other-machine-free block). DONE FR must stamp the `/pull/` URL on the superseding MRB so `mrb_row_offerable` is true; resync skips draft open PRs (`skipped_draft`) and must not enqueue them as MRB jobs.

**FR #4496:** A fold or tip-fix commit on an open product tip keeps the existing tip author name and email for that commit only via `git -c user.name` and `git -c user.email` (copy `git log -1 --format`). Never commit as the reviewing seat nick. Do not change git config.

**FR assign is not self-MRB:** When this seat is later assigned the intake it just filed, implement that issue. Self-MRB applies only when this seat is assigned the MRB of a PR it opened or pushed.

Wire (preferred after you already ACK'd):

1. Confirm authorship: branch you pushed, PR head from this seat's FR promote, or a `lesson(<book>):` / harvest-lesson tip from this seat's `Invoke-BobiverseHarvest`.
2. Outbox: GIVEUP MRB owner/repo#N
3. Separate line: reason self-MRB - this seat opened PR #N; needs a different seat (and DIRTY/rebase needed when the head conflicts with main).
4. Harvest the lesson; do not open a second MRB from this seat on that PR.

If you spot self-MRB **before** any review work and have not ACK'd yet, NACK MRB owner/repo#N with the same reason is also valid (job-irc: NACK = decline before work). After ACK, always **GIVEUP** — never go silent.

**Harvest-lesson self-MRB (MRB #2732 / #2735):** a harvest-lesson PR opened from this seat's `Invoke-BobiverseHarvest` is self-MRB for that seat — NACK/GIVEUP and leave it for another seat.

## Harvest-lesson intake PRs (FR #2705 / FR #3299 / FR #3317)

Non-draft PRs labelled `harvest-lesson` with title `lesson(<book>): …` edit a skill book `SKILL.md` under `## Harvested lessons (intake)`. They are offerable MRB work (gitclaim must not treat them as draft/receipt harvests). The same owning-repo rules apply to draft `harvest:` / label `skill` PRs.

**FR #3317 — seats open harvest PRs in the owning skill book** (job/product/plan repo; Bob tooling stays bobiverse). MRB is a **light triage**, not a re-route. Cost cap: use the short checklist below; **no full test suite** unless the tip also touches code/tests.


**FR #4800 (CAST IRON):** harvest tip light-triage exits (FAIL-supersede / CLOSED not-useful / Duplicate / MOVED / plan-content) complete as **`DONE MRB … PASS <url>`**. Never `DONE FAIL` on those tips — FR #4718 would enqueue a FIX job for a tip that must stay closed unmerged. Chair also skips FIX when the PR is `harvest-lesson` and closed unmerged (or carries a FAIL-supersede/CLOSED/MOVED board).

**FR #4917 (CAST IRON):** do **not** open a `docs/mrb-N` pin for a lesson-of-lesson tip (CLOSED-duplicate / FAIL-supersede / light-triage meta / FIX of a pin). Do **not** harvest after FIX/MRB/re-DONE on `harvest-lesson` or `docs/mrb-*` PRs (`Invoke-BobiverseHarvest` skips; Jeeves does not offer those tips as MRB). First-level pin of a useful product lesson still OK.

**Short triage checklist (FR #3317):**

1. **Useful?** Adds a durable playbook an agent would re-run.
2. **Generalised?** Fleet-reusable, not a one-box anecdote.
3. **Non-duplicate?** Not already on main in this book (CAST IRON / product paragraph / earlier harvest tip).
4. **Vision / AGENTS fit?** Matches this repo's vision and harvest-home rules.
5. **Plan content?** Only how-to-plan lessons are harvests (exit below).

Exits: **PASS** → merge. **Not useful / off-vision** → close with a one-line reason; board **`MRB CLOSED - not-useful: …`** then `DONE MRB … PASS <url>` (CLOSED/MOVED count as done, not `mrb-fail`). **Duplicate / FAIL-supersede / CAST IRON already covers it** → close unmerged citing the skill-book link; board **`FAIL-superseded`** / **`MRB CLOSED`**; then **`DONE MRB … PASS <url>`** (FR #4800 — never `DONE FAIL` here: that queues FIX via FR #4718). **Wrong owner** (should be rare after direct filing) → step 0 / FR #3299 re-file / **MOVED** then `DONE MRB … PASS`.

**Plan-content exit (owner rule 2026-10-08, test case #3097):** A Plan-seat harvest (`seat=…-plan`, `plan-<yyyyMMdd-HHmmss>`, `Report-BobiverseIntakeIssue` from a plan folder) may only carry how-to-plan lessons: process, pitfalls, repo-setup steps. If it is **only plan content** (requirements, designs, architecture/product decisions, FR/issue lists, numbering maps), close it with the reason **`plan content, not a lesson`**. Board **`MRB CLOSED - plan-content: …`**. Do not re-file it, and do not hold it OPEN as `owner-missing`. If a genuine how-to-plan lesson sits inside, keep only that line (generalised, product names removed) and move it to `SimonBarnett/skills-visionary` (step 0, **MOVED**), then close the original with both the link and the reason.

On review:

0. **Who owns this lesson (owning repo)?** Decide from the job repo / product named in the lesson, the plan's product, and the skill-book ownership lines (`harvest-agent-skills` domain table and `github:` frontmatter, `harvest-skills-visionary`, product `AGENTS.md` harvest routing). Bob fleet tooling (chair, worker, intake, tray, harvest process) stays in bobiverse. **FR #4970:** a customer/project-specific lesson belongs in that customer's GitHub topic `priority-customer` repo (look the topic up; do not hard-code names). Test: "would this be true for every Priority customer?" Yes -> `SimonBarnett/agentic_fomprep`. No -> the customer repo (example: Rees Machinery forms/data -> `SimonBarnett/rees`). If a customer-specific lesson was filed to a general book (`agentic_fomprep`, bobiverse `harvest` / `harvest-agent-skills`, `a-search`, etc.), MRB **must not merge** it: twin-check the customer repo's main and open PRs, then re-file or close **MOVED** with the link. Reverse: a general Priority lesson filed into a customer repo is redirected to `SimonBarnett/agentic_fomprep`. **Owner is this repo:** continue with the short triage (and steps 1–10 when needed). **Owner is another repo that exists:** twin-check its main and open PRs; if the lesson is already there, link it; otherwise **re-file** as a branch + PR in that repo's skill-book layout (its `harvest-agent-skills` or the specific skill, plus `docs/skill-harvest-log.md`), linking the original; if a PR cannot be opened, file a `harvest:` issue there with the full text; then comment `Moved to owner/repo#N` on the original and close it; board verdict **MOVED owner/repo#N** (not FAIL), then `DONE MRB … PASS <assigned-url>`. **Owner repo does not exist yet** (planned product): leave the original **OPEN** with a comment naming the intended owner — do not FAIL-close it — **unless** it is plan content (checklist 5): plan content is closed with `plan content, not a lesson`, never held. Held bobiverse issues labelled `owner-missing` are not offerable until the repo exists (FR #3317). **Never** FAIL / FAIL-supersede / close a harvest PR as wrong-book unless the board cites a link where the lesson text actually sits (a skill book on main, or a reviewable skill-book PR). A product/FR PR does not count unless it carries the lesson text in a skill book.

1. Verify each lesson is generalised (fleet-reusable playbook, not a one-box anecdote).
2. Confirm it sits in the right `SKILL.md` (move or reword if the book/path is wrong) **after** step 0 confirms this repo owns it.
3. Then merge. Pure status receipts with no Lessons stay `receipt_recorded` and are never offered.
4. **Twin harvest-lesson PRs** for the same book/lesson: FAIL-superseded board, close the later PR citing the merged first; never merge the misplaced raw duplicate tip (MRB #2741 / #2747 / #2750). **FR #3414 / FR #3803:** select twins by **exact lesson/title needle** only (`-eq` / `.StartsWith` of the full title — never PowerShell `-match`, never a shared substring like `lessons that already live`); never a broad Phase-2/normalize/stack regex; when batch-closing wrong-book tips, each close comment cites that tip's own durable product/skill PR (not the assigned MRB URL unless exact twin).
5. **CAST IRON already covers it:** if the target book already has a CAST IRON / product paragraph for the lesson, FAIL-supersede and close as not planned — do not merge a weaker Harvested lessons duplicate (MRB #2732 / #2783). Cite the skill-book link on main (step 0).
6. **Tip current with main (MRB #2818 / #2823):** when `rev-list --left-right --count origin/main...HEAD` is `0` behind, merge directly after the book/path check — no behind-main fold required. Still open one `docs/mrb-N` hostile PR from the new main tip that pins contiguous skill phrases (for example `path_fn` / `events.jsonl`), prior intake bullets in the same window, and UTF-8/no-BOM.
7. **Nothing-queued `nak_s` product MRB (MRB #2825 / #2828 / FR #2806):** merge the **product** PR first, then open `docs/mrb-N` from the **new** `origin/main` tip with a `nak-beats-repeat_s` hostile pin (and skill contiguous FR #2806 / never-inject). First idle `!bored` cycle before `nak_due` is **ACCEPTABLE drift** when the worker skill already cites sooner-than-`repeat_s` — do not FAIL solely for that timing window. If intake parks this playbook under `harvest`, apply step 0 (re-file / move here); do not leave a second copy in harvest.
8. **Wrong-book bob-worker product lesson already on main (MRB #2826 / #2831):** if intake parks a bob-worker IRC/product classifier lesson under `common/.../harvest/SKILL.md` and the durable text is already on `main` in `bobiverse-bob-worker` (product + docs merge), **FAIL-supersede** and close the harvest PR unmerged — do not land a second copy in harvest. Do not re-home that product paragraph into this job-mrb book either; the worker skill is the home. Cite the superseding worker/product **skill-book** PR on the board (step 0: never FAIL-close without that link).
9. **FR #2811 giveup/hold hostile MRB (MRB #2832 / #2842 / #2850):** merge `origin/main` into the FR tip first. Hostile/docs pins: NQ skipped while `hold_assigns_while` is true; docs/mrb contiguous `**FR #2811:** while the harvest hold` window must be wide enough for `held_until_turn_end` / `post_bored`. Product/home text stays in `bobiverse-bob-worker` (+ job-irc as needed). If intake parks this MRB playbook under `harvest`, apply step 0 and move it here — do not leave a second copy in harvest (twin #2850 landed wrong-book; #2842 FAIL-superseded).
10. **Fold into existing Harvested playbook (MRB #2824 / #2844):** when the target product skill already has a `## Harvested … playbook` (or similar) section — for example `bobiverse-jeeves-monitor` beside FR #2803 Assign — fold thin intake lessons into that section next to the related FR docs; do not open a second thin heading. Still merge `origin/main` first when behind; put hostile pins on `docs/mrb-N` after the skill merge.
- When a seat finishes work on an intake tip or pin branch, do not file a new Harvested-lessons bullet; stamp Invoke-BobiverseHarvest source.version so overlays older than fr4780 refuse to post

## Skill / markdown diff hygiene (harvest #1616)

Hostile-read **skill and docs diffs line-by-line**, not only the code/tests. A mid-bullet or mid-paragraph insert that truncates a list item and leaves **orphan continuation text** (dangling clause on the next line, broken markdown list, severed mermaid/code fence) is an MRB **FAIL** even when pytest is green (MRB #1608 / fix #1610).

Checks:
1. Every changed SKILL.md / docs bullet still reads as a complete sentence/item.
2. Inserted bullets did not splice into the middle of an existing bullet.
3. No orphan lines that only make sense as the tail of a removed/split bullet.
4. Prefer a regression test that asserts a distinctive phrase from the restored bullet remains contiguous.
5. BEL / C0 control characters can corrupt product names in skill bullets (for example BEL + `"irc.exe"` makes `airc.exe` read as `irc.exe`). Hostile-pin the correct spelling (`airc.exe`) and reject the corrupted form (`irc.exe`) in the same AV / install window (FR #4215 / MRB #4220). Prefer ASCII wording; do not park this playbook under `harvest/SKILL.md` --- fold it here.

## Harvested MRB discipline

- **FR #4925 foreign `gh pr checkout`:** never checkout another repo's PR from the bob install CWD; use a `%TEMP%` worktree/clone. Install remote bobiverse + foreign `--repo` is a refuse/warn (`Assert-BobiverseForeignPrCheckout.ps1`).

- **FR #4906 conflict FIX re-offer:** conflict_blocked resync must call offer_dirty_conflict_fix (not bare enqueue_conflict_fix) so DONE same-SHA conflict FIX re-offers; !assign FIX accepts CONFLICTING/DIRTY even when checks are green.
 (skill records #1223-#1457)

- After a sibling merge leaves your MRB head CONFLICTING: merge `origin/main`, keep both soft-cap and StrictMode `@()` wraps; `Closes` only remaining open FRs when the twin is already closed (harvest #1694).
- Never let an unrelated docs/vendor/product PR `Closes` a `label:skill` harvest issue; strip wrong `Closes`, use `Refs`, close the harvest record separately when lessons are already on main (harvest #1674 / MRB #1660).
- When a harvest tip already closed the product issue, still PASS and merge the product tip. Note the early close as ACCEPTABLE. Reuse the docs/mrb hostile pin.
- When a docs/mrb hostile companion supersets an open product tip: PASS the assigned companion, keep `Closes` on the tip that lands product acceptance, re-arm `--auto`, and do not fold merely-behind MERGEABLE tips (FR #4649); product and companion may both carry auto-merge. (context: a-search MRB #3955 companion of #3953)
- A harvest tip that only restates a product MRB and whose body Closes the product issue is FAIL-superseded. Do not merge it: that merge would close the product issue while the product tip is still open. The durable home is the product tip. Put Refs on the harvest tip, not Closes.
- **Partial FR ACCEPTABLE drift (harvest #1663 / MRB #1645):** SkipTidy autostart PASS when TipForm Restart still tidies is intentional; leave explicit follow-up issues open; run `check_conflict_markers` before merge; fold `origin/main` only under FR #4649.
- **Offer-order fixtures + deferred precompute (MRB #3265 / tip #3269; tip #3273 / fix #3272):** hostile/FR tests for kind+number offer order must use full `owner/repo` pull URLs — bare repo ids can sort correctly in `ordered_unaccepted` while `mrb_row_offerable` skips them. After FR #3205 MRB-first order, fixtures that previously assumed the first offer was FR `#1` must assert against the **offered id** (not a hard-coded FR `#1`); merge the product PR, then one fix/docs PR. **ACCEPTABLE drift:** continuous background precompute may stay deferred when the zero-GitHub `!bored` path already lands via fresh precompute / resync / post-offer rebuild (FR #3205). Do not park this playbook under `harvest/SKILL.md` (move/fold here).
- **Helper already on main / env-only red synth (MRB #3145):** when the assigned FR’s code helper already landed via an earlier merge, **PASS** a remaining docs + dedicated-tests PR that still closes the issue acceptance. CDK/`npx cdk synth` fails on a seat without `aws-cdk` are **environment** — confirm the **same** fail on a clean `origin/main` checkout before treating them as product FAIL. If intake parks this under `harvest`, move it here.
- CONFLICTING/superseded duplicate PR: FAIL board, close the PR, DONE FAIL; never force-merge (harvest #1609). CONFLICTING with open acceptance still uses one fix/rebase PR. Mere CONFLICTING unique heads: merge main, resolve, re-test.
- After DONE PASS, if the fix PR races closed unmerged: open a land PR from the known-good tip onto current main, merge, verify `origin/main` contains the lesson (harvest #1981 / MRB #1847).
- CONFLICTING/superseded duplicate PR: FAIL board, close the PR, DONE FAIL; never force-merge (harvest #1609). CONFLICTING with open acceptance still uses one fix/rebase PR. Mere CONFLICTING unique heads: merge main, resolve, re-test. Harvest-log append races: keep both dated sections (FR #1757 / #1750).
- Skill/docs diffs: mid-bullet insert leaving orphan continuation text is FAIL even when code is green (harvest #1616 / MRB #1608).
- The implementing seat must GIVEUP self-MRB and ask the chair for a different seat; a green local test run is not a non-author MRB. Full wire: **Self-MRB** section above.

- MRB PASS requires the claimed tests, a clean/rebased branch, and the merged PR's `Closes` lines. When an acceptance contract changes, expect a focused fix/nits PR and rerun the hostile tests rather than accepting stale evidence.
- Chair side (FR #1585 / harvest #1613): an open GitHub pull must survive resync even if ledger `mrb_done` was stamped early — `mrb_already_done(pr_exists)` keeps open PRs; resync clears stale stamps.
- After merge: switch to `main`, fast-forward from `origin/main`, sync the installed tree, and restart only the relevant service. Do not treat a harvest/MRB record as a new FR row.
- **Behind-main + nits (harvest #1647 / MRB #1629 / harvest #2740 / FR #4649):** never fold just because the PR is behind; fold only when CONFLICTING/DIRTY or CI failed on a main-fixed issue; put additive hostile tests on `docs/mrb-N`; missing `Duplicates closed:` is a body nit (close harvest twins as not planned); PASS without a fix PR when only body/docs nits remain and tests are green. For Jeeves `!status` / frozen-VERSION style FRs, pin `Client.__init__` `_process_started` and `Build-Jeeves.ps1` `--add-data VERSION` (install-root resolve) on that docs/mrb-N PR (MRB #2733 / FR #2728).
- **Harvest promote MRB (harvest #2296 / MRB #2289):** merge skill PR first → then `docs/mrb-N` hostile-test PR from **new** `origin/main` → verify skill issue closed via `Closes` before DONE PASS.

## Harvest digest (lessons audit 2026-10-06)

Generalised from 372 harvested lessons that never reached this book (audit for FR #2705). The per-lesson table is in `common/docs/harvest-lessons-audit-2026-10-06.md`.

**Digest audit path (MRB #2718 / #2763 / #2765):** harvest-digest skill PRs that cite `common/docs/harvest-lessons-audit-2026-10-06.md` keep that citation when the file exists on the tip/`main`; if it is missing, drop the dead path on `docs/mrb-N` and pin digest bullets with a hostile test module (same pattern as docs/mrb-2717 for job-irc).

**Complementary digests (MRB #2719 / #2765):** FR #2705 job-mrb audit digest bullets that restate Self-MRB/CONFLICTING themes are complementary digests (PASS + pin on `docs/mrb-N`), not FAIL-duplicates; still drop a missing `harvest-lessons-audit-2026-10-06.md` citation on that docs PR.

- **Self-MRB is per seat, not per machine:** a seat that opened, authored or pushed commits to the PR under review (including a `docs/mrb-N` PR stacked on its own tip) must ACK then GIVEUP with `reason=self-MRB`. NACK only before any work, and never DONE PASS/FAIL. A sibling seat on the same machine may review. The chair stamps `author_seat`/implementer on DONE and on `edited`/`synchronize` webhooks; a seat that only cited another seat's PR is informational (`FRW`) and does not block review. (42 lessons: harvest #2310, #2247, #2222, #2219, #2217, #2213 +40 more, 5 held intake rows)
- **Re-offered or already-merged MRB:** ACK, then re-verify on `origin/main`: merge commit present, `Closes` closed the issue, claimed and parent tests green, board posted. DONE with the same verdict and the assigned PR URL. Do not merge again or open new worktrees. Additive hostile gates still go on `docs/mrb-N` from the new main tip. Repeated re-offers after DONE are a chair purge gap: comment on the existing issue. (79 lessons: harvest #2220, #2218, #2214, #2205, #2066, #2154 +68 more, 23 held intake rows)
- **CONFLICTING or superseded heads:** compare with main first. If the acceptance already landed through another PR, post a FAIL-superseded board, close the duplicate and DONE citing the assigned URL. Never revive a closed head and never force-merge. If the head is unique, merge `origin/main` keeping both sides (for example both dated `skill-harvest-log` sections and both `Claim` fields), re-test, then merge. Fix PRs branch from `origin/main` after the original merges. When two open PRs fix the same gap, keep the fuller one and FAIL-close the subset. (109 lessons: harvest #2316, #2288, #2271, #2259, #2255, #2249 +101 more, 13 held intake rows, 1 recovered receipt)
- **Pre-merge hygiene gates:** run `check_conflict_markers.py` (or grep `^<<<<<<<`) before every merge. Reject mojibake, C0 controls (a `\x08` that eats the first letter of a book name), new files without a trailing newline, and unreachable code after `return`/`raise`. New `.py`/`.ps1` read by WinPS must be ASCII, or carry a BOM where the encoding gate demands one. Write `gh pr` and board bodies with `--body-file` as UTF-8 without BOM so `Closes` still links. (35 lessons: harvest #2169, #2041, #2038, #2021, #2009, #1856 +17 more, 12 held intake rows)
- **FR #4718 MRB FAIL queues FIX:** when the newest board is FAIL at the live head and no linked fix PR is open, resync and DONE MRB FAIL queue one FIX (not another MRB); stamp the failing seat so it is not re-offered; `!assign FIX` accepts green PRs with that board. Worker seats still open exactly one fix PR when they can. **FR #5142:** the FIX seat pushes that companion commit onto the assigned tip and closes the companion as duplicate so the original PR carries the fix (example: FIX#5138 tip fa47fb8a, companion #5139 closed). **FR #4800 carve-out:** harvest-lesson tips closed unmerged with FAIL-supersede / CLOSED / MOVED / not-useful boards must `DONE MRB … PASS`; chair skips FIX enqueue for those tips even if a seat mistakenly posts `DONE FAIL`.
- **Hostile tests:** merge the product PR first, then put additive hostile tests on `docs/mrb-N` from the new main tip, and gate that commit on the pytest exit code. Prefer behavioural tests to string-contains checks: a PR that claims `assign_row` acceptance needs a test that calls `assign_row`. Parse PowerShell Assert scripts as well. Overlapping hostile suites from an earlier docs PR are additive, not a FAIL. (27 lessons: harvest #2264, #1362, #1146, #716, #1051, #590 +3 more, 17 held intake rows, 1 recovered receipt)
- **Verdict boards are not FR work:** issues labelled `mrb-pass` or `mrb-home` (verdict and home boards) get ACK then GIVEUP or DONE with the issue URL, and are never implemented. `mrb-fail` remediation issues have been offerable FR work since #2464. MRB-checklist issues assigned as FR: run the verify suite, comment the evidence and close; an FR seat never merges the target PR. (77 lessons: harvest #2297, #2281, #2162, #1957, #1872, #1713 +92 more, 21 held intake rows, 2 recovered receipts)
- **Prove the claim literally:** routing claims need explicit cases (empty labels, line-text skip, pull-URL repo match). State transitions must fire at the right wire event (`on_offer` at assign, `on_ack` only on ACK, no fan-out of remaining work to every seat). Intentional agent-overlay ordering, such as keep-the-flow first, is not a nit. (3 lessons: harvest #775, #723, #614)
