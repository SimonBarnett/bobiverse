<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-spec-intake/SKILL.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-spec-intake
description: >
  Park a functional specification or feature request as git: GitHub issue plus
  /docs markdown. Keep a source PDF only if one was supplied; do not generate
  review PDFs. Use when another agent sends a spec or feature request, says
  park in docs, or /bob-spec-intake, or create a new SimonBarnett repo.
  After park, run bob-job-loop unless Simon said park-only / later
  (Simon 2026-09-23: if you get a FR, you bob job it). A new repo is
  public (anyone can open a PR), gets the irc.ntsa.uk git webhook, and
  the Cursor GitHub App (All repositories) so Cursor Web can push/PR.
  New products and feature requests run visionary first (measurable
  success, shape, stack, architecture, HTML mocks when UI) before park
  or dispatch.
---

# Spec intake to /docs

## New product (fresh functional spec)

0. **Visionary first.** Skill `visionary`. High-reasoning / plan-mode.
   Fill `docs/templates/vision.md` in this session before `gh repo create`.
   Refuse park/dispatch until shape and success metrics are LOCKED or
   UNKNOWN, **and** `python tools/validate-vision-pack.py docs/vision.md
   --mocks-dir docs/mocks` exits 0 (product `tools/` else sister clone
   `C:\ai\skills-visionary`, `D:\ai\skills-visionary`,
   `C:\src\skills-visionary`). Non-zero = refuse.
1. Choose a clear public repo name under `SimonBarnett` (kebab-case).
2. Create the repo with **New GitHub repo** below if it does not exist.
3. Commit under `/docs`:
   - `docs/vision.md` (objective, success table, shape, stack, architecture).
   - `docs/mocks/*.html` (key screens plus empty/error; no PNGs).
   - `docs/functional-spec.md` (LOCKED pulled from vision, unknowns, Phase 0, acceptance).
   - Keep a source PDF **only if the sender provided one**. Do not invent a PDF.
   - If the product is a **skill pack**, LOCK a harvest skill as foundation
     (`.grok/skills/harvest-<repo>/SKILL.md` or equivalent). CAST IRON:
     learnings harvest back to that repo (`harvest-agent-skills`).
4. Open a GitHub issue titled from the spec, body linking `docs/vision.md`,
   `docs/mocks/`, and `docs/functional-spec.md`, label `feature-request`.
5. Push. Tell the human the issue URL and commit SHA.
6. Next: run `bob-build-dispatch` (unless the human said park-only / later).

## Feature request (extends existing repo)

0. **Visionary first.** Skill `visionary` (home:
   `SimonBarnett/skills-visionary`). High-reasoning / plan-mode. Confirm
   target repo; do **not** `gh repo create`. Fill success metrics LOCKED
   or UNKNOWN in the FR markdown (see visionary); add `docs/mocks/*.html`
   when the FR has a UI. Run `python tools/validate-vision-pack.py
   <fr.md> [--mocks-dir docs/mocks]` (product `tools/` else sister
   clone as in New product step 0). Refuse commit/issue/dispatch until
   the gate passes (validator exit 0).
1. Confirm target repo. **Do not break** prior versions.
2. Prefer new work in `v2/`, `v3/`, when the feature is a parallel product surface; keep root/`v1` frozen if the spec says so.
3. Commit `docs/feature-request-<slug>-YYYY-MM-DD.md` with summary plus **gap vs current tree**. Keep a source PDF only if one was supplied.
4. Open a GitHub issue (`feature-request`) linking that markdown. That issue is the MRB home.
5. Push. Tell the human the issue URL and commit SHA.
6. Next: `bob-job-loop` (isolated cwd + unique LogPath) unless Simon
   said **park-only** / later. Standing rule 2026-09-23: if you get a
   FR, you bob job it.

## New GitHub repo

Every new repo under `SimonBarnett` (this intake or any other create):

1. **Public, and anyone can open a pull request.** `gh repo create` with
   `--public`. Leave forking on. Do not set an interaction limit. Do not
   protect `main` so that only collaborators can open PRs. A GitHub user
   forks the repo and opens a PR. No extra permission step.
2. **Git webhook, same turn.** Skill `setup-github-webhooks`. Skip if
   `https://irc.ntsa.uk/bob/v1/git` is already on the repo. Do not point
   GitHub at `/bob/v1/report`. No hook secret in git, issues, or channel.
   Leave other hooks (Amplify and the rest) in place.
3. **Cursor GitHub App, same turn.** Skill `setup-github-cursor`. Cursor
   Web pushes as `cursor[bot]`. If the app is "Only select repositories"
   this new repo 403s (`git-receive-pack` denied to cursor[bot]). Keep
   **All repositories** (Contents + Pull requests Read and write).
   `tools\Grant-CursorGitHubApp.ps1` opens **Configure existing** on the
   Cursor GitHub App (`https://github.com/settings/installations`). Do not
   open `/apps/cursor/installations/new` when Cursor is already installed
   (that flow can replace Selected-repos and drop repos). A `gh`
   user token cannot grant the app. Do not
   `PUT collaborators/cursor[bot]` (not a user).

Write `hook.json` UTF-8 **without BOM** (PowerShell `ConvertTo-Json` adds a
BOM and GitHub returns 400):

```json
{"name":"web","active":true,"events":["push","pull_request","issues"],"config":{"url":"https://irc.ntsa.uk/bob/v1/git","content_type":"json","insecure_ssl":"0"}}
```

```powershell
gh api repos/SimonBarnett/<name>/hooks --jq ".[].config.url"
gh api repos/SimonBarnett/<name>/hooks -X POST --input hook.json
```

Create sends a `ping`. Jeeves announces `GIT ...` on `#bobiverse`. A
delivery `status_code` of 204 is success. GET on that URL is 405.

## Docs quality bar

- Capture LOCKED vs UNKNOWN.
- Name acceptance IDs / phase order if the source PDF has them.
- Never invent instance URLs, secrets, or procedure ENAMEs.
- If Simon said park-only / later, stop after push — do not dispatch.
  Otherwise dispatch (`bob-job-loop`).