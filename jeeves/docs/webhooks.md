# Bobiverse webhooks (Jeeves / digest host)

Default public base: `https://bob.ntsa.uk` (FR #5272 / FR #6142 / FR #6166). IRC host stays `irc.ntsa.uk` (TLS 6697); never use the IRC hostname for `/bob/v1/*` HTTP (Hours and all other HTTP examples below use `bob.ntsa.uk`). Local listener often `127.0.0.1:7700` (align IIS; do not bake `:19781`).

Auth: **report / intake / jira / hours need no password** (v0.1.16). Nothing to copy between machines for those routes. Protection is validation instead: body size caps (413), strict JSON/op schema (400), per-machine rate limit (429), GitHub hooks only for allow-listed owners (`BOB_GIT_OWNERS`, default `SimonBarnett`; 403 otherwise), and `POST /bob/v1/report` only from machine ids on the **roster Jeeves publishes** (`registered-machines.json`, mirrored from ChanServ by the chair; 403 otherwise). The receiver only reads that file - it never talks to ChanServ or IRC. A stray `X-Bob-Secret` header is ignored. `POST /bob/v1/intake`, `POST|GET /bob/v1/jira`, and `POST|GET /bob/v1/hours` stay open with their own rate limits / schema gates (hours also rejects obvious credential fields and never logs request bodies).

**Git HMAC (FR #7467, optional):** when `BOB_GIT_WEBHOOK_SECRET_FILE` or `<BOB_CONFIG_DIR>/github-webhook.secret` exists, `POST /bob/v1/git` requires `X-Hub-Signature-256` (HMAC-SHA256 over the raw body). Invalid signatures always return **401**. `BOB_GIT_ALLOW_UNSIGNED=1` allows a *missing* signature only (migration). With no secret file the unsigned owner-gated contract is unchanged. Real 4xx bodies are compact JSON `{"ok":false,"error":"<fixed reason>"}`. Processing failures return **503** `{"error":"processing deferred"}` with `Retry-After` and keep the durable envelope pending.

## Paths

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/bob/v1/report` | Public fleet digest JSON. `/bob/v1/digest` is the **same** webhook and **301**s here. |
| POST | `/bob/v1/report` | TipForm / status callback (`op`: merge\|delete-worker\|worker-remove\|shop-down); **no secret; machine must be on the Jeeves roster**. `/bob/v1/digest` 301s here. **`delete-worker` / `worker-remove`:** HTTP **204** when a digest row changed (including `workers_last_good` snapshot cleanup), **200** when unchanged (FR #9145 / #9042). |
| POST | `/bob/v1/git` | GitHub git webhook → digest queue |
| POST | `/bob/v1/intake` | Harvest/intake (`kind`: issue\|fr\|skill\|harvest); **`repo` required** (`owner/name`) — **open, no secret** — **not** `/bob/v1/harvest` |
| POST/GET | `/bob/v1/jira` | Jira-style intake — **open, no secret** |
| POST | `/bob/v1/hours` | Create a work-time entry (open or closed); needs `idempotency_key` — **open, no secret** (FR #3450) |
| POST | `/bob/v1/hours/{id}/heartbeat\|close\|withdraw` | Heartbeat, close, or soft-withdraw an entry |
| GET | `/bob/v1/hours?user=…&from=…&to=…` | List entries (Europe/London days); optional `agent`/`customer`/`project`/`ticket`/`status` |
| GET | `/bob/v1/hours/summary?user=…&date=…` | Day totals: raw + de-overlapped minutes, overlaps |
| GET | `/bob/v1/hours/export?user=…&format=csv\|json` | Export entries |
| GET | `/bob/v1/builds` | Build catalog JSON array from digest-home `builds-catalog.json` (FR #8490); **open, no secret** |
| GET | `/bob/v1/models` | Fleet Weights JSON: nested `clis` (per-CLI model→context→efforts from `models-valid-combos.json`) + `agents` selections (BOB-01 / FR #8707 / FR #8819); **open, no secret** |
| PUT | `/bob/v1/models` | Persist Weights full replace; agent `cli` read-only (FR #8819); direct/LAN; IIS GET\|HEAD only |
| GET | `/health` | Local BobCallback liveness (FR #1136): `ok`, `lock_age_s`, `last_digest_write`; **not** published on the IIS front-door |

### Machine field `grok_account` (FR #6143)

`GET /bob/v1/report` and `POST /bob/v1/report` `op=merge` accept optional machine scalar `grok_account` (string or null). Ear-owned: omit keeps the stored value; null / `cleared: ["grok_account"]` removes it. Not filled from peer files. Never include credentials in the payload.

### Machine fields `cursor_account`, `cursor_account_user`, `cursor_account_source` (FR #7907)

`op=merge` accepts ear-owned scalars. `cursor_account` is a valid email or the literal `none` (a published value, not a clear). `cursor_account_user` is the Windows account leaf. `cursor_account_source` is only `api_key`, or null / `cleared: ["cursor_account_source"]` when the override is gone. Omit keeps the stored value. Invalid non-blank values are ignored. Not filled from peer files. Never include tokens or keys. An identity-only merge does not clear `model`.

### Machine field `opencode_account` (FR #6301 / FR #6312 / FR #6318)

Same semantics as `grok_account`: optional string label or null on `op=merge`; `GET` returns it; omit keeps the stored value; null / `cleared: ["opencode_account"]` removes it. Ear-owned (not peer-filled). Never holds API key material. OpenCode Go windows and Copilot live on digest `fleet_pools` (FR #7366); the hub drops per-machine copies. Ear paint contract (FR #6312 / #6318 / docs/mrb-6319): when neither a usable absolute `resetsAt` nor a usable relative `resetInSec` (go-zen layout) is available, paint `error: "reset unavailable"` with null `reset_label` and no invented `resets_at`. A valid `resetInSec` still yields countdown + `resets_at` even when `resetsAt` is absent. When both `resetInSec` and `resetsAt` are present, `resetInSec` wins (same order as `opencode_fuel._go_zen_meter_to_window`). A past absolute reset keeps `resets_at` and sets `reset_label` to null (countdown only while the reset is still in the future). Reporters should send the complete `opencode_windows` map on each merge - the hub replaces the stored map rather than deep-merging partial window rows.


Git hooks must target **`/bob/v1/git`**, never `/bob/v1/report`.

### FR #5170: webhook-first queue; Copilot virtual seat

Jeeves updates the job queue from `/bob/v1/git` deliveries (`issues`, `pull_request` including synchronize/closed, `pull_request_review`, `check_run`, `workflow_run`). `!resync` / hourly `github-resync` is the fallback (startup, webhook gap, delivery failure, safety interval). Required hook events include `pull_request_review`, `check_suite`, `check_run`, and `workflow_run` (`New-BobGitWebhook.ps1` / `copilot_dispatch.ensure_repo_webhook`). Permission failures file a stall issue (FR #5164). When Copilot allowance remains, Jeeves POSTs `agents/repos/{owner}/{repo}/tasks` with a `prompt` field and announces hand-off/completion as seat nick `copilot`. FR #5172 / #7255 / #7288 / #7371 / #7377 / #7382: allowance is `GET /copilot_internal/user` (dedicated fixed-rate 60s fleet fetch on Jeeves; watchdog poke independent of outbox drain; genuine `unlimited` or remaining/percent > 0). Used-up premium (`remaining=0`, `overage_permitted=false`) is exhausted even when GitHub sets `unlimited=true` / `percent_remaining=100`. OpenCode free/Go and Cursor (FR #7289, CredMan `Bobiverse/CursorAccess`) are the same fleet minute tick (`fleet_pools` on the digest). Credentials for Copilot/OpenCode: CredMan then Jeeves-root files (see `jeeves/docs/fleet-pools-credentials.md`); digest `source` is a tag only. FR #5316 / #5515: an out-of-tokens / quota-exhausted Copilot response persists a cooldown in `copilot-allowance.json` (`exhausted_until`) until `quota_reset_date` 00:00 UTC from `GET /copilot_internal/user`, or 00:00 UTC on the 1st of the next calendar month if that field is missing (`exhausted_until_source` = `api` or `fallback-1st`). Other fuels keep the 7-day pause unless a reset date is available. Jeeves announces once (`copilot out of tokens - paused until <UTC> (<source>)`), releases rows held by nick=copilot, and does not dispatch or probe until the cooldown ends. Digest `resume_at` / `resume_source` show when Copilot comes back. FR #5397: `cooldown_active(..., fuel=)` reads `fuels.<name>.exhausted_until`; Copilot still writes the legacy top-level key; exhausting cursor/grok does not pause Copilot or release Copilot rows. FR #5433: mark_tokens_exhausted keeps an already-active until and skips a second pause announce; an expired until still extends and announces. Digest `copilot` pool shows `state=exhausted` and `resume_at`. Chair calls `ensure_repo_webhook` on startup and hourly. Digest `copilot` pool is shown once on TipForm. FR #6148 / FR-008 / FR #6204: `observe_quota` refreshes Copilot into `copilot-observation.json` on the chair tick (300s cache) when dispatch is enabled or observation is explicitly opted in (`BOB_COPILOT_OBSERVE` / allowance `observe`); default with dispatch off is no quota GET; `fetched_at` advances only on successful parse; `pool_for_digest` prefers the newer successful observation over allowance and keeps cooldown `resume_at` from allowance. TipForm/Status mark aged `fetched_at` stale (900s) even when `resume_at` is still in the future. FR #5847: a draft Copilot FR implement PR (`copilot/fr-<N>-*` head, or `app/copilot-swe-agent` + Closes/Fixes #N) enters the MRB queue; stuck-sweep marks the held FR done (`COPILOT_PR`) and never releases `accepted_holder_gone` or starts a second Copilot task for that issue.

### Digest lock watchdog (FR #1136 / FR #1388)

BobCallback / `bobreport.digest_lock` self-heals a wedged `digest.lock` (empty, older than `BOB_DIGEST_LOCK_STALE_S` default 30s, dead holder PID, or a **foreign** live holder older than `BOB_DIGEST_LOCK_FOREIGN_S` default 12s — e.g. chair `irc_agent` leaving the lock while `:7700` needs it): logs `lock-broken age=… pid=… reason=…`, bounded acquire + one break-and-retry, then HTTP **503** instead of hanging. A daemon thread probes loopback `GET /health` every `BOB_CALLBACK_HEALTH_S` (default 30s) and breaks a stale/foreign lock on failure. Fresh locks held by **this** BobCallback PID are kept. `GET /health` reports `lock_pid` / `pid`. Startup binds `:7700` **before** `drain_pending` so a blocked drain cannot leave the process alive with no LISTEN. **FR #7618:** `serve_forever_guarded` reports and exits non-zero on accept/serve fatals (including `MemoryError`) so NSSM restarts instead of leaving the port bound but dead; the same health loop self-probes with budget `BOB_CALLBACK_LISTENER_PROBE_S` (default 10s) and exits after `BOB_CALLBACK_LISTENER_PROBE_FAILS` consecutive failures (default 2). FR #2595: `drain_intake_outbox` (used by startup `drain_pending` and `Drain-BobiverseIntakeOutbox.ps1` / `python intake.py drain`) is receipt-aware — drops `do-not-file` probes, records DONE/twin/GIVEUP harvest receipts without opening draft PRs, dedupes by idempotency key and existing `intake/<iid>` PRs, supports `--dry-run` counts, and only files remaining real playbooks/issues. FR #5359: `ChairJobs` also retries `intake/outbox` on a timer with backoff and immediately after a successful GitHub resync; `drain_intake_outbox_all` walks the whole queue in batches of 20 (not only the first 20). Digest GET exposes `intake_outbox.count` / `oldest_age_s` / `gh_cli`. Missing `gh` is a loud `--self-test` error (`check_gh_cli`) and is announced on `#bobiverse`.

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
curl -sS "https://bob.ntsa.uk/bob/v1/report"
```

### GET builds catalog (FR #8490)

Serves the validated JSON array from digest-home `builds-catalog.json` (missing file → `[]`). Each entry needs `name`, `yml` (`owner/repo` or `owner/repo:path`; path may not contain `..`, absolute/drive forms, or `?#%`/whitespace), `output` (artifact export dir; no whitespace), `install` (`fleet` or a machine id); optional `dep` (list, documentation only), `version` (numeric `x.y.z` / `x.y.z.w`), `ref`. Invalid rows are skipped. Chair `!build` loads the digest-home file first and only falls back to this HTTP endpoint when local catalogs are empty (FR #8770). Ops `!build n` builds the selected `yml` path, copies pack artifacts into `output`, then reinstalls on `install` (fleet expands from `registered-machines.json`). Example seed: `common/defaults/builds-catalog.example.json`.

```bash
curl -sS "https://bob.ntsa.uk/bob/v1/builds"
```

### GET models / Weights rows (BOB-01 / FR #8707 / FR #8819 / FR #9258)

Serves `{"clis":{…},"agents":[…]}` for the Weights grid. `agents` is one row per agent (Agent / CLI / Model / Context / Effort). Missing or empty digest-home `models-catalog.json` returns built-in rows for Plan, Priority, Jeeves, Grok, Cursor, Opencode, Opencode-Free with empty `model` / `context` / `effort` placeholders.

**FR #9258 (Grok-only context/effort):** context and effort apply only to the Grok CLI. Allowed contexts are `256` or `500`; allowed efforts are `high`, `medium`, or `low` (case-insensitive). Cursor and OpenCode catalog rows are valid with empty `contexts` / `efforts`, so the Weights form and tray start dialog offer those dropdowns only for Grok. Non-Grok stored `workerStartContext` / `workerStartEffort` values are ignored and dropped on the next write; pass status is `not-applicable`.

`clis` is the nested allow-list for dropdowns (Si locked shape, FR #8819):

```json
{"clis":{"Grok":{"models":{"<model>":{"contexts":{"256":{"efforts":["high","medium","low"]},"500":{"efforts":["high","medium","low"]}}}}},"Cursor":{"models":{}},"Opencode":{"models":{}}},
 "agents":[{"agent":"Plan","cli":"Grok","model":"","context":"","effort":""}]}
```

Built from digest-home `models-valid-combos.json` (BOB-03/04). A CLI with no catalog entry returns `models: {}` (still 200 — no invented names). Each agent row's options are `clis[row.cli]`. Example agents seed: `common/defaults/models-catalog.example.json`.

```bash
curl -sS "https://bob.ntsa.uk/bob/v1/models"
```

### PUT models / Weights rows (BOB-02 / FR #8708 / FR #8819)

Full-replace fleet Weights in digest-home `models-catalog.json`. Public IIS BobModelsWebhook forwards **GET|HEAD|POST** (FR #9224); PUT is direct listener / allowlisted LAN peer (same gate as other writes). Returns 204 when changed, 200 when unchanged. Agent row **`cli` is read-only** (FR #8819): a body that changes `cli` for a known agent returns **400** and leaves the store unchanged. Primary validation of model/context/effort is the Weights form dropdowns from `clis[row.cli]` (no POST validate required for this FR).

```bash
curl -sS -X PUT "http://127.0.0.1:7700/bob/v1/models" -H "Content-Type: application/json" --data-binary @weights.json
```

### POST models refresh (FR #8820)

`POST /bob/v1/models/refresh` rebuilds the per-CLI `clis` catalog inside digest-home `models-catalog.json` from each CLI's official listing command (no scraping, no cloud API keys):

| CLI | Command | Resolver order |
|-----|---------|----------------|
| Grok | `grok models` | `BOB_GROK_EXE`, PATH `grok`, `%USERPROFILE%\.grok\bin\grok.exe` |
| Cursor | `agent models` | `%LOCALAPPDATA%\cursor-agent\agent.cmd`, PATH `agent.cmd` / `cursor-agent.cmd` (never `agent.exe`) |
| OpenCode | `opencode models` | `BOB_OPENCODE_EXE`, PATH `opencode` |

Vendor docs: [xAI CLI](https://docs.x.ai/docs/cli), Cursor agent changelog, [OpenCode CLI](https://opencode.ai). Captured fixture samples live under `common/tests/fixtures/models_refresh/` (dated headers).

Rules:
- A failed or empty listing leaves that CLI's existing catalog untouched and reports `status: failed` with a fixed reason (`not_installed`, `timeout`, `exit_nonzero`, `spawn_error`, `empty_listing`).
- New models are stored with empty `contexts` / `efforts` (operator/seed enrich later). Existing listed rows keep their metadata.
- Agent selections are never rewritten. GET `/bob/v1/models` adds response-only `stale: true` when a row's model is non-empty and absent from `clis[lower(cli)].models`.
- Rate limit: one attempt per CLI per 60 s (in-memory; process restart resets). A second call inside the window returns **429** `rate_limited` with `retry_after_s` and changes nothing.
- BOB-04 seeds (`models-valid-combos.json`) remain the starting allow-list until the first successful refresh writes `refreshed_at` on a CLI entry in `models-catalog.json`.
- Peer gate: same `BOB_REPORT_ALLOW` allow-list as other POSTs. IIS `BobModelsWebhook` (`^bob/v1/models(.*)`) forwards GET|HEAD|POST (FR #9224; PUT/PATCH stay direct/LAN).
- Operator check: the `ircJeeves` service account must be able to run each CLI non-interactively; otherwise that CLI reports `failed`.

```bash
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/models/refresh"
```

### Models validation (form-only — Si 2026-11-22 / FR #9258)

There is **no** `POST /bob/v1/models/validate`. Available model / context / effort per CLI belong on **GET `/bob/v1/models`**. The Weights systray form shows current values and offers those options as dropdowns — that is the validation. Context and effort dropdowns are populated only for Grok (`256`|`500`, `high`|`medium`|`low`); Cursor/OpenCode rows have empty lists. A POST to `/bob/v1/models/validate` returns **404** `no_models_validate`.

### POST report (status / ops)

```bash
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/report" \
  -H "Content-Type: application/json" \
  -d "{\"op\":\"ping\",\"machine\":\"example-host\"}"
```

### POST git webhook (GitHub-shaped)

```bash
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/git" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -d "{\"action\":\"opened\",\"repository\":{\"full_name\":\"SimonBarnett/bobiverse\"},\"issue\":{\"number\":1,\"title\":\"example\"}}"
```

Fleet hooks subscribe to the chair's eight events: `issues`, `issue_comment`, `pull_request`, `pull_request_review`, `push`, `check_suite`, `check_run`, `workflow_run` (FR #5170 / #7467). Handled by the receiver (enqueue + apply): all of those except `workflow_run`, which is acknowledged with **204** and ignored (CI / merge-on-green state comes from `check_run` + resync; announcing every workflow would flood IRC). Other unhandled events also return 204 after the owner gate and do not consume the per-repo rate budget. A `lesson(<book>):` harvest tip enqueues MRB on `opened` from the title (no wait for `harvest-lesson`). If that webhook is missed, `pull_request` `labeled` backfills the same row (FR #4955). `pull_request`/`issues` deliveries also invalidate that repo's open issues/pulls list ETags so the next reconcile re-GETs even when enqueue missed (FR #4959). Product titles do not invent an MRB from a stray label. Repo setup: `tools/bob_git_hook.py` (eight events; `--secret-file` signs replay and sets the hook secret) / `tools/New-BobGitWebhook.ps1` (unsigned creator — the chair reconciler adds a provisioned secret on its next cycle). GitHub masks hook secrets, so the reconciler can detect a *missing* secret but not a mismatched one.

**Git secret rollout:** (1) write `github-webhook.secret` under `BOB_CONFIG_DIR` (or point `BOB_GIT_WEBHOOK_SECRET_FILE`), (2) run the chair webhook ensure or `bob_git_hook.py --secret-file`, (3) confirm signed deliveries are 2xx, (4) remove `BOB_GIT_ALLOW_UNSIGNED`. Rotation requires a BobCallback / Jeeves restart so the receiver reloads the file. **Recovery:** GitHub does not auto-retry; use manual/API redelivery within ~3 days for 503s; pending envelopes drain on restart; `!resync` / hourly reconcile rebuilds current state; IIS may return 502.3 while the listener is unbound during restart.

### POST intake (harvest) — no secret

```bash
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/intake" \
  -H "Content-Type: application/json" \
  -d "{\"kind\":\"harvest\",\"title\":\"example lesson\",\"body\":\"…\",\"repo\":\"SimonBarnett/bobiverse\"}"
```

Optional **`dedupe_key`** (FR #4963, at most 128 chars; else `400 bad_dedupe_key`): scoped per `repo`. When omitted on `kind=issue|fr`, intake derives a stable `msgfp:` key from a normalized title+body fingerprint (FR #6196: strips timestamps, intake ids, machine-pid nicks, `lag_s`, `elapsed_ms`, job ids; exact match only; no fuzzy merge). An explicit `dedupe_key` is tried first. Decision order after allowlist/rate/redaction:

1. **`idempotency_key`** — same POST retry is a no-op (`duplicate: true`, original `action`/`number`/`url`).
2. **`dedupe_key`** — open match: comment (`action=commented`); closed match: reopen then comment (`action=reopened`).
3. **title + signature** (FR #8019) — when the caller key misses (or was omitted), the same normalized title+body against an open issue comments instead of filing a twin. Covers per-job keys such as OpenCode hard-ceiling kills. A genuinely different title or error text still files a new issue. New filings index both the caller key and the `msgfp:` fingerprint (rebuilt from `gh issue list --search` / signature scan if the index is lost).

Response fields stay backward compatible: `intake_id`, `url`, `queued`, `duplicate`, `state`, plus `action` (`filed`|`commented`|`reopened`) and `number`. Outbox rows carry `dedupe_key`; `drain_intake_outbox` (FR #2595) runs the same comment/reopen/file decision (no duplicate comments on a re-drain).

```bash
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/intake" \
  -H "Content-Type: application/json" \
  -d "{\"kind\":\"issue\",\"repo\":\"SimonBarnett/a-search\",\"title\":\"import failure: awin merge\",\"body\":\"merge threw\",\"idempotency_key\":\"run-2026-10-25-1\",\"dedupe_key\":\"awin|feed-1|E_MERGE\"}"
```

Use a **single** `/bob/v1/intake` for harvest; do not add `/bob/v1/harvest`.

Intake `repo` must match `owner/name` and be under **`SimonBarnett/*`** (FR #3135) or the POST returns **403** `repo_not_allowed`. Non-SimonBarnett owners stay denied unless explicitly listed in `DEFAULT_ALLOW_REPOS` later. Known products (`bobiverse`, `skills-visionary`, `priority-mcp` — GitHub alias of the former `agentic_fomprep` name — `a-search`, `trutex`) remain documented examples (FR #94; FR #3023; FR #3050; FR #7121). Private repos are eligible (visibility is not a gate). Queue behaviour uses `!ignore` / `!focus` — not a second hardcoded intake list.

After intake allow-rule changes merge to `main`, **Sync/compose (or restart) ircJeeves on walrus** (Ergo/chair host; ionos deprecated) so the live webhook picks it up — source-on-main alone does not update a stale install (FR #3117 / #3122 class). Monitor: `Test-JeevesMonitorIntakeAllowlist.ps1`.

### POST jira — no secret

```bash
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/jira" \
  -H "Content-Type: application/json" \
  -d "{\"summary\":\"example\",\"description\":\"…\",\"project\":\"BOB\"}"
```

### Hours webhook (FR #3450) — no secret

Agents POST partial work-time entries as source material for Priority timesheets. Nothing here writes to Priority. Day filters use **Europe/London**. Open entries with no heartbeat past `BOB_HOURS_OPEN_TIMEOUT_MIN` (default 120) become `auto_closed`. Store lives under digest home `hours/`. Canonical field names live here (FR #3673); agent skill books must match this schema.

**Agent field map (accepted vs rejected):**

| Accepted body / query field | Rejected aliases (do not send) |
|---|---|
| `start` (ISO-8601 datetime) | `started_at`, `start_at`, `started`, `from` |
| `end` (ISO-8601; omit for open) | `ended_at`, `finish` |
| `customer` | `customer_slug` |
| `project` | `project_slug` |
| `on_behalf_of` | — |
| `idempotency_key`, `agent`, `repo_url`, `description`, `source`, optional `tickets`, `billable_hint` | credential keys (`password`, `token`, …) — rejected |

**Create errors (FR #3673):** missing/empty `start` → `{"error":"missing_start","hint":"expected: start"}` (adds `rejected_aliases` when an alias was sent). Unparseable `start` → `{"error":"bad_start","hint":"start must be ISO-8601 datetime"}`. GET list/summary/export without `user` → `{"error":"user_required","hint":"?user=USERLOGIN"}`.

```bash
# Create (open entry)
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/hours" \
  -H "Content-Type: application/json" \
  -d "{\"idempotency_key\":\"seat-1\",\"agent\":\"Haitch\",\"on_behalf_of\":\"SimonB\",\"start\":\"2026-10-08T09:15:00+01:00\",\"customer\":\"ce-priority\",\"project\":\"dayworks\",\"repo_url\":\"https://github.com/SimonBarnett/ce-priority\",\"description\":\"Draft Day Works hours\",\"source\":\"marchhare\"}"

# Create closed in one POST (start + end) — returns status:closed and duration_minutes
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/hours" \
  -H "Content-Type: application/json" \
  -d "{\"idempotency_key\":\"seat-1-closed\",\"agent\":\"Haitch\",\"on_behalf_of\":\"SimonB\",\"start\":\"2026-10-08T09:00:00+01:00\",\"end\":\"2026-10-08T17:00:00+01:00\",\"customer\":\"trutex\",\"project\":\"deposco\",\"description\":\"Closed day\",\"source\":\"cloud\"}"

# Heartbeat / close / withdraw
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/hours/<id>/heartbeat" -H "Content-Type: application/json" -d "{}"
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/hours/<id>/close" -H "Content-Type: application/json" \
  -d "{\"end\":\"2026-10-08T11:00:00+01:00\"}"
curl -sS -X POST "https://bob.ntsa.uk/bob/v1/hours/<id>/withdraw" -H "Content-Type: application/json" -d "{}"

# List / summary / export (user= is required)
curl -sS "https://bob.ntsa.uk/bob/v1/hours?user=SimonB&from=2026-10-08&to=2026-10-08"
curl -sS "https://bob.ntsa.uk/bob/v1/hours/summary?user=SimonB&date=2026-10-08"
curl -sS "https://bob.ntsa.uk/bob/v1/hours/export?user=SimonB&from=2026-10-08&to=2026-10-08&format=csv"
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

**FR #9246 post-install probe:** `Install-BobWebhooks.ps1` GETs `$Backend/bob/v1/report` after writing rules. Default is WARN when the backend is down (IIS would 502); pass `-RequireBackend` to fail the install, or `-SkipBackendProbe` in unit tests.


## Jeeves appliance static assets (FR #7411)

`Install-BobWebhooks.ps1` copies `jeeves-butler.ico` and `ntsa-gut-logo.png` to `<IIS physical>/jeeves/assets/`. The `BobJeevesAppliance` rewrite skips `/jeeves/assets/` so IIS serves those files (`.ico` / `.png` allowed). Login HTML uses prefix-aware `/jeeves/assets/...` when mounted at `/jeeves`. Packed installs also resolve the butler from `assets/jeeves-butler.ico`.

## Front-page HTML docs (FR #6453 / FR #8835)

Static pages under `jeeves/www/irc-ntsa/`. Browse `https://bob.ntsa.uk/` (keeps the `bobiverse acme` marker), `https://bob.ntsa.uk/docs/webhooks/`, and `https://bob.ntsa.uk/downloads`.

**Coverage rule (FR #8835):** every public route under `/bob/v1/*` served by Jeeves/BobCallback (plus local health/digest and outbound stall/wake) MUST have (1) a card in Webhooks & API on the home page, (2) a page under `docs/webhooks/`, and (3) a row on `docs/webhooks/index.html`. Registry: `common/scripts/bob_webhook_docs.py`. Route inventory: `common/scripts/bob_route_inventory.py`. Enforced by `common/tests/test_fr8835_webhook_docs_route_coverage.py` (also run from `pytest-ascii-bom`). Coming operations (models PATCH; #8708) use `DocEntry.status="coming"` until served. Models PUT is live (FR #8708 / #8819 / #9122). POST models/refresh (#8820) is live.

**Static-only content publish (FR #8835 / #8803):** for HTML/docs-only updates, copy `jeeves/www/irc-ntsa/**` to the IIS site physical path **excluding `web.config`**, `*.bak`, and `_backup-*`, and do **not** delete live files. Do **not** re-run `Install-BobWebhooks.ps1` for content-only changes --- that installer rewrites WebSocket rules (#8803). Use `Install-BobWebhooks.ps1` only when rewrite rules or site wiring must change. Regenerate pages with `python common/scripts/gen_bob_webhook_docs_html.py` after registry edits.

**Publish backups (FR #8887):** `Install-BobWebhooks.ps1` writes rollback copies under `-BackupRoot\_backup-www-<site leaf>` (default: parent of `-PhysicalPath`; `Install-Jeeves` passes the install root, e.g. `C:\ai\jeeves\_backup-www-irc-ntsa`). Never place `_backup-*` or `*.bak` inside the IIS web root. The shipped `web.config` denies `.bak` (fileExtensions) and the URL sequences `_backup-` / `.bak/` so a stray backup is not served. Removing legacy live-root backups on walrus is a one-off for Slab (Si go) and is outside the installer PR.

**Walrus verify checklist (FR #8887):** after publish, confirm `https://bob.ntsa.uk/web.config.fr8803.anything.bak` and `https://bob.ntsa.uk/downloads/_backup-20261115-x/` return 404/403 (not 200). Upper-case `_BACKUP-` must also stop. Working routes (`/`, `/bob/v1/models`, `/downloads/`) still 200. Owner sign-off before declaring green.

FR #7413 publishes unauthenticated <code>/jeeves/commands</code>. FR #7410 / #7528 downloads shelf. FR #7414 (publish path): when rewrite/site wiring must change, re-run `Install-BobWebhooks.ps1` after git pull / compose so walrus IIS stays in sync — it can publish `site.css`, `downloads/`, `jeeves/commands/` (when present), and `docs/` (opt-in `-PublishWww` / `-SiteKit` per #8803). FR #7442: site-root `/favicon.ico` is the Bob tray icon; `web.config` maps `.ico` to `image/x-icon` and does not rewrite `/favicon.ico` to Jeeves. Optional `-WwwSource` overrides the tree for installer tests.
