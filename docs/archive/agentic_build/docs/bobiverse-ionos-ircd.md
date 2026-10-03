<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/bobiverse-ionos-ircd.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Bobiverse IRC on ionos (Ergo)

Libera banned `bob-ionos`. Fleet status now targets a private Ergo on this IONOS box.

| | |
|---|---|
| Server | Ergo 2.19.1 `C:\ai\ergo\ergo.exe` |
| Name | `irc.ntsa.uk` |
| Listen | TLS `:6697` only (loopback `:6667` stays localhost) |
| Channel | `#bobiverse` (same nicks) |
| Auth | IRC `PASS` (bcrypt in `ircd.yaml`; plaintext in `~\.grok\ergo\connect.password`) |
| Service | `BobIrcd` (Automatic, LocalSystem, NSSM wraps `C:\ai\ergo\ergo.exe`). Start: `Start-Service BobIrcd`. Recycle: `Restart-Service BobIrcd`. Status Stopped / no `ergo.exe` means down. |
| Firewall | IONOS Cloud Panel inbound TCP 6697 **and** Windows rule `Bobiverse IRC TLS 6697`. Do not open public `:6667`. |

Let’s Encrypt for `irc.ntsa.uk` is live (issued 2026-09-20, HTTP-01). Ergo serves that cert on :6697. win-acme renews into `C:\ai\ergo\*.pem`; use `tools/Install-BobIrcdCert.ps1` (or a copy under `C:\ai\ergo`) as the renewal script. It restarts service `BobIrcd`, then `Start-Service BobJeeves` when that chair service is installed. It does not touch scheduled tasks.

## Jeeves (digest chair, starts with BobIrcd)

| | |
|---|---|
| Service | `BobJeeves` (Automatic). **Canonical:** gh-Jeeves `Install-BobJeeves.ps1` (`python -m jeeves`). **Legacy:** NSSM, depends on `BobIrcd`. |
| Nick | `Jeeves` (exactly one; never `Jeeves_`) |
| IRC home | `~\.agentic-irc-jeeves` (`--home`). Not the bob-ionos home. |
| Digest home | `BOB_DIGEST_HOME` = `~\.agentic-irc-bobiverse` (`chair-outbox.txt` / queue; same place `POST /bob/v1/git` writes) |
| Command (legacy) | `python -u scripts/irc_agent.py … --chair` via this repo’s NSSM wrapper |
| Command (canonical) | `python -m jeeves` via [gh-Jeeves](https://github.com/SimonBarnett/gh-Jeeves) (FR #330 / gh-Jeeves #1 token-less gate) |
| Password | From secure store / `connect.password` path only; never git; never printed |
| Install | Prefer `gh-Jeeves/tools/Install-BobJeeves.ps1 -Apply -Production`. Legacy: `tools/Install-BobJeeves.ps1 -AllowLegacyAgenticIrc` |

`fleet_digest_home()` uses `BOB_DIGEST_HOME`. The service sets it. A Jeeves process without that env drains `~\.agentic-irc-jeeves\chair-outbox.txt` and leaves GIT lines on the digest home.

Boot starts `BobIrcd`, then `BobJeeves`. Stopping `BobIrcd` stops `BobJeeves`. Starting `BobIrcd` does not start dependents. After any Ergo recycle, including cert renewal:

```powershell
Restart-Service BobIrcd
Start-Service BobJeeves
```

Watch-Bobiverse does not start Jeeves. Do not pass `--hello` or `--announce-key` on this seat.

The old logon task `BobIrcd-ionos` is unregistered by `tools/Install-BobIrcd.ps1`. Do not `Start-ScheduledTask BobIrcd-ionos`. Do not `Stop-ScheduledTask BobFleet-*` for IRC recovery. Fleet tray/jobs stay logon tasks, not services.

The IONOS **hardware** firewall (Cloud Panel: Network > Firewall Policies) defaults to 80/443/3389. Windows `New-NetFirewallRule` does not open that panel. 80/443 up with 6697 down is the panel. Status "Being configured" flaps the port; wait until Active. Canonical join/recycle: `agentic_irc` skill `bob-irc`.

Copy `~\.grok\ergo\connect.password` to flamingo / marchhare / DEV1 out of band (same path). Pull `agentic_build` + `agentic_irc` (`PASS` support). Recycle **Watch-Bobiverse only** on those boxes. Never commit the password.

## Channel registration and durable ops (FR #327)

LOCKED 27 / A23 needs durable op: `bob-{machine}` in `#{machine}`, `Jeeves` in
`#bobiverse`. Ergo must have **channel registration on** and public **account**
registration **off**.

| | |
|---|---|
| Patch | `tools/Set-BobIrcdChannelRegistration.ps1` (also called from `Install-BobIrcd.ps1`) sets `channels.registration.enabled: true` and keeps `accounts.registration.enabled: false` |
| Decision helper | `tools/Ergo-FleetChannelOps.ps1` — `Test-BobErgoShouldOp` / `Test-BobErgoStandingBotOp` (pure; unit-tested) |
| Fleet registry | `config/ergo-fleet-registry.example.json` → copy to `~\.grok\ergo\fleet-registry.json` (certfp → machine; not secrets in git) |
| Bots | SASL via existing `AGENTIC_IRC_SASL_USER` / `AGENTIC_IRC_SASL_PASSWORD` (provisioned per box outside git, same class as connect password) |
| Standing +o | After oper `NS SAREGISTER` + nick reservation: ChanServ founder/AMODE +o for `Jeeves` on `#bobiverse` and each `bob-{machine}` on `#{machine}` |
| simon | **No standing AMODE.** +o only when (a) logged into account `simon` and (b) TLS client certfp is in the fleet registry for a machine. Shared NAT cloak alone is **not** enough (marchhare and flamingo share a cloak). Grant is done by the channel op bot; revoke if the check fails. |
| Live ionos | Operator-only after review. CI and agents **must not** change live Ergo on ionos without Simon. |

```powershell
# On ionos (operator), after reviewing the yaml diff:
powershell -NoProfile -File C:\ai\agentic_build\tools\Set-BobIrcdChannelRegistration.ps1 -ErgoRoot C:\ai\ergo
# Then oper steps (NS SAREGISTER / CERT ADD / CS AMODE) using secrets outside git.
Restart-Service BobIrcd
Start-Service BobJeeves
```

## Do not

- Point `irc_agent` at `irc.libera.chat`
- Open public `:6667`
- Run two Watch-Bobiverse processes (Libera banned the reconnect flood)
- Put SASL passwords, connect passwords, or real client private keys in git
- Grant simon standing ChanServ op on any channel
- Treat Ergo IP cloak alone as proof of a fleet machine
