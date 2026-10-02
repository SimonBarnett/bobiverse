---
name: plan-bob-webhooks
description: >
  Point a SimonBarnett GitHub repo at Bob fleet webhooks (git events to
  /bob/v1/git). Use when a new plan-created repo needs hooks, set up
  webhooks on git, GitHub hook, or /plan-bob-webhooks. Digest report URL
  is documented here for Plan seats but is NOT the GitHub hook target.
  Orchestrator: plan-git-from-plan. Source harvest: agentic_build
  setup-github-webhooks + bobiverse.json reportUrl.
---

# Bob webhooks from plan (Plan seats)

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


Self-contained harvest from `agentic_build` skills
`setup-github-webhooks` and `bob-digest-webhook` (URL table only).
No IRC restart. No digest producer code.

## Two different Bob URLs (do not mix)

| Role | URL | Who uses it |
|------|-----|-------------|
| **GitHub webhook** (this skill) | `https://irc.ntsa.uk/bob/v1/git` | GitHub → Jeeves `GIT ...` on `#bobiverse` |
| **Digest report** (document only) | `https://irc.ntsa.uk/bob/v1/report` | Fleet / TipForm GET+POST `op=merge`; `config/bobiverse.json` `reportUrl` |

Never point a GitHub hook at `/bob/v1/report` (that path expects
`X-Bob-Secret` digest merges). Never HMAC/webhook secret in git,
issues, or channel.

Source of truth for reportUrl in the build pack:
`agentic_build/config/bobiverse.json` → `"reportUrl": "https://irc.ntsa.uk/bob/v1/report"`.

## Gate: hook BEFORE any push or issue (required)

Tracks FR **#19** (and closes the club-madeira-onboarding miss): Plan
must leave a new repo fully wired into Bob Fleet before any issue or PR.

GitHub never backfills: anything pushed or opened before the hook exists
is never delivered, so Jeeves never announces it and the FR issue never
reaches the unaccepted queue. (club-madeira-onboarding 25/09: repo 08:03:30Z,
first commit 08:03:43Z, issue #1 08:04:00Z, hook 08:04:21Z, so repo and
issue #1 were silent on `#bobiverse`.)

Run this right after `gh repo create`, before the first push, and
before `gh issue create`:

```
python tools/bob_git_hook.py SimonBarnett/<name>
```

It is the single source of truth for the hook and exits 0 only when:

1. The hook matches the fleet config **exactly** (creates it if absent, PATCHes
   drift, never adds a second one, leaves unrelated hooks alone):
   url `https://irc.ntsa.uk/bob/v1/git`, `content_type` `json`,
   `insecure_ssl` `0`, events `issues`,`pull_request`,`push`, active.
2. A `ping` delivery returned **2xx** (the receiver answers 204).
3. Items opened before the hook existed are replayed as `opened` events
   (automatic when this run created the hook; else `--replay-missed`).
4. Jeeves' `GIT ping SimonBarnett/<name>` (and each replayed
   `GIT issues|pull_request ... opened #N`) line is seen in
   `~/.agentic-irc-bobiverse/irc.log`, or the replayed item is in the
   digest unaccepted queue.

Exit 1 = hook or ping failed; exit 2 = Jeeves announce not seen. Either
way, **webhook setup is NOT done**. Do not tell the human it is, and do
not push or open the issue yet.

Fix for a repo that was already set up late (after the fact):

```
python tools/bob_git_hook.py SimonBarnett/<name> --replay-missed
```

## Secret handling

Fleet hooks (agentic_build, agentic_irc, AgentMonitor, skills-visionary)
carry **no** webhook secret; the `/bob/v1/git` receiver does not check
HMAC. Match that. `--secret-file <path>` exists only for a future signed
receiver. The value is read from the file and never printed. Never type
a secret on a command line, in chat, in git, or in an issue.

## Events

`push`, `pull_request`, `issues`. JSON body. `insecure_ssl` = `0`
(receiver must already be HTTPS).

## One repo

Write `hook.json` UTF-8 **without BOM**:

```
{"name":"web","active":true,"events":["push","pull_request","issues"],"config":{"url":"https://irc.ntsa.uk/bob/v1/git","content_type":"json","insecure_ssl":"0"}}
```

PowerShell `ConvertTo-Json` often adds a BOM and GitHub returns 400
"Problems parsing JSON". Prefer:

```powershell
$json = '{"name":"web","active":true,"events":["push","pull_request","issues"],"config":{"url":"https://irc.ntsa.uk/bob/v1/git","content_type":"json","insecure_ssl":"0"}}'
[IO.File]::WriteAllText("$PWD\hook.json", $json, [Text.UTF8Encoding]::new($false))
gh api repos/SimonBarnett/<name>/hooks -X POST --input hook.json
```

Or use this pack's helper:

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\New-BobGitWebhook.ps1 -Repo SimonBarnett/<name>
```

## List / skip if present

```
gh api repos/SimonBarnett/<name>/hooks --jq '.[].config.url'
```

If `https://irc.ntsa.uk/bob/v1/git` is already there, do not create a
second hook. Leave other hooks (Amplify, etc.) in place.

## Check

`python tools/bob_git_hook.py SimonBarnett/<name>` is the check (see Gate).
Manual spot-checks:

```
gh api repos/SimonBarnett/<name>/hooks/<id>/deliveries --jq '.[0] | {event,status,status_code}'
```

- GET `https://irc.ntsa.uk/bob/v1/git` is 405 (POST only)

## Do not

- Push, commit to the remote, or open an issue/PR before `bob_git_hook.py` exits 0.
- Declare setup done on a 2xx ping alone; the Jeeves announce is required too.

- Point GitHub at `/bob/v1/report`.
- Put hook secrets in git.
- Replace unrelated hooks.
- Restart IRC / touch chair.
- Stamp UAT.