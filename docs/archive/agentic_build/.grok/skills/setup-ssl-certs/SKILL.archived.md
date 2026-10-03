<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/setup-ssl-certs/SKILL.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: setup-ssl-certs
description: >
  Issue and bind a free Let's Encrypt certificate on IIS with
  win-acme. Use when the user says set up SSL, free SSL, Let's
  Encrypt, win-acme, HTTPS binding, cert for IIS, irc.ntsa.uk SSL
  for webhooks, or /setup-ssl-certs. GitHub hook create is
  setup-github-webhooks. Ergo :6697 PEM is bob-irc / agentic_irc.
---

# Set up SSL certs (IIS + win-acme)

Free cert = Let's Encrypt via win-acme. This box already has
`C:\ai\win-acme\wacs.exe` (2.2.9) and ACME data under
`C:\ProgramData\win-acme`. Contact `si@ntsa.uk`. Scheduled task
`win-acme renew (acme-v02.api.letsencrypt.org)`.

## Before you issue

1. DNS A record for each hostname points at this machine
   (ionos public `217.154.57.228`).
2. IIS site has an **http** hostname binding on port 80 (HTTP-01).
3. Inbound **80** and **443** open (Windows firewall + IONOS panel).
   Policy "Being configured" flaps the port.
4. `http://<host>/` returns 200 from the intended site.

Do **not** replace an existing win-acme renewal that stores PEM
for a different service. Ergo TLS on :6697 is
`C:\ai\ergo` + `install-cert.ps1` (friendly name
`[Manual] irc.ntsa.uk`). IIS webhooks are a **second** renewal.

## Issue and bind (IIS)

Site `irc-ntsa` is id **12**, webroot `C:\inetpub\irc-ntsa`,
hosts `irc.ntsa.uk` and `bob.ntsa.uk`.

```
New-Item -ItemType Directory -Force -Path C:\inetpub\irc-ntsa\.well-known\acme-challenge
C:\ai\win-acme\wacs.exe --source iis --siteid 12 --host irc.ntsa.uk,bob.ntsa.uk --commonname irc.ntsa.uk --validation filesystem --validationsiteid 12 --webroot C:\inetpub\irc-ntsa --store certificatestore --certificatestore My --installation iis --accepttos --emailaddress si@ntsa.uk --friendlyname "IIS irc-ntsa webhook" --verbose
```

Filesystem HTTP-01 writes under the site webroot. Self-hosting on
:80 fights IIS. `--friendlyname` must stay distinct from the Ergo
PEM renewal.

win-acme creates SNI `https` bindings (`*:443:<host>`, sslFlags 1)
and a renewal row. Next due ~60 days minus 55-day renew window.

Other IIS sites: same command, change `--siteid`, `--host`,
`--webroot`, `--friendlyname`. One cert can list several names
(`--host a,b`).

## Check

```
Get-WebBinding -Name <site>
# https *:443:<host> CertificateHash set, sslFlags 1
```

TLS handshake `CN=` + SAN must include the hostname. Browser or
`Invoke-WebRequest https://<host>/` is 200. For the webhook site,
`GET https://irc.ntsa.uk/bob/v1/report` and `/bob/v1/git` are 405.

## After HTTPS is up

Fleet digest URL lives in `config/bobiverse.json` as `reportUrl`
`https://irc.ntsa.uk/bob/v1/report`. Keep port 80 for ACME renewals.

GitHub will now accept hooks. Skill `setup-github-webhooks`.

## Do not

- Overwrite `C:\ai\ergo\*.pem` or run `install-cert.ps1` for IIS.
- Recycle `BobIrcd` for an IIS cert.
- Force-redirect all HTTP (breaks HTTP-01).
- Stamp UAT.
