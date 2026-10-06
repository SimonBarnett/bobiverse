---
name: bobiverse-bob-job-mrb
description: >
  The single skill for MRB jobs - process diagram from Jeeves assign through ACK, vision-first tests-first hostile review and drift check, docs review, one docs or fix PR and merge to DONE; steps, evidence required, who owns what (the originating agent owns the hostile MRB).
---

# bobiverse bob - MRB job (hostile review)

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

**Job type `MRB`** (Material Review Board) - hostile, tests-first review of a pull request against the FR and the repo vision. Wire format and timing: `bobiverse-bob-job-irc`. The MRB is done by a **different seat or a fresh session** than the one that wrote the PR; the originating agent owns the review. An assigned MRB job authorises you to merge **that PR** (and its one docs/fix PR) - nothing else.

## Process

```mermaid
flowchart TD
  A["Jeeves assign: nick: MRB owner/repo#N url"] --> B["ACK MRB owner/repo#N (outbox, at once)"]
  B --> C["gh pr checkout in a temp worktree; read PR intent + changed files"]
  C --> D["Find the vision: VISION.md, brief, README, CAST IRON rules; quote 1-2 lines"]
  D --> E["Add NEW tests for the PR BEFORE the verdict"]
  E --> F["Run existing + new tests; hostile review; drift check; UTF-8/no-BOM check"]
  F -->|"tests or drift FAIL"| G["Exactly ONE separate fix PR"]
  G --> H["Merge original + fix PR"]
  F -->|PASS| I["Review README/skills/docs/mermaid for stale text"]
  I -->|stale| J["ONE separate docs/mrb-N PR"]
  I -->|ok| K["Merge the PR"]
  J --> K
  H --> L["Post the MRB board: verdict, drift line, evidence, links"]
  K --> L
  L --> M["Verify the originating issue: closed by the merge, or the PR carries Closes owner/repo#N"]
  M -->|"not closed (non-default branch / link missing)"| M2["Worker closes the issue with a comment: PR url + verdict"]
  M -->|"closed, or linked and merge pending"| P["Hand off: repo UAT is queued by Jeeves only when the whole repo is clear (no per-PR UAT)"]
  M2 --> P
  P --> N["DONE MRB owner/repo#N PASS-or-FAIL pr-url  (nothing after the url)"]
  N --> O["Program posts !bored - next job"]
  B -. cannot or blocked .-> X["NACK / GIVEUP MRB owner/repo#N + reason on its own line"]
```

## Steps

