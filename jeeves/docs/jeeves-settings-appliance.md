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
4. Foundation module: `common/scripts/jeeves_settings.py` (schema, LAN gate,
   secret-safe GET, validated PUT, timestamped backups, audit JSONL, rollback).
5. HTTP listener, AD/CredMan login UI, and NSSM apply path are **child FRs**
   after this foundation. Until those land, operators use the Python helpers /
   future CLI against chair home (`~\.jeeves`).

## Storage

| Artifact | Path under chair home |
|----------|------------------------|
| Config file | `appliance-settings.json` |
| Audit log | `settings-audit.jsonl` |
| Backups | `settings-backups/<id>.json` |

Environment variables still override file values; the API shows `source=env`
when that happens. Secret keys return only `set` / `unset` (never plaintext).

## Operator notes

- Unused: importing the module does not start a server and does not change
  chair behaviour.
- Restart-required keys are flagged in the schema; foundation does not restart
  `ircJeeves` (child FR: restart when idle).
