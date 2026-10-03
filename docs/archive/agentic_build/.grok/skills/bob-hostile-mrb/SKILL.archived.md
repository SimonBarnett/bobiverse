<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-hostile-mrb/SKILL.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-hostile-mrb
description: >
  Hostile Material Review Board of a worker PR as a GitHub issue. Bob hands
  the review off (Cursor Models, then grok.exe). He does not write the MRB
  in-session. STANDARD worker steps: bob-mrb-worker (tests-first + vision/drift
  FR #351; after PASS review docs and merge one separate docs/mrb-<n> PR when
  needed; FAIL â†’ exactly one fix PR then merge both). No MRB PDFs. Use when the
  user says MRB, hostile review, review the push, ready for UAT, hand off MRB,
  missing features, or /bob-hostile-mrb. Loop table is bob-build-loop.
github: https://github.com/SimonBarnett/agentic_build
---

# Hostile MRB (GitHub issue)

Foundation: `harvest-agent-skills` (honesty box) -> report back to
https://github.com/SimonBarnett/agentic_build.

Git (the product repo's issues + `docs/feature-request-*.md`) is the single
source of truth. **Do not generate `docs/mrb-*.pdf`.** Loop table:
`bob-build-loop`. **Worker process STANDARD:** `bob-mrb-worker` (mermaid +
vision/drift + PASS docs review/merge / FAIL one-fix-PR).

## Shop IRC (every MRB worker)

Load skill `bob-shop-worker` as soon as this process starts on a fleet box.
JOIN `#<machine-id>` as `w-<shortid>-<pid>`. Set `working_on` from the FR
title. POST `reportUrl`. Do not JOIN `#bobiverse`. Do not `!report`.
Conversation stdout â†’ shop. Thinking/tool traces â†’ open Query only.
On exit QUIT the shop. Canon: agentic_irc #46 / this repo #124.

## Bob hands off (do this first)

Bob **does not write** the review in Grok Bot / this grok.exe session.
The implementer does not review their own PR (**FR #343**: FR mode opens
the PR and **never** `gh pr merge`; MRB is a **different** seat or fresh
session â€” `docs/fr-mode-no-self-merge.md`). Dispatcher runs
`tools/Start-BobBuildLoop.ps1` (skill `bob-job-loop`) or, for a single
SHA, starts a **new** MRB worker (`Start-BobMrbHandoff`, `-Kind mrb`) as
soon as the PR exists. The driver comments the new URL on the prior FAIL
board.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Start-BobMrbHandoff.ps1 `
  -Repo owner/repo -Issue <feature-request-n> -Sha <pr-head> -Cwd C:\ai\<repo> `
  -Docs docs/feature-request-....md -Plan docs/build-and-test-plan.md
# default -Fuel cursor-models; grok-build only when Cursor Models remaining is 0
# or cursor-agent is missing
```

Default is Cursor Agent (`cursor-agent.cmd`, never `~\.grok\bin\agent.exe`)
on Cursor Grok (`config/default.json` `models.mrbCursor`, `grok-4.6`).
Grok Build fallback uses `models.mrbGrok` (`grok-4.6` on grok.exe). PR
workers use Composer `composer-2.5` or `build0.1` / `grok-4.5`. Never Other
Models. Copilot only with `-AllowCopilot`.

**Grok-build fallback is dispatcher-local until issue #11.** Run the handoff
on the machine that will post.

After a FIX **PR**, hand off **again** only when a **new** head still needs
a separate board (legacy multi-cycle). Under `bob-mrb-worker`, FAIL opens
**exactly one** fix PR and the same MRB seat merges original + that fix â€”
do not spawn a chain of FIX workers.

IRC verb `MRB <job> <nick>` is the machine nick; fuel is in the job file.

**Chair:** only Bob may declare **ready for human UAT**. Worker posts `FAIL`
or `PASS` / `PASS-nits` only (board titles may still use `PASS-nits`).
PASS **includes merge**. If the worker thinks it passed UAT, they write
`candidate PASS-UAT, Bob stamp required`.

## STANDARD worker process â†’ `bob-mrb-worker`

1. Use `gh pr checkout` in a temporary worktree; read intent + changed files
2. Read vision (VISION.md / BRIEF / README / CAST IRON / Three Laws); quote lines
3. BEFORE testing: add any NEW tests appropriate to the PR
4. Run existing + new tests; hostile review + **drift check** (FR #351)
6. PASS â†’ review docs; if stale, separate `docs/mrb-<n>` PR (never push onto the
   reviewed branch); merge; close FR; UAT handoff; only Bob stamps UAT
7. FAIL â†’ exactly ONE separate fix PR, then merge original + fix
8. Jeeves announces whatever happens (merge / fix+merge)

Shop channel only. Report **agent + model** on the webhook. Full mermaid
and free-agent harvest CAST IRON: `bob-mrb-worker`.

## PASS / PASS-nits MUST close, merge, and pull (Simon 2026-09-22 â€” VERY important)

A PASS that leaves git dirty is not finished. The MRB worker MUST,
in this order, before the driver prints DONE:

1. After PASS, review README, skills, `docs/`, mermaid diagrams, and
   usage/help text against the new behavior. If stale, open exactly one
   **separate** `docs/mrb-<n>-...` PR against `main` (never push onto the
   reviewed branch â€” FR #348); merge that docs PR together with the reviewed
   PR. If docs are fine, merge the reviewed PR as before (`gh pr merge --merge`).
   Do not claim merged unless the required merge command succeeded (or
   `gh pr view` is already MERGED). Guard: `tools/mrb_docs_branch_guard.py`.
2. **Close finished issues**: the feature-request issue, **every** prior
   FAIL MRB board for this FR, and this PASS board. Each close
   comment links the merged PR URL.
3. **Pull completed PRs** on the product checkout and isolated worktrees
   (`git fetch` + fast-forward `main` / default branch to the merge SHA).
   The next FR must not start on stale main. Dispatcher verifies
   `origin/main` contains the merge commit before `start_build` on a
   remaining issue.

The loop finish race (`FAILED: PASS-nits finish: PR still open after gh
pr merge`) is not a reason to skip close/pull. If the PR is already
MERGED and the FR is CLOSED, treat DONE, then still pull.

## recycle-after-merge (Simon 2026-09-23 â€” merger owns live fleet)

Anyone merging `agentic_build` or `agentic_irc` to **main** (MRB
worker or Bob) must **recycle-after-merge** so live boxes are not left on
the old tree. Sister FR: `agentic_irc` #168 (`agentic-irc` / `bob-irc`
skills); this skill owns the MRB merger duty on `agentic_build`.

After merge, close, and pull (above), before the driver prints DONE:

4. **Recycle live machines**: merger (or Bob) recycles Watch-Bobiverse,
   Bob Fleet tray, and agent seats on affected fleet boxes â€” pull `main`
   at the merge SHA, then roll watchers / tray / seats per local playbook.
5. **ionos restart IRC when required**: when the merged change is not
   tray-only, notify **ionos** to restart IRC altogether (Ergo / bobircd /
   chair). Merger decides tray-only vs full IRC restart; exact notify
   transport is UNKNOWN (`agentic_irc` #152).

**Implementer PR workers do not live-recycle.** Document the duty in skill
and FR only. Bob or ionos runs recycle / IRC restart after merge to main â€”
not a worker on DEV1 (or any non-merger seat) calling live `!recycle` at
another box.

Escape hatch: if Cursor Agent and grok.exe both cannot start, Bob writes the
MRB himself using the rest of this skill. Say that in the issue.

## Tone (worker)

Detailed and brutal. No credit for intent. Success gates in the feature
request and `docs/build-and-test-plan.md` are the law.

## Source of truth

1. The **feature-request GitHub issue** and/or `docs/feature-request-<slug>-YYYY-MM-DD.md`.
2. The **build-and-test plan** in `/docs`.
3. The **PR diff** vs that request.
4. **Open issues** labeled `feature-request`.

If there is no issue yet: `gh issue create` with label `feature-request`,
then MRB comments on that issue (or a child labeled `mrb`).

## Missing features (every MRB)

Before the verdict, walk:

1. MUST / MUST NOT / acceptance IDs on **this** FR + plan vs the PR.
2. Other open GitHub issues vs `/docs` vs the PR head.
3. Holes the PR made visible that **no** FR covers.

| Gap | Action |
|---|---|
| This FR's acceptance still red | **Required fix** on this MRB issue. Fold into the **one** fix PR (`bob-mrb-worker`). Do not open a second FR for the same MUST. |
| Adjacent / unspecified hole, or an issue with no intake doc | **Request it**: park via `bob-spec-intake`. Link from **Missing features**. Dispatcher starts a **new** worker for that FR. |
| Already parked issue+doc, not in this PR | List under Missing features with the issue URL. Do not duplicate. Dispatcher starts a **new** worker if none is running. |

Do not implement unrelated missing features in the MRB job beyond the
single fix PR for this FAIL. Listing alone is not enough for parked FRs â€”
the dispatcher must hand remaining FRs to new workers (`bob-job-loop`).

## Worker steps

Score the review SHA only. If the shared checkout HEAD is a different
job, add a detached worktree at that SHA. Do not `reset` / `checkout`
away from another worker's branch. Do not score later commits or dirty
files. A GitHub `CONFLICTING` PR is FAIL even when this SHA's
acceptance is green in isolation: PASS includes `gh pr merge`.
Re-read `mergeable` immediately before posting PASS. A stale
`CLEAN` can go `DIRTY` while the board is written. If `gh pr merge`
then fails, that PASS is void: open a **new** FAIL issue on the
same SHA (do not reuse the pass board). Comment the FAIL URL on the
voided issue. If you then see the **same PR already MERGED** (another
worker scored a later head, or `gh pr view` is MERGED), close that
leftover FAIL with the merged PR URL. Do **not** start FIX. Pull
main. Do not claim you merged unless your `gh pr merge` succeeded.
`gh pr merge` can print `already merged` and still exit 0. That is
not this worker's merge. Parse stdout. Do not write `Merged <url>`
unless this process created the merge commit.

1. Diff the PR against the parked feature request and plan.
2. Run the missing-features check. File any new FRs before or with the MRB post.
3. Run or cite automated evidence (Test-Pack, CI). Note what was **not** run.
4. Post **only** with `tools/Start-BobMrb.ps1` (never `gh issue create`):
   - `-Verdict FAIL` or `PASS-nits`; title slug + `-Sha`; body sections as below.
   - **PASS-nits requires `-PrUrl`** â€” the script **merges that PR before** creating the
     `mrb-pass` issue. If merge fails, post **FAIL** instead.
   - Body: **Verdict**, **Feature request**, **Missing features**, **Blockers**, **Nits**, **Evidence**, **Required fixes**, **PR**
   - Worker must not use verdict `PASS-UAT` (Bob stamp).
6. **FAIL:** do not leave the original PR unfixed. Create **exactly one**
   fix branch/PR with the fix (+ new tests). Merge **original PR + that
   one fix PR**. Jeeves announces both. Do not open multiple fix PRs.
   Do not reuse this FAIL issue as a second board for another fix cycle.
7. **PASS:** complete the docs review above, merge the original plus any one
   docs PR (`gh pr merge --merge`), and keep nits listed; they do not block
   the merge. After merge succeeds, close the feature-request issue, **every**
   prior FAIL MRB board for this FR, and this PASS issue. Each close comment
   links the merged PR URL. Jeeves announces, then a separate UAT worker is
   handed off; only Bob stamps UAT.
8. **Remaining issues / feature requests:** after PASS or FAIL+merge, the
   dispatcher must pass work to **new** workers for **any other open
   actionable issues** â€” not only those labeled `feature-request` (Simon
   2026-09-22). Skip pure MRB meta boards. Missing features just parked
   count. Listing under Missing features is not enough â€” hand each to
   `bob-job-loop`. Remaining issues do not block this merge.
9. **No Bob, still open issues â€” do not sit (Simon 2026-09-22):** if you
   just MRB'd and Bob is not on channel / not assigning, **do not leave
   remaining open issues idle**. Find someone: ask `#bobiverse` for a
   spare seat, or launch the next `bob-job-loop` yourself on another
   open actionable issue. Waiting for Bob to notice is a bug. Harvest
   this playbook when you learn it (`harvest-agent-skills`).

## Pass bar

- Feature-request MUST / MUST NOT honored
- **Vision / drift (FR #351):** change serves the quoted vision lines; no CAST
  IRON / Three Laws contradiction; no scope creep or under-delivery
- Plan phases claimed as done have evidence
- New tests appropriate to the PR were added and run
- Missing features either requested (issue+doc) or explicitly out of scope
- Prior version folders intact on feature work
- No secrets in repo or prompts
- README, skills, `/docs`, mermaid diagrams, and usage/help text match reality
- Any stale docs are corrected in exactly one **separate** `docs/mrb-<n>` PR
- PR is merged by this MRB worker

## Fail bar (examples)

- ok=true without the documented gate
- **Drift:** tests pass but change contradicts repo vision / CAST IRON (FR #351)
- Invented APIs
- Breaking v1 while adding v2
- Empty errors[] on failure paths the spec requires
- Code landed with no FR, or an open issue with no intake doc, and the MRB did not request them
- Worker pushed `main` or merged their own implementer PR without MRB
- Multiple fix PRs for one FAIL (violates `bob-mrb-worker`)
- Docs commits pushed onto the PR under review (violates FR #348)
- Bob wrote the full MRB in-session when Cursor Agent or grok.exe could take it