1. **ACK.** 2. Check out the PR in a temp worktree; read the intent, the FR and every changed file. Before `git worktree add`, if `Get-PSDrive C` FreeGB is under 2, run `..\scripts\Clear-BobiverseJobWorktrees.ps1 -RepoRoot <ai root>\bob` (FR #877). **CAST IRON (FR #2727):** never hand-delete / `Remove-Item` paths Clear did not select; if FreeGB stays under 2 after Clear, file an intake disk issue and put the MRB tree on a roomy drive (or GIVEUP) — do not invent a `C:\ai\*` delete list. After DONE, prune again with `-KeepPath` omitted so the MRB tree can go. 3. **Vision first**: read `VISION.md`/brief/README/AGENTS and quote 1-2 lines the PR is judged against. For **bob** ear/worker/tray changes prefer **`bob/VISION.md`** (FR #1615 / harvest #1632); the fleet umbrella stays `common/docs/vision.md` — do not treat the umbrella as the bob product vision.
No vision found: record "no vision source found", review against README + FR, and file ONE FR asking for a `VISION.md`. If the PR shows the vision itself should change, do not edit it - file an FR tagged `vision` for the owner.
4. **Tests before verdict**: add the new tests the PR needs, then run existing + new. **FR #2655 (airc PRs):** before PASS, run the full `airc/tests` suite (not only the new FR file) — signature changes like `send_privmsg(..., flood=)` break 2-arg monkeypatch stubs elsewhere. 5. Hostile review + **drift check** (separate verdict line): serves the stated vision? contradicts CAST IRON / earlier decisions? scope creep? under-delivery (letter, not intent; code never wired)? Drift is a FAIL like a red test. **ACCEPTABLE drift (harvest #1663):** a partial FR that lands the core acceptance and files explicit follow-up issues for the remainder (e.g. SkipTidy autostart PASS while TipForm Restart still tidies; leftover #1642/#1643) may PASS — say so on the drift line; do not FAIL solely for intentional scoped follow-ups.
6. Encoding: changed *.md are UTF-8 without BOM (no mojibake). **CAST IRON (FR #1634):** before every gh pr merge, run python common/scripts/check_conflict_markers.py --root <worktree> (or rely on the check-conflict-markers CI workflow) and **refuse merge** if any <<<<<<< / ======= / >>>>>>> conflict markers remain in the tip. **Behind-main (harvest #1647 / #1657):** if the PR head is behind origin/main, merge (or rebase) origin/main into the FR branch and re-run conflict-marker + tests **before** gh pr merge. 7. **PASS** -> review docs/skills/usage text for staleness; if stale open exactly ONE **separate** docs/mrb-<N>-... PR (never push onto the PR under review) and merge both; if not, merge the PR. Additive hostile tests that are not product fixes belong on that docs/mrb-N PR. **Body/docs-only nits** (e.g. missing Duplicates closed: line) while tests are green: PASS and merge without a separate **fix** PR — put wording nits on the docs PR or edit the PR body; close harvest twins as not planned (Duplicate of #N / fixed by PR #M).
**Harvest promote order (harvest #2296 / MRB #2289):** merge the **skill/promote PR first**, then open the one `docs/mrb-N` hostile-test PR **from the new `origin/main` tip** (not from the pre-merge promote tip). Before **DONE PASS**, verify `gh issue view` that `Closes` actually closed the skill issue (or close it with a comment). Example: #2289 then docs #2295.
**FAIL** -> exactly ONE separate fix PR, then merge original + fix (not several fix PRs). Never merge UNSTABLE/red. 8. Post the MRB board. **Issue closure (t826u):** the assigned MRB authorises you to merge that PR (and its one docs/fix PR). On merge, the PR's **`Closes <owner>/<repo>#N`** line closes the originating issue - confirm that line is in the PR body (add it by editing the body if the FR author missed it; a fix/docs PR gets `Refs`, never a second `Closes`). If you are **not authorised to merge**, still confirm the `Closes` link so the issue closes when the owner merges, and say so on the board.
After the merge check `gh issue view N --repo <owner>/<repo> --json state`: if it is still open (PR merged into a non-default branch, or the link was missing) **close it yourself with a comment** (`gh issue close N --comment "Closed by <PR url> (merged into <branch>). MRB: <verdict>"`). **FR #791:** `gh issue close` does not accept `--body-file` (unknown flag) — use `-c` / `--comment` only. A FAIL that ends without a merge leaves the issue open.
9. Hand off: there is no per-PR UAT - Jeeves queues ONE repo-level UAT once every issue is closed and every PR is merged. 10. **DONE** - only after the issue is verified closed, or (not merged yet) verified linked via `closingIssuesReferences`.

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

`repo_layout` lives in `common/scripts/repo_layout.py`. Prefer `git sparse-checkout disable` in the MRB temp tree. Partial sparse sets must include `common/scripts`; do not rely on `PYTHONPATH=common/tests`. Service `*/tests/conftest.py` puts `common/scripts` on `sys.path`.
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
* **Never merge conflict markers (FR #1634):** tip must be clean of `<<<<<<<` / `=======` / `>>>>>>>`; use `common/scripts/check_conflict_markers.py`. Merge/rebase `origin/main` into behind branches before merge; harvest twins close as not planned. * Report which agent and model did the review. * CAST IRON harvest rule at the top: file every issue/FR/bug you find in the same turn - findings that are not part of this PR become new intake items.


## CONFLICTING / superseded MRB (harvest #1609)

**CONFLICTING alone is not an automatic FAIL.** If this PR is still the unique fix: merge `origin/main` into the tip, resolve markers, re-run tests + `check_conflict_markers.py`, then continue the normal PASS/FAIL review.

**skill-harvest-log.md (FR #1757 / #1750 / harvest #2274):** harvest/promote PRs that append dated sections to common/docs/skill-harvest-log.md race each other. Rebase onto main before merge; when both sides added sections, **keep both dated sections** in the one fix/rebase PR (MRB #1741 -> #1750). Dropping the other promote's section is a FAIL. If the **fix PR itself** goes CONFLICTING against newer `main` before you REST/`gh pr merge`, merge `origin/main` into the fix tip and **keep-both again**, then re-check markers/tests, then merge (do not REST-merge a dirty tip). Example: MRB #2241 → fix #2272.

When the assigned PR is already **closed**, or a **duplicate/superseded** of work already on main (twin FR closed by another merge) — including when that duplicate head is also CONFLICTING:

1. Confirm the superseding merge: `gh pr view` / `gh issue view` — lessons and originating issues already landed (`Closes` / merged PR URLs).
2. Do **not** force-merge, rebase-to-revive, or re-open the duplicate head.
3. Post an MRB board with verdict **FAIL** (or FAIL-superseded): cite the merged PR(s) that already satisfy acceptance.
4. Close the duplicate/conflicting PR with a comment pointing at the superseding merge.
5. If the originating issue is still open only because this duplicate never merged, close it citing the merged fix URLs (not this PR).
6. **DONE MRB owner/repo#N FAIL <assigned-pr-url>** — nothing after the URL.

**Harvest-lesson twins:** the same rule applies when two `lesson(<book>):` / `harvest-lesson` tips carry the same playbook — FAIL-superseded the later one; never merge the misplaced raw duplicate tip into `harvest` when the playbook belongs (or already landed) in `bobiverse-bob-job-mrb` (MRB #2741 / #2747 / #2750).

Self-MRB remains a separate hand-back (GIVEUP / NACK); this section is for hostile review of a head that lost the race to main.

## Fix-PR race after DONE (harvest #1981 / MRB #1847)

After you **DONE PASS** a FAIL-fixed MRB, the one fix PR can still race **CONFLICTING** and be closed **unmerged** (parallel main moves). Before ending the seat:

1. Confirm the fix tip actually landed: `git fetch origin main` and `git show origin/main:<path>` / pytest for the lesson markers.
2. If the fix PR is closed unmerged or main lacks the lesson, immediately open a **land PR** from the known-good tip (or cherry-pick the fix commit tree) onto current `main`, merge it, and verify `origin/main` again.
3. Post a short follow-up board comment on the assigned PR citing the land PR URL.
4. Do **not** force-push an empty main tip onto the fix branch; do **not** close originating issues until the lesson is on `main`.

## Self-MRB (harvest #1603 / MRB #1578)

Never hostile-review or merge a PR **this seat opened** (same nick/session/worktree author). A green local pytest run is not a non-author MRB.

**FR #2604 / MRB #2607 (exact-seat):** chair `review_blocked_for_author` blocks **MRB** only for the exact author/implementer seat. A sibling seat on the same machine may take the MRB even when another machine looks live (UAT keeps the sibling-when-other-machine-free block). DONE FR must stamp the `/pull/` URL on the superseding MRB so `mrb_row_offerable` is true; resync skips draft open PRs (`skipped_draft`) and must not enqueue them as MRB jobs.

Wire (preferred after you already ACK'd):

1. Confirm authorship: branch you pushed, or PR head from this seat's FR promote.
2. Outbox: GIVEUP MRB owner/repo#N
3. Separate line: reason self-MRB - this seat opened PR #N; needs a different seat (and DIRTY/rebase needed when the head conflicts with main).
4. Harvest the lesson; do not open a second MRB from this seat on that PR.

If you spot self-MRB **before** any review work and have not ACK'd yet, NACK MRB owner/repo#N with the same reason is also valid (job-irc: NACK = decline before work). After ACK, always **GIVEUP** — never go silent.

## Harvest-lesson intake PRs (FR #2705)

Non-draft PRs labelled `harvest-lesson` with title `lesson(<book>): …` edit a skill book `SKILL.md` under `## Harvested lessons (intake)`. They are offerable MRB work (gitclaim must not treat them as draft/receipt harvests).

On review:
1. Verify each lesson is generalised (fleet-reusable playbook, not a one-box anecdote).
2. Confirm it sits in the right `SKILL.md` (move or reword if the book/path is wrong).
3. Then merge. Pure status receipts with no Lessons stay `receipt_recorded` and are never offered.
4. **Twin harvest-lesson PRs** for the same book/lesson: FAIL-superseded board, close the later PR citing the merged first; never merge the misplaced raw duplicate tip (MRB #2741 / #2747 / #2750).

## Skill / markdown diff hygiene (harvest #1616)

Hostile-read **skill and docs diffs line-by-line**, not only the code/tests. A mid-bullet or mid-paragraph insert that truncates a list item and leaves **orphan continuation text** (dangling clause on the next line, broken markdown list, severed mermaid/code fence) is an MRB **FAIL** even when pytest is green (MRB #1608 / fix #1610).

Checks:
1. Every changed SKILL.md / docs bullet still reads as a complete sentence/item.
2. Inserted bullets did not splice into the middle of an existing bullet.
3. No orphan lines that only make sense as the tail of a removed/split bullet.
4. Prefer a regression test that asserts a distinctive phrase from the restored bullet remains contiguous.

## Harvested MRB discipline (skill records #1223-#1457)

- After a sibling merge leaves your MRB head CONFLICTING: merge `origin/main`, keep both soft-cap and StrictMode `@()` wraps; `Closes` only remaining open FRs when the twin is already closed (harvest #1694).
- Never let an unrelated docs/vendor/product PR `Closes` a `label:skill` harvest issue; strip wrong `Closes`, use `Refs`, close the harvest record separately when lessons are already on main (harvest #1674 / MRB #1660).
- **Partial FR ACCEPTABLE drift (harvest #1663 / MRB #1645):** SkipTidy autostart PASS when TipForm Restart still tidies is intentional; leave explicit follow-up issues open; still merge `origin/main` and run `check_conflict_markers` before merge.
- CONFLICTING/superseded duplicate PR: FAIL board, close the PR, DONE FAIL; never force-merge (harvest #1609). CONFLICTING with open acceptance still uses one fix/rebase PR. Mere CONFLICTING unique heads: merge main, resolve, re-test.
- After DONE PASS, if the fix PR races closed unmerged: open a land PR from the known-good tip onto current main, merge, verify `origin/main` contains the lesson (harvest #1981 / MRB #1847).
- CONFLICTING/superseded duplicate PR: FAIL board, close the PR, DONE FAIL; never force-merge (harvest #1609). CONFLICTING with open acceptance still uses one fix/rebase PR. Mere CONFLICTING unique heads: merge main, resolve, re-test. Harvest-log append races: keep both dated sections (FR #1757 / #1750).
- Skill/docs diffs: mid-bullet insert leaving orphan continuation text is FAIL even when code is green (harvest #1616 / MRB #1608).
- The implementing seat must GIVEUP self-MRB and ask the chair for a different seat; a green local test run is not a non-author MRB. Full wire: **Self-MRB** section above.

- MRB PASS requires the claimed tests, a clean/rebased branch, and the merged PR's `Closes` lines. When an acceptance contract changes, expect a focused fix/nits PR and rerun the hostile tests rather than accepting stale evidence.
- Chair side (FR #1585 / harvest #1613): an open GitHub pull must survive resync even if ledger `mrb_done` was stamped early — `mrb_already_done(pr_exists)` keeps open PRs; resync clears stale stamps.
- After merge: switch to `main`, fast-forward from `origin/main`, sync the installed tree, and restart only the relevant service. Do not treat a harvest/MRB record as a new FR row.
- **Behind-main + nits (harvest #1647 / MRB #1629 / harvest #2740):** merge `origin/main` into the FR branch before merge; put additive hostile tests on `docs/mrb-N`; missing `Duplicates closed:` is a body nit (close harvest twins as not planned); PASS without a fix PR when only body/docs nits remain and tests are green. For Jeeves `!status` / frozen-VERSION style FRs, pin `Client.__init__` `_process_started` and `Build-Jeeves.ps1` `--add-data VERSION` (install-root resolve) on that docs/mrb-N PR (MRB #2733 / FR #2728).
- **Harvest promote MRB (harvest #2296 / MRB #2289):** merge skill PR first → then `docs/mrb-N` hostile-test PR from **new** `origin/main` → verify skill issue closed via `Closes` before DONE PASS.
