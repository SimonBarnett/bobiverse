# Jeeves appliance settings (FR #6436 foundation + FR #6440 LAN HTTP + FR #6441 auth)

Internal-only settings surface for the Ergo chair host. **Never** publish this
on Cloudflare or public DNS. Do **not** front it via `bob.ntsa.uk` or
`irc.ntsa.uk`.

Operator URL: **https://jeeves.ntsa.uk/** (FR #6757 / FR #6758). The name is
internal DNS only. TLS uses an operator-supplied certificate (store thumbprint
on the chair host). Do **not** request a public ACME certificate. Do **not** create public DNS for this name.

## How to reach it

1. On the internal DNS (LAN AD / router), create **A** record:
   - `jeeves.ntsa.uk` -> walrus (chair host) LAN IPv4
2. Do **not** create a public DNS or Cloudflare record for `jeeves.ntsa.uk`.
3. Browser / API clients must use a source IP in RFC1918 (`10/8`, `172.16/12`,
   `192.168/16`) or loopback. The server rejects other sources even if DNS is
   wrong.
4. Foundation modules: `common/scripts/jeeves_settings.py` (schema, LAN gate,
   secret-safe GET/PUT, backup/audit/rollback) and
   `common/scripts/jeeves_settings_auth.py` (AD/CredMan + sessions).
