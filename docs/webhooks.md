# Bobiverse webhooks (Jeeves / digest host)

Default public base: `https://irc.ntsa.uk`. Local listener often `127.0.0.1:7700` (align IIS; do not bake `:19781`).

Auth: `POST /bob/v1/report` needs header `X-Bob-Secret` from `BOB_REPORT_SECRET` or `~\.grok\bob\report.secret` (never commit secrets). **`POST /bob/v1/intake` and `POST|GET /bob/v1/jira` are open** (no secret) so skill harvest and Jira webhooks can file without a fleet credential. Rate limits and repo allowlists still apply on intake.

## Paths

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/bob/v1/report` | Public fleet digest JSON (also `/bob/v1/digest`) |
| POST | `/bob/v1/report` | TipForm / status callback (`op` body); **secret required** |
| POST | `/bob/v1/git` | GitHub git webhook → digest queue |
| POST | `/bob/v1/intake` | Harvest/intake (`kind`: issue\|fr\|skill\|harvest); **`repo` required** (`owner/name`) — **open, no secret** — **not** `/bob/v1/harvest` |
| POST/GET | `/bob/v1/jira` | Jira-style intake — **open, no secret** |

Git hooks must target **`/bob/v1/git`**, never `/bob/v1/report`.

## Placeholder curls

Replace `SECRET` and host as needed. Bodies are minimal scaffolds.

### GET digest

```bash
curl -sS "https://irc.ntsa.uk/bob/v1/report"
```

### POST report (status / ops)

```bash
curl -sS -X POST "https://irc.ntsa.uk/bob/v1/report" \
  -H "Content-Type: application/json" \
  -H "X-Bob-Secret: SECRET" \
  -d "{\"op\":\"ping\",\"machine\":\"example-host\"}"
```

### POST git webhook (GitHub-shaped)

```bash
curl -sS -X POST "https://irc.ntsa.uk/bob/v1/git" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -H "X-Bob-Secret: SECRET" \
  -d "{\"action\":\"opened\",\"repository\":{\"full_name\":\"SimonBarnett/bobiverse\"},\"issue\":{\"number\":1,\"title\":\"example\"}}"
```

Repo setup helper: `tools/New-BobGitWebhook.ps1` / `tools/bob_git_hook.py`.

### POST intake (harvest) — no secret

```bash
curl -sS -X POST "https://irc.ntsa.uk/bob/v1/intake" \
  -H "Content-Type: application/json" \
  -d "{\"kind\":\"harvest\",\"title\":\"example lesson\",\"body\":\"…\",\"repo\":\"SimonBarnett/bobiverse\"}"
```

Use a **single** `/bob/v1/intake` for harvest; do not add `/bob/v1/harvest`.

### POST jira — no secret

```bash
curl -sS -X POST "https://irc.ntsa.uk/bob/v1/jira" \
  -H "Content-Type: application/json" \
  -d "{\"summary\":\"example\",\"description\":\"…\",\"project\":\"BOB\"}"
```

## Local assert

```powershell
# TipForm digest path smoke (bob install):
.\scripts\Assert-BobDigestWebhookLocal.ps1 -InstallRoot C:\ai\bob
```

## Offline / resume

When the handler is offline, webhook intakes should be cached and processed on resume (chair/cache policy — expand when listener lands).
