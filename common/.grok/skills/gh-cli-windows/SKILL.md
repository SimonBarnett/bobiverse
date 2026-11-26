---
name: gh-cli-windows
description: >
  WinPS 5.1 + gh/git pitfalls for Bobiverse seats: --body-file UTF-8 no BOM, HTTP 500
  empty-body close fallback via issues PATCH, closingIssuesReferences, merge races.
  Use when gh fails oddly on Windows PowerShell or MRB board/close is blocked.
---

# gh CLI on Windows PowerShell

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

Fleet seats run **Windows PowerShell 5.1**. Prefer `--body-file` (UTF-8 **no BOM**) over multiline `--body`. Never print tokens.

## HTTP 500 empty-body fallback (FR #3160)

GitHub sometimes returns **HTTP 500 with an empty body** for:

- `POST .../issues/N/comments` (board / close comments)
- `PATCH .../pulls/N` (`state=closed`)
- GraphQL `gh pr comment` / `gh pr close`

**Reads** (`gh pr view`) and **issues-API close** may still work.

### Workaround

```powershell
# Close the PR via the issues endpoint (PRs share the issues number space)
gh api --method PATCH "repos/OWNER/REPO/issues/N" -f state=closed
# Retry the board comment later; DONE still cites the assigned PR URL
gh pr comment N --repo OWNER/REPO --body-file $boardFile
```

Evidence (bobiverse#3142 / intake #3160): pulls PATCH + comment POST returned 500; `PATCH .../issues/3142` with `state=closed` succeeded. Rate-limit remaining was healthy (~4875) — treat as transient edge unless request ids recur.

If it keeps happening: file intake with `gh` verbose request ids; keep this skill as the durable playbook (not a harvest tip).

## Body file pattern

- WinPS can split multiline `--body` into many argv (`accepts at most 1 arg(s)`).
- Write temp `.md` as UTF-8 **no BOM**:
  `[IO.File]::WriteAllText($path, $body, (New-Object System.Text.UTF8Encoding $false))`
- Then `gh pr create|edit|comment --body-file $path`.
- `Set-Content -Encoding utf8` on PS 5.1 writes a **BOM** and can break `closingIssuesReferences`.

## gh pr close / issue close flags

- `gh pr close` has **no** `--reason` (only `-c/--comment`, `-d/--delete-branch`).
- `gh issue close` accepts `--reason` / `--duplicate-of`.
- Prefer `gh pr comment --body-file` then `gh pr close` when the comment is long.

## closingIssuesReferences

- After `gh pr create`, re-check `gh pr view --json closingIssuesReferences` (can lag).
- Prefer same-repo `Closes #N` on its own line near the top of the body.
- Full-form `Closes owner/repo#N` alone may leave the field empty on some repos.

## Merge races

- GraphQL `gh pr merge` can briefly say not mergeable while UI is CLEAN; retry REST:
  `gh api --method PUT repos/OWNER/REPO/pulls/N/merge`
- 502 / "Merge already in progress": wait and re-check — may already be MERGED.
- Confirm `state=MERGED` before DONE PASS.

## Other WinPS pitfalls (short)

- `gh pr view --json` uses `author` (not `user`); `gh issue view` uses `closedByPullRequestsReferences` (not `closedBy`).
- `gh pr diff` has no path filter — use the pulls files API.
- `Get-ChildItem -Filter` takes a **single** pattern.
- `(Test-Path a) -or (Test-Path b)` — never `Test-Path a -or b`.
- Avoid Python f-strings inside `powershell python -c`; write a temp `.py` instead.
- `git push` stderr `remote:` lines often trip NativeCommandError; verify with tracking/`gh`.

## Shared GitHub OAuth budget (FR #9104)

One SimonBarnett **user OAuth** token (keyring / `gh auth`) is a **single 5000/hr core bucket** across every machine that uses it (MarchHare, flamingo, RQ, monitor). `gh api rate_limit` on two boxes shows the **same** `reset` and a shared falling `remaining`.

**Seat playbook when `API rate limit exceeded` / secondary rate limit:**

1. Check budget: `gh api rate_limit --jq .resources.core` (this call does not burn core quota).
2. If `remaining` under 500 (`github_api_budget.BACKOFF_FLOOR`): pause non-essential `gh` (search / broad list / resync fan-out); exponential backoff on 403/429; surface TipForm/digest-style signal `gh_rate_limited` instead of spinning.
3. Prefer git (`git fetch` + `git show`) over `gh api` for contents / PR patches when REST is starved.
4. Monitor: `Test-JeevesMonitorGithubRateLimit.ps1` (EXIT 1 when remaining under floor, JSON includes `machine`).

**Separate budgets (ops only):** per-machine fine-grained PAT or GitHub App installation token for worker seats; chair keeps its own app/token. Never print, commit, or paste tokens into skills, filings, or logs. Do not raise `seat_target` to compensate for a shared bucket.

Chair webhook side: under local intake rate limit, `check_run` / `check_suite` return **204** (`reason=rate deferred`) so GitHub does not retry-storm; push/PR/issues still **429**.

## Verify

```powershell
gh api rate_limit --jq .resources.core.remaining
gh pr view N --repo OWNER/REPO --json state,url
```