<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/setup-github-webhooks/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: setup-github-webhooks
description: >
  Set up GitHub repository webhooks. Use when the user says set up
  webhooks on git, GitHub hook, add hook to a repo or all repos, hook
  URL, /setup-github-webhooks, or a new SimonBarnett repo needs
  https://irc.ntsa.uk/bob/v1/git. Cursor Web PR/push grant is
  setup-github-cursor. HTTPS on the receiver is
  setup-ssl-certs. Jeeves announce text is agentic_irc
  jeeves-git-webhook.
---

# Set up GitHub webhooks

GitHub will not deliver to plain HTTP unless `insecure_ssl` is on.
Receiver must already be HTTPS. If `https://<host>/...` is not live,
do `setup-ssl-certs` first.

Default fleet receiver (every SimonBarnett repo):

`https://irc.ntsa.uk/bob/v1/git`

Events: `push`, `pull_request`, `issues`. JSON body. No hook secret
in git, issues, or channel. Do not point GitHub at
`/bob/v1/report` (that is digest `X-Bob-Secret`, skill `bob-irc`).

Jeeves announces accepted events as `GIT ...` on `#bobiverse`.
`bob-*` and talk seats do not narrate, and `bob-*` does not
auto-claim those lines. Skill `jeeves-git-webhook` in
**agentic_irc** (chair queue). Idle shop workers: skill
`bob-git-accept` (`!BORED` only; Jeeves `!TASK` marks accepted).

## One repo

Write `hook.json` UTF-8 **without BOM**:

```
{"name":"web","active":true,"events":["push","pull_request","issues"],"config":{"url":"https://irc.ntsa.uk/bob/v1/git","content_type":"json","insecure_ssl":"0"}}
```

```
gh api repos/SimonBarnett/<name>/hooks -X POST --input hook.json
```

PowerShell `ConvertTo-Json` often adds a BOM and GitHub returns 400
"Problems parsing JSON". Use `[IO.File]::WriteAllText($path, $json,
[Text.UTF8Encoding]::new($false))`.

Create sends a `ping`. Jeeves will `GIT ping`. Extra ping only if a
delivery looks dead:

```
gh api repos/SimonBarnett/<name>/hooks/<id>/pings -X POST
gh api repos/SimonBarnett/<name>/hooks/<id>/deliveries --jq '.[0] | {event,status,status_code}'
```

OK is `status_code` 204.

## List / skip if present

```
gh api repos/SimonBarnett/<name>/hooks --jq '.[].config.url'
```

If the target URL is already there, do not create a second hook.
Leave other hooks (Amplify, etc.) in place.

## All SimonBarnett repos

GitHub user accounts have **no** org-wide default. New repos need
this hook added.

```
gh repo list SimonBarnett --limit 200 --json name --jq '.[].name'
```

For each name, list hooks; POST `hook.json` only when the URL is
missing. PowerShell 5.1 `ConvertFrom-Json` of a JSON array can wrap
as one object so `$array.name` becomes every name joined. Iterate
`--jq '.[].name'` lines, not `$repos.name`.

Cursor Web / `cursor[bot]` push+PR is skill `setup-github-cursor`
(All repositories). Do that in the same turn as this hook on a new repo.

## Check

- Hook `config.url` is `https://irc.ntsa.uk/bob/v1/git`
- `insecure_ssl` is `0`
- Latest delivery 204
- GET `https://irc.ntsa.uk/bob/v1/git` is 405 (POST only)

## Do not

- HMAC / webhook secret in git.
- Replace unrelated hooks on the same repo.
- Stamp UAT.
