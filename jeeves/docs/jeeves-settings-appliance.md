# Jeeves appliance settings (FR #6436 foundation)

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
4. Foundation modules: `common/scripts/jeeves_settings.py` (schema, LAN gate,
   secret-safe GET/PUT, backup/audit/rollback) and
   `common/scripts/jeeves_settings_auth.py` (AD/CredMan + sessions).
5. HTTP listener / HTML UI is child FR #6440 (wires auth sessions). NSSM apply
   is #6442. Until the UI lands, operators exercise the Python helpers against
   chair home (`~/.jeeves`).

## Auth (FR #6441)

Settings API/UI must require login.

1. **LAN first.** Non-RFC1918 sources are rejected before credential checks.
2. **Windows / AD.** Win32 LogonUser network logon via authenticate_windows_logon.
   Prefer DOMAIN\user or pass domain separately.
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
6. HTTP login form / cookie wire-up is child FR #6440.

## Storage

| Artifact | Path under chair home |
|----------|------------------------|
| Config file | `appliance-settings.json` |
| Audit log | `settings-audit.jsonl` |
| Backups | `settings-backups/<id>.json` |
| Sessions | `appliance-sessions.json` (token hashes only) |

Environment variables still override file values; the API shows `source=env`
when that happens. Secret keys return only `set` / `unset` (never plaintext).

## Operator notes

- Unused: importing the modules does not start a server and does not change
  chair behaviour.
- Restart-required keys are flagged in the schema; foundation does not restart
  `ircJeeves` (child FR: restart when idle).
