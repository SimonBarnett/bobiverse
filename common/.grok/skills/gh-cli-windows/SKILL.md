---
name: gh-cli-windows
description: >
  WinPS 5.1 + gh/git pitfalls for Bobiverse seats: --body-file UTF-8 no BOM, HTTP 500
  empty-body close fallback via issues PATCH, closingIssuesReferences, merge races.
  Use when gh fails oddly on Windows PowerShell or MRB board/close is blocked.
---

# gh CLI on Windows PowerShell

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
  `[System.IO.File]::WriteAllText($path, $body, (New-Object System.Text.UTF8Encoding $false))`
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

## Verify

```powershell
gh api rate_limit --jq .resources.core.remaining
gh pr view N --repo OWNER/REPO --json state,url
```