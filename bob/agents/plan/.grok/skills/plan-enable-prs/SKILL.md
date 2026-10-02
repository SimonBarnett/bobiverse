---
name: plan-enable-prs
description: >
  Permit pull-request workflow on a new SimonBarnett product repo: keep
  the repo public with forking on, avoid rulesets that block outside PRs,
  and ensure the Cursor GitHub App can push/PR as cursor[bot]. Use when
  Plan seats finish create+webhook, cursor[bot] 403, permit PRs, or
  /plan-enable-prs. Orchestrator: plan-git-from-plan. Harvest from
  agentic_build setup-github-cursor + bob-spec-intake public-PR rules.
---

# Enable PRs from plan (Plan seats)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `..\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `..\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `..\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.


Self-contained harvest from `agentic_build` `setup-github-cursor` and
the "anyone can open a PR" rules in `bob-spec-intake`. Plan seats do
**not** install the full build pack.

## Human fork-PRs (default for new public products)

After `gh repo create --public`:

1. Leave **forking on**.
2. Do **not** set an interaction limit.
3. Do **not** add a ruleset / branch protection that blocks outside
   collaborators from opening PRs on day one.
4. Do **not** protect `main` so that only collaborators can open PRs.

A GitHub user forks the repo and opens a PR. No collaborator invite.

(The stricter `agentic_build` `docs/github-main-protection-checklist.md`
is for that fleet repo's MRB gate — not the default for a brand-new
product created from Plan. Add protection later at human UAT if needed.)

## Cursor Web / Cloud Agent push+PR

Cursor Web does **not** use your `gh` user token. It pushes as
`cursor[bot]` with an installation token. If the Cursor GitHub App is
not granted on the repo (or Contents is Read only):

```
remote: Permission to SimonBarnett/<repo>.git denied to cursor[bot].
```

### All repositories (preferred, once)

1. Open **Configure** on the existing Cursor install:
   https://github.com/settings/installations
   (SimonBarnett user — not org MedatechUK).
2. Repository access: **All repositories** so every future public repo
   is included. Do not leave "Only select repositories" (new repos 403).
3. Permissions enough as-is when they already match:

   Read: administration, commit statuses, deployments, metadata,
   packages, pages.

   Read and write: actions, checks, **code**, discussions, issues,
   merge queues, **pull requests**, workflows.

   `code` write = Contents write (`git-receive-pack`).
   `pull requests` write = PR API.

4. If GitHub shows a **Review request** / new permissions banner,
   accept it.

Helper (opens the pages; Simon must click — `gh` cannot grant apps):

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Grant-CursorGitHubApp.ps1
```

### New repo same turn

After create + `plan-bob-webhooks` (gate exit 0):

1. Confirm Cursor app is still **All repositories**. If "Only select
   repositories", add this repo now or switch to All.
2. Do not set interaction limits. Do not add a ruleset that blocks
   `cursor/*` branches or outside collaborators opening PRs.
3. Leave forking on.
4. Ensure merge buttons work (default allow merge commit / squash /
   rebase — do not disable all three via API).
5. Create the `feature-request` label **before** the first issue
   (new repos have no labels; `gh issue create --label feature-request`
   fails otherwise):

```
gh label create feature-request --repo SimonBarnett/<name> --color 0E8A16 --description "Feature request / MRB home" --force
```

### If All repositories is already set and Cursor still 403s

Known Cursor Cloud/Web token bug. Do not change GitHub again.

1. https://cursor.com/dashboard/integrations — **Disconnect** GitHub,
   then **Connect** as **SimonBarnett** (not MedatechUK).
2. Retry Cursor Web push.
3. If still 403: push and `gh pr create` from a box logged in as
   SimonBarnett. Do not add `cursoragent` or `cursor[bot]` as a
   collaborator (`cursor[bot]` is not a user).

Do **not** prefer https://github.com/apps/cursor/installations/new
when Cursor is already installed (can replace Selected-repos and drop
existing repos).

## Same-turn order (with plan-git-from-plan)

After `gh repo create` and **after** `python tools/bob_git_hook.py …`
exits 0 (skill `plan-bob-webhooks`), run this skill before the first
push and before opening the FR issue. Do not open issues/PRs while the
repo still blocks forks or while Cursor is on Selected-repos only.

Create the `feature-request` label before the first issue
(`gh label create feature-request --force` — a brand-new repo has no
labels, so `gh issue create --label feature-request` fails otherwise).

## Real check

**Real test:** Cursor Web / Cloud Agent push no longer 403s as
`cursor[bot]`. Local `gh pr create` as SimonBarnett does **not** prove
the app grant. A human fork-PR still opens without a collaborator invite.

## Do not

- Put a PAT or installation token in git, issues, or channel.
- `PUT collaborators/cursor[bot]` (404: not a user).
- Stamp UAT.
- Depend on full `agentic_build` skill install.