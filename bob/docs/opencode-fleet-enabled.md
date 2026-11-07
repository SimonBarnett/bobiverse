# OpenCode-enabled fleet boxes (no secrets)

FR #6160 / FR-OC-FLEET. How operators see which machines can run OpenCode seats
**without** reading keys, auth bodies, or private host details beyond the public digest.

## How to tell a box is OpenCode-capable

1. **Local smoke (on the box):**
   `.\scripts\Assert-BobOpencodeFleetSmoke.ps1 -SkipPong`
   (add live pong when network/auth allow). Exit 0 means PATH + auth presence/ACL
   (+ dry-run `opencode_cmd`) look healthy.
2. **Digest / TipForm:** public report `https://bob.ntsa.uk/bob/v1/report` may show
   `machines.<id>.pcent.opencode-free` / `opencode-go` when the ear publishes known
   fuel (FR #6146 / #6147). Presence of those keys means the box is publishing
   OpenCode fuel; it does **not** print credentials.
3. **Shop kind:** when a seat runs OpenCode, digest / chair rows may show
   `kind=opencode`. Chair gate FR #6134 skips MRB/UAT offers to that seat.

## What never goes in this note

- API keys, `auth.json` body, tokens, passwords, NickServ/SASL values
- Full paths that embed secrets
- Private operator hostnames beyond the fleet machine id already on the digest

## Ops roll call (fill per site; machine ids only)

| machine id | smoke date (UTC) | Assert exit | notes (no secrets) |
|------------|------------------|-------------|--------------------|
| *(example)* marchhare | | 0 | winget 1.x; dry-run sees opencode_cmd |
| | | | |

Update this table when a box first passes Assert (or fails for a durable reason).
Do not paste auth paths with user profile secrets beyond the standard
`%USERPROFILE%\.local\share\opencode\auth.json` pattern already in the setup skill.

## Trial metrics template (optional, FR #6120)

Per box or per week, copy into an ops comment or harvest note:

```text
OpenCode trial metrics
machine_id:
window_utc:
prs_attempted:
first_mrb_pass: yes|no|n/a
fuel_note: free_pct= / go_pct= / n/a (from digest or TipForm only)
Assert-BobOpencodeFleetSmoke: exit=
```

Never attach key material or auth.json excerpts to the metrics note.
