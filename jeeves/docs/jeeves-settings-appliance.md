# Jeeves appliance settings (FR #6436 foundation + FR #6440 LAN HTTP)

Internal-only settings surface for the Ergo chair host. **Never** publish this
on Cloudflare or public DNS. Do **not** front it via `bob.ntsa.uk` or
`irc.ntsa.uk`.

## How to reach it

1. On the internal DNS (LAN AD / router), create **A** record:
   - `jeeves.ntsa.uk` -> walrus (chair host) LAN IPv4
2. Do **not** create a public DNS or Cloudflare record for `jeeves.ntsa.uk`.
3. Browser / API clients must use a source IP in RFC1918 (`10/8`, `172.16/12`,
   `192.168/16`) or loopback. The server rejects other sources even if DNS is
   wrong.
4. Foundation module: `common/scripts/jeeves_settings.py` (schema, LAN gate,
   secret-safe GET, validated PUT, timestamped backups, audit JSONL, rollback).
5. LAN HTTP UI: see **Enable the LAN HTTP UI (FR #6440)** below.
6. AD/CredMan login (FR #6441) and restart-when-idle / status (FR #6443) remain child FRs.
   NSSM env migrate/apply is FR #6442 (see **Migrate NSSM env** below).


## Enable the LAN HTTP UI (FR #6440)

Off by default. On the chair host (walrus), set NSSM / process env and restart `ircJeeves`:

| Env | Purpose |
|-----|---------|
| `JEEVES_SETTINGS_HTTP=1` | Start the LAN listener (alias `JEEVES_SETTINGS_UI=1`) |
| `JEEVES_SETTINGS_HTTP_BIND` | Bind IP (must be RFC1918 or loopback; default `127.0.0.1`) |
| `JEEVES_SETTINGS_HTTP_PORT` | TCP port (default **7701**) |

Browse `http://jeeves.ntsa.uk:7701/` from a LAN client (or `http://127.0.0.1:7701/` on the host).
JSON: `GET /api/settings`, `PUT /api/settings/<KEY>`, `POST /api/rollback`, `GET /api/schema`.

Socket-layer gate: the server binds only to LAN/loopback and `verify_request` drops non-RFC1918 peers before handlers run. Helpers also reject non-LAN `client_ip`.

**Never** put this behind Cloudflare, `bob.ntsa.uk`, or `irc.ntsa.uk`. AD/CredMan login is FR #6441; restart-when-idle / status is FR #6443.

Module: `common/scripts/jeeves_settings_http.py` (started from `ChairJobs` via `maybe_start_from_chair`).

## Storage

| Artifact | Path under chair home |
|----------|------------------------|
| Config file | `appliance-settings.json` |
| Audit log | `settings-audit.jsonl` |
| Backups | `settings-backups/<id>.json` |

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
  `JEEVES_SETTINGS_HTTP=1` (FR #6440).
- `jeeves_main` applies file-backed settings on start (FR #6442); env still overrides.
- Restart-required keys are flagged in the schema; idle restart is child FR #6443.