5. LAN HTTP UI: see **Enable the LAN HTTP UI (FR #6440)** below.
6. NSSM env migrate/apply is FR #6442 (see **Migrate NSSM env** below).
   Auth is FR #6441 (see **Auth** below). Restart-when-idle + status is FR #6443 (see below).

## Auth (FR #6441)

Settings API/UI require login (authed helpers). FR #6451 wires LAN HTTP to
api_*_authed with POST /api/login, HttpOnly cookie jeeves_appliance_session,
and Authorization: Bearer <token>. Unauthenticated API calls return 401.

1. **LAN first.** Non-RFC1918 sources are rejected before credential checks.
2. **Windows / AD.** Win32 LogonUser network logon via authenticate_windows_logon.
   The login page has one account field (`DOMAIN\user` or `user@domain`; no domain
   input). POST `/api/login` still accepts JSON `domain` from older clients.
   CredMan is tried with the typed string and, when split, the SAM name.
3. **CredMan fallback.** Generic credential target **`Jeeves/ApplianceAdmin`**
   (`CREDMAN_TARGET`). Username + password must match CredMan; missing target
   fails closed.
4. **Sessions.** Successful login returns a random `session_token`. Only the
   SHA-256 hash is stored under chair home `appliance-sessions.json` (actor +
   expiry). TTL default 8h. Passwords are never stored, logged, or returned.
5. **Authed helpers.** api_get_settings_authed / api_put_setting_authed /
   api_rollback_authed reject missing/invalid/expired sessions. Audit actor
   comes from the session (not a caller-supplied spoof). Secret settings still
   return only `set` / `unset`.

## Enable the LAN HTTP UI (FR #6440)

Off by default. On the chair host (walrus), set NSSM / process env and restart `ircJeeves`:

| Env | Purpose |
|-----|---------|
| `JEEVES_SETTINGS_HTTP=1` | Start the LAN listener (alias `JEEVES_SETTINGS_UI=1`) |
| `JEEVES_SETTINGS_HTTP_BIND` | Bind IP (must be RFC1918 or loopback; default `127.0.0.1`) |
| `JEEVES_SETTINGS_HTTP_PORT` | Backend TCP port (default **7701**; operators do not browse this port) |
| `JEEVES_SETTINGS_FRONTDOOR=1` | FR #6757: force bind `127.0.0.1` behind the IIS TLS front door |

Browse **https://jeeves.ntsa.uk/** from a LAN client (FR #6757 / FR #6758). Internal DNS only. Do not publish public DNS or Cloudflare. Do not browse `:7701`. The settings process listens on loopback `:7701` when the front door is enabled; login HTML does not mention that port. Install the front door with `jeeves/scripts/Install-JeevesApplianceFrontDoor.ps1 -Thumbprint <existing cert>` (operator-supplied store thumbprint; no public ACME). HTTP port 80 for that name redirects to HTTPS. The Python LAN check trusts `X-Forwarded-For` only from a loopback TCP peer.
JSON: `GET /api/settings`, `PUT /api/settings/<KEY>`, `POST /api/rollback`, `GET /api/schema`,
`GET /api/status`, `GET /api/queue` (FR #6754), `GET /api/pools` (FR #6760 / FR-12; FR #6759 may extend),
`POST /api/restart-when-idle`.
HTML: `GET /` settings, `GET /status`, `GET /queue` (FR #6755 waiting / in-progress lists).
HTML shell (FR #6756): login, settings, status, queue, and pools share a header with `/assets/ntsa-gut-logo.png` (bytes of `bob/tray/assets/ntsa-gut-logo.png`). Authed pages link Settings, Queue, Pools, Status, Log out. Login omits Log out.

GET /api/settings includes a default field per row (schema default; secrets return "").
The HTML settings table has a **Default** column for every non-secret key (FR #6751 / FR-03).
The Value control keeps the current value; the default is shown beside it and is not written into the control unless it is already current.

Socket-layer gate: the server binds only to LAN/loopback and `verify_request` drops non-RFC1918 peers before handlers run. Helpers also reject non-LAN `client_ip`.

**Never** put this behind Cloudflare, `bob.ntsa.uk`, or `irc.ntsa.uk`. Auth helpers are FR #6441; HTTP cookie/Bearer session wire is FR #6451; NSSM apply is FR #6442; restart-when-idle / status is FR #6443; show defaults is FR #6751.

Module: `common/scripts/jeeves_settings_http.py` (started from `ChairJobs` via `maybe_start_from_chair`).

The settings page lists eight groups. Defaults and checkboxes are on that page.

| Group | Heading |
|-------|---------|
| fuel | Fuel and review waits |
| digest | Digest |
| irc | IRC timing |
| homes | Chair home |
| wake | Wake and ticket closure |
| probes | Webhook probes |
| resync | Resync |
| secrets | Secrets |

Bool SCHEMA keys render as `input type=checkbox` with `value="1"` when truthy (FR #6750 / FR-02). Save posts `"1"` when ticked and `"0"` when cleared. Secret fields left blank are not PUT. `str` / `int` / `float` stay text inputs.

`SettingSpec.choices` defaults to `()`. A non-empty list on a non-bool setting renders a `<select>` (FR #6753 / FR-05). The current value is selected; a value not in the list is added as an extra selected option so save does not silently change it. Bools stay checkboxes. Today's SCHEMA keys have empty choices (paths, URLs, and seconds stay text).


## Restart-when-idle + status (FR #6443)

Read-only status (LAN only):

- HTML: `GET /status` (shared shell + NTSA logo, FR #6756). Token comparison (FR #6784): inline SVG of measured `by_model` totals when the job-cost ledger has measured rows; empty copy and no series when none exist; error copy and no invented bars when the ledger cannot be read. `unknown_jobs` is text beside the chart, never a zero bar. Same session auth as `/status`. Does not add token fields to `GET /api/pools`.
- HTML: `GET /queue` (FR #6755; same shell; waiting / in-progress lists (`repo`, `task`, `id`, optional `worker`). Empty copy is exactly `Nothing is waiting.` / `Nothing is in progress.` Unauthenticated visitors get the login page.) The queue is at `/queue`.
- HTML: `GET /pools` (FR #6760 / FR-12) --- one row per machine from digest `machines.<id>.xai_weekly` via the same document as `GET /api/pools`. Row rules: `[stale]` hides the percent; `0` shows `0%` plus `out of tokens`; a number shows `<n>%`; null non-stale shows `n/a`; empty list shows `No pool readings`. `reset_label` when present. No Cursor spending-group bars. Unauthenticated HTML returns the login page (HTTP 200). Copilot line is sibling FR #6761. Overspend line (FR #6762): when overage_gbp is greater than 0 show the word overspend, the pound sign, and two decimals; null, missing, or 0 omit the line; once per page, not per machine.
- Asset: `GET /assets/ntsa-gut-logo.png` --- PNG bytes of `bob/tray/assets/ntsa-gut-logo.png` (LAN; no session)
- JSON: `GET /api/status` — `version`, `source_commit`, `uptime_s`, `queue`, `seats`, `fuel` (no secrets)
- JSON: `GET /api/queue` (FR #6754) — `ok`, `unaccepted`, `accepted`; each row is `repo`, `task`, `id`, optional `worker` (from stored `worker`, else `nick`). Other queue fields are dropped. Same secret-shape refusal as status.
- JSON: `GET /api/pools` (FR #6760 machine rows; FR #6759 owns richer pool JSON) — `ok`, `machines[]` with `id`, `remaining_pct`, `fuel_stale`, `reset_label` from digest `xai_weekly` only (not Cursor groups). Session required; LAN required. Sibling FR #6759 may add Copilot / overage without changing the `/pools` page contract.

Restart `ircJeeves` only when the accepted queue is empty (no review/job running):

- `POST /api/restart-when-idle` with optional `{"actor":"..."}`
- If accepted work is present, the request is **deferred** to `settings-restart-pending.json` under chair home; `ChairJobs` ticks `tick_restart_when_idle` on the stall cadence and restarts when idle.
- CAST IRON: restarts **ircJeeves** only — never Ergo, never `BobIrcd`.

## Storage

| Artifact | Path under chair home |
|----------|------------------------|
| Config file | `appliance-settings.json` |
| Audit log | `settings-audit.jsonl` |
| Backups | `settings-backups/<id>.json` |
| Sessions | `appliance-sessions.json` (token hashes only) |

Environment variables still override file values; the API shows `source=env`
when that happens. Secret keys return only `set` / `unset` (never plaintext).


## Migrate NSSM env into the chair file (FR #6442)

Settings that used to live only in NSSM `AppEnvironmentExtra` for `ircJeeves`
are inventoriable in `SCHEMA` and stored in `appliance-settings.json` under the
chair home. Process environment values still **override** the file (API shows
`source=env`).

### Safe migration (no secret print)

From an elevated shell on the chair host (after a backup of NSSM parameters):

```powershell
# Dry inventory: Python helpers never print secret plaintext
python -c "import jeeves_settings as j; from pathlib import Path; print(j.migrate_nssm_env_to_file(Path($env:BOB_HOME)))"
```

Or call `jeeves_settings.migrate_nssm_env_to_file(chair_home)` from a maintenance
script. The function:

1. Copies non-empty schema keys from the current process env into
   `appliance-settings.json` (timestamped backup + audit row per key).
2. Writes `set` / `unset` only for secret keys in the audit log (never the
   token/password value).
3. Leaves NSSM env in place until you remove entries; env continues to win
   until removed. Then restart `ircJeeves` so `apply_file_settings` loads the
   file for keys no longer in NSSM.

`jeeves_main` / `jeeves.exe` calls `apply_file_settings(chair_home)` on start so
file-backed values become live when env is unset.

Do **not** paste `GH_TOKEN` / IRC passwords into tickets, chat, or harvest
filings. Prefer CredMan / file permissions on chair home for secrets after
migration.

## Operator notes

- Unused: importing the settings modules does not start a server unless
  JEEVES_SETTINGS_HTTP=1 (FR #6440).
- jeeves_main applies file-backed settings on start (FR #6442); env still overrides.
- Restart-required keys are flagged in the schema; use **Restart-when-idle** (FR #6443)
  so ircJeeves restarts only when accepted work is clear.
