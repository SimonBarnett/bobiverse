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

### Digest lock watchdog (FR #1136 / FR #1388)

BobCallback / `bobreport.digest_lock` self-heals a wedged `digest.lock` (empty, older than `BOB_DIGEST_LOCK_STALE_S` default 30s, dead holder PID, or a **foreign** live holder older than `BOB_DIGEST_LOCK_FOREIGN_S` default 12s — e.g. chair `irc_agent` leaving the lock while `:7700` needs it): logs `lock-broken age=… pid=… reason=…`, bounded acquire + one break-and-retry, then HTTP **503** instead of hanging. A daemon thread probes loopback `GET /health` every `BOB_CALLBACK_HEALTH_S` (default 30s) and breaks a stale/foreign lock on failure. Fresh locks held by **this** BobCallback PID are kept. `GET /health` reports `lock_pid` / `pid`. Startup binds `:7700` **before** `drain_pending` so a blocked drain cannot leave the process alive with no LISTEN. FR #2595: `drain_intake_outbox` (used by startup `drain_pending` and `Drain-BobiverseIntakeOutbox.ps1` / `python intake.py drain`) is receipt-aware — drops `do-not-file` probes, records DONE/twin/GIVEUP harvest receipts without opening draft PRs, dedupes by idempotency key and existing `intake/<iid>` PRs, supports `--dry-run` counts, and only files remaining real playbooks/issues.

### Task principal must match digest home (FR #1316)

Scheduled task **BobCallback** must run as the same Windows account that owns `--home` (typically Administrator / Interactive for `C:\Users\Administrator\.bobiverse`). Registering it as **SYSTEM** (`S-1-5-18`) against an Admin profile home causes cross-principal `digest.lock` / ACL fights: the process can sit **Running** with no LISTEN on `:7700`, or LISTEN while HTTP hangs. `Install-Jeeves.ps1` calls `Register-BobCallbackTask.ps1` (Interactive home owner, never `/RU SYSTEM`). Startup refuses a non-writable home (exit 2) and bind failure (exit 1) so Task Scheduler can restart. `Start-Jeeves.ps1` treats task Running + no LISTEN after ~15–20s as a wedge and falls back to user-context `Start-Process`.

```powershell
.\scripts\Register-BobCallbackTask.ps1 -Start
Get-ScheduledTask BobCallback | Select-Object TaskName, State, @{n='RunAs';e={$_.Principal.UserId}}
Invoke-WebRequest http://127.0.0.1:7700/health -UseBasicParsing
```

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

Intake `repo` must be on the default allow-list in `scripts/intake.py` (`DEFAULT_ALLOW_REPOS`) or the POST returns **403** `repo_not_allowed`. Current defaults: `SimonBarnett/bobiverse`, `skills-visionary`, `agentic_fomprep`, `a-search`, `trutex` (FR #94; FR #3023; FR #3050; FR #795 retired archived `gh-Jeeves` / `agentic_build` / `AgentMonitor` / `bob-design-uat` / `agentic_irc`). Private repos are allowlist-eligible (visibility is not a gate).

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

## Intake ARR 502.3 (FR #1014)

When public /bob/v1/intake returns IIS **502.3**, BobCallback is not listening on 127.0.0.1:7700. See [fr-1014-intake-arr-restore.md](./fr-1014-intake-arr-restore.md). Assert: .\scripts\Assert-BobIntakeLocal.ps1.
