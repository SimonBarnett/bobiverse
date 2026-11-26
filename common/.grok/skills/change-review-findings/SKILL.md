---
name: change-review-findings
description: >
  Write a change review as concrete findings, after reading the code the
  diff touches (callers, callees, tests), not only the patch. Rank Must fix
  (bug, security, data loss, breaks at expected load), Should fix (missing
  test, real slowness, duplication, unneeded code), and Nice to have.
  Each finding has what this is, the problem, the smallest fix, and what
  happens if we skip it. Use on MRB, FR self-review, FIX review, or
  "review this change".
depends_on: []
---

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

# Change review findings

Adapted from Ponytail's review skill (MIT, Copyright (c) 2026 Dietrich Gebert,
https://github.com/DietrichGebert/ponytail). Fleet rules below win if they conflict.

This is a findings format. It does not replace `bobiverse-bob-job-mrb`.
Hostile MRB still owns vision-first review, tests-first, drift, docs, CodeRabbit
stamps, PASS/FAIL, and merge. When a CodeRabbit light review is in force, do not
do a full line-by-line re-read of the diff; still use this format for the
findings you do raise. This skill changes no code.

## 1. Understand first

- Review what the job names: a PR, a branch, uncommitted changes, or files.
  Nothing named: the assigned PR, else uncommitted changes, else the last commit.
- Read the diff, then the code it touches: callers of every changed function,
  the functions it calls, the tests, and the relevant README or vision lines.
- Trace the real flow: where data comes in, what is stored, what goes out.
- A change can break code it does not touch. When a signature, return value or
  behaviour changes, grep every caller.
- Judge scale against the load the repo actually expects. Say which load you assumed.

## 2. Look for

1. Bug: wrong result, crash, missed edge case, a caller broken by the change, a
   fix in one caller while the shared function stays broken.
2. Risk: injection, weak randomness, secrets, missing checks on user input, data
   loss (swallowed errors, writes in the wrong order, no transaction).
3. Scale: check-then-write races, work done by every process, memory that only
   grows, a query per item, per-process state that must be shared.
4. Missing test: risky new logic with no test that fails when it breaks. One good
   test, not coverage. MRB still adds its own tests before the verdict.
5. Speed: big slowdowns are problems. Small wins are suggestions.
6. Lean: dead or speculative code; a helper the repo already has; stdlib or
   platform already does it; a new dependency for a few lines; an abstraction
   with one implementation; near-copies that must change together. Split by job,
   never by line count, and never into helpers that exist only to shorten a function.

## 3. Check before you report

- Every finding needs a concrete case: this input or situation leads to this
  wrong result. No case, no finding.
- Re-read the lines and confirm: the caller exists, the value can really be
  empty, the code really is unused (grep the tree, including tests, fixtures,
  config, and string references).
- A `shortcut:` comment that names its limit is a decision, not a finding,
  unless the expected load already crosses it.
- Propose the smallest fix that works. Prefer fixes that delete code.
- No style taste, no "consider", no vague worries.

## 4. Output

Start with `What this change does:` in two or three sentences.

Then findings in three groups, skip empty groups:

- **Must fix:** bug, security, data loss, breaks at the expected load.
- **Should fix:** risky code without a test, real slowness, duplication, a
  function that mixes jobs, code that should not exist.
- **Nice to have:** small speed-ups, shorter forms.

Number findings across all groups so a reviewer can say "fix 2 and 5".
Every finding has all four parts:

2. **Short title** (`path:Lx-Ly`)
   - **What this is:**
   - **Problem:**
   - **Fix:**
   - **If we skip it:**

End with:

- `Verdict:` for an MRB job this is still PASS or FAIL per `bobiverse-bob-job-mrb`
  (Must fix means FAIL unless already fixed on the tip). For FR self-review, say
  whether the PR is ready.
- `Not checked:` one line if something mattered and you could not check it.

Nothing found: `What this change does:`, then `Looks good.` and one line on what
you checked.
