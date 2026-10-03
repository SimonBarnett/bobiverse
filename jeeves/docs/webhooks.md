# Bobiverse webhooks (Jeeves / digest host)

Default public base: `https://irc.ntsa.uk`. Local listener often `127.0.0.1:7700` (align IIS; do not bake `:19781`).

Auth: **none. No route needs a password or shared secret** (v0.1.16). Nothing to copy between machines. Protection is validation instead: body size caps (413), strict JSON/op schema (400), per-machine rate limit (429), GitHub hooks only for allow-listed owners (`BOB_GIT_OWNERS`, default `SimonBarnett`; 403 otherwise), and `POST /bob/v1/report` only from machine ids on the **roster Jeeves publishes** (`registered-machines.json`, mirrored from ChanServ by the chair; 403 otherwise). The receiver only reads that file - it never talks to ChanServ or IRC. A stray `X-Bob-Secret` header is ignored. `POST /bob/v1/intake` and `POST|GET /bob/v1/jira` stay open with their own rate limits and repo allow-lists.

## Paths

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/bob/v1/report` | Public fleet digest JSON (also `/bob/v1/digest`) |
| POST | `/bob/v1/report` | TipForm / status callback (`op`: merge|delete-worker|shop-down); **no secret; machine must be on the Jeeves roster** |
| POST | `/bob/v1/git` | GitHub git webhook → digest queue |
| POST | `/bob/v1/intake` | Harvest/intake (`kind`: issue\|fr\|skill\|harvest); **`repo` required** (`owner/name`) — **open, no secret** — **not** `/bob/v1/harvest` |
| POST/GET | `/bob/v1/jira` | Jira-style intake — **open, no secret** |
| GET | `/health` | Local BobCallback liveness (FR #1136): `ok`, `lock_age_s`, `last_digest_write`; **not** published on the IIS front-door |

Git hooks must target **`/bob/v1/git`**, never `/bob/v1/report`.

### Digest lock watchdog (FR #1136)

BobCallback / `bobreport.digest_lock` self-heals a wedged `digest.lock` (empty, older than `BOB_DIGEST_LOCK_STALE_S` default 30s, or dead holder PID): logs `lock-broken age=… pid=…`, bounded acquire + one break-and-retry, then HTTP **503** instead of hanging. A daemon thread probes loopback `GET /health` every `BOB_CALLBACK_HEALTH_S` (default 30s) and breaks a stale lock on failure. Fresh locks held by a live PID are never broken.

## Placeholder curls

Replace the host as needed. Bodies are minimal scaffolds.

### GET digest

```bash
curl -sS "https://irc.ntsa.uk/bob/v1/report"
```

### POST report (status / ops)

```bash
curl -sS -X POST "https://irc.ntsa.uk/bob/v1/report" \
  -H "Content-Type: application/json" \
  -d "{\"op\":\"ping\",\"machine\":\"example-host\"}"
```

### POST git webhook (GitHub-shaped)

```bash
curl -sS -X POST "https://irc.ntsa.uk/bob/v1/git" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
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

Intake `repo` must be on the default allow-list in `scripts/intake.py` (`DEFAULT_ALLOW_REPOS`) or the POST returns **403** `repo_not_allowed`. Current defaults: `SimonBarnett/bobiverse`, `skills-visionary`, `agentic_fomprep` (FR #94; FR #795 retired archived `gh-Jeeves` / `agentic_build` / `AgentMonitor` / `bob-design-uat` / `agentic_irc`).

### POST jira — no secret

```bash
curl -sS -X POST "https://irc.ntsa.uk/bob/v1/jira" \
  -H "Content-Type: application/json" \
  -d "{\"summary\":\"example\",\"description\":\"…\",\"project\":\"BOB\"}"
```

## Local assert

```powershell
# TipForm digest path smoke (bob install):
.\scripts\Assert-BobDigestWebhookLocal.ps1 -InstallRoot <ai root>\bob
```

## Offline / resume

When the handler is offline, webhook intakes should be cached and processed on resume (chair/cache policy — expand when listener lands).

## Intake errors (FR #611)

`POST /bob/v1/intake` returns JSON `{"error":"<code>"}` on 400/403. `Report-BobiverseIntakeIssue.ps1` surfaces that `error` in `intake_error` / `error` (not only `(400) Bad Request`). Permanent validation codes (`bad_title`, `bad_kind`, `payload_too_large`, …) are dropped on `Invoke-BobiverseHarvest -Flush` instead of retrying forever. Titles must be 1–200 characters.

