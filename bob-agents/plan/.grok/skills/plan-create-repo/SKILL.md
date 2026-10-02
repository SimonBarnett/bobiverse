---
name: plan-create-repo
description: >
  Create a public SimonBarnett GitHub repo from an approved plan / vision
  pack. Use when a TipForm Plan seat (Grok/Cursor) has LOCKED a vision pack
  and needs gh repo create, after plan approved, new product git, or
  /plan-create-repo. Orchestrator: plan-git-from-plan. Webhooks:
  plan-bob-webhooks. PR permit: plan-enable-prs. Do not use on feature
  requests against an existing repo.
---

# Create repo from plan (Plan seats)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `C:\ai\bob\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `C:\ai\bob\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `C:\ai\bob\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.


Self-contained harvest from `agentic_build` `bob-spec-intake` **New
GitHub repo** (create half only). Plan seats load **skills-visionary**
only — do not require the full agentic_build pack.

## Preconditions

- Vision pack written this session (`docs/templates/vision.md` filled).
- Shape + success LOCKED or UNKNOWN.
- `python tools/validate-vision-pack.py docs/vision.md --mocks-dir docs/mocks`
  exits 0 (product `tools/` else sister clone `D:\ai\skills-visionary`,
  `C:\ai\skills-visionary`, `C:\src\skills-visionary`).
- This is a **new product**, not an FR on an existing repo.

## Steps

1. Choose a clear public repo name under `SimonBarnett` (kebab-case).
2. Skip create if it already exists:

```
gh repo view SimonBarnett/<name> --json name,url,isPrivate,url
```

3. Create **public** (anyone can open a PR via fork):

```
gh repo create SimonBarnett/<name> --public --description "<one-line from vision objective>"
```

Leave forking on. Do not set an interaction limit. Do not protect
`main` so that only collaborators can open PRs. A GitHub user forks
and opens a PR — no extra permission step for humans.

4. Clone or init local cwd for the first vision-pack commit (orchestrator
   `plan-git-from-plan` does the commit). Prefer:

```
gh repo clone SimonBarnett/<name> D:\ai\<name>
```

(or `C:\ai\<name>` / fleet home convention).

## Same-turn follow-ups (required)

**Immediately after `gh repo create`, before clone/commit/push/issue:**

```
python tools/bob_git_hook.py SimonBarnett/<name>
```

must exit 0 (skill `plan-bob-webhooks`, Gate). Events before the hook
are never delivered, so Jeeves stays silent about the new repo and its FR issue.

After create, in the **same turn**:

1. `plan-bob-webhooks` — git hook to Bob.
2. `plan-enable-prs` — Cursor app / no ruleset that blocks PRs.

Do not invent instance URLs or secrets. Do not stamp UAT.

## Do not

- `gh repo create --push` / `--source` with commits before the hook is verified.

- `gh repo create` on a feature-request path (existing target repo).
- Create private by default (Plan → public products).
- Put PATs, hook secrets, or `report.secret` in git.
- Depend on installing all of `agentic_build`.