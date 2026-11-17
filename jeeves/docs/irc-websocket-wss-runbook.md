# IRC-over-WebSocket (WSS) runbook — FR #7999

Customer egress firewalls reset TLS on the IRC listener ports (993/6697) while
ordinary HTTPS on 443 survives. Airc falls back to IRC-over-WebSocket (RFC 6455,
Ergo's native `websocket` listener, subprotocol `text.ircv3.net` / `binary.ircv3.net`)
through a Cloudflare-proxied hostname. This runbook installs the server side.

Replace `<ws-host>` and `<path>` with the approved hostname and route path. Do
not hard-code customer names or secrets here.

## 1. Ergo: loopback WebSocket listener

Edit Ergo's `ircd.yaml` (do **not** touch the existing `:993` / `:6697` TLS
listeners) and add a loopback-only WebSocket listener:

```yaml
server:
  listeners:
    # ... existing TLS listeners unchanged ...
    "127.0.0.1:<ws-port>":
      websocket: true
  websockets:
    allowed-origins:
      - "https://<ws-host>"
  # Trust X-Forwarded-For from the loopback reverse proxy only.
  proxy-allowed-from:
    - "127.0.0.1"
    - "::1"
```

- `<ws-port>` is a free loopback port (for example 8765). It is **not** exposed
  to the network, so do **not** add a firewall rule for it.
- `proxy-allowed-from` scoped to loopback so Ergo trusts the `X-Forwarded-For`
  header only from IIS, never from a client that bypasses the proxy.
- Restart only Ergo: `Restart-Service BobIrcd` (or the local Ergo restart for
  this install). Leave the 993/6697 listeners and `BobIrcd` service name as-is.

## 2. IIS: reverse proxy with WebSocket upgrade

1. Install the **WebSocket Protocol** role service
   (`Install-WindowsFeature Web-WebSockets`), plus **Application Request
   Routing (ARR)** and **URL Rewrite** if not present.
2. Verify the ARR proxy is enabled (not best-effort):
   `Get-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter 'system.webServer/proxy' -Name enabled`
   → must be `True`. If not, enable it (`Set-WebConfigurationProperty ... enabled -Value $true`).
3. Create a **dedicated IIS site** for `<ws-host>` with an HTTPS **443** binding
   (origin certificate matching `<ws-host>`).
4. Add a URL Rewrite rule from `<path>` to `http://127.0.0.1:<ws-port>/` with
   **WebSocket upgrade enabled** (rule `WebSocket`, not `HTTP`).

Do **not** host the route on the `irc-ntsa` site: `jeeves/scripts/Install-BobWebhooks.ps1`
regenerates that site's rewrite rules and would overwrite a manual WebSocket rule.

## 3. Cloudflare

- Create a **proxied** DNS record (`orange cloud`) for `<ws-host>` → the
  public address of the IIS box.
- Set the zone/domain SSL/TLS mode to **Full (strict)**.
- Turn **WebSockets** on (`Network` → `WebSockets`).
- Confirm the WAF / bot rules do not block the upgrade request; if needed, add a
  WAF exception for `<ws-host>/<path>`.

Cloudflare drops idle WebSockets after ~100 s. Airc's IRC keepalive sends a
`PING` after 60 s idle, which keeps the tunnel alive.

## 4. Verify

1. Loopback upgrade returns `101` with `text.ircv3.net`:

   ```powershell
   $r = Invoke-WebRequest -Uri "http://127.0.0.1:<ws-port>/" -Headers @{
     Upgrade = 'websocket'; Connection = 'Upgrade';
     'Sec-WebSocket-Key' = 'dGhlIHNhbXBsZSBub25jZQ=='; 'Sec-WebSocket-Version' = '13'
   }
   # expect status 101 Switching Protocols (via a raw HTTP client; Invoke-WebRequest may not surface it)
   ```

2. Public upgrade returns `101`:

   ```powershell
   # expect 101 Switching Protocols over HTTPS
   curl.exe -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" `
     -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" `
     "https://<ws-host><path>"
   ```

3. Airc registers over WSS (change in situ, no reinstall):

   ```powershell
   setx /M AIRC_IRC_TRANSPORT wss
   setx /M AIRC_IRC_WS_URL "wss://<ws-host><path>"
   Restart-Service Airc
   # log line: INFO registered via transport=wss wss://<ws-host>:443<path>
   ```

### Rollback

- Remove the `AIRC_IRC_TRANSPORT` / `AIRC_IRC_WS_URL` machine variables and
  `Restart-Service Airc` (falls back to `wss,tls` → WSS first, then 993/6697).
- To force raw TLS IRC only: `AIRC_IRC_TRANSPORT=tls` with `AIRC_IRC_PORT=993`
  or `6697`, then `Restart-Service Airc`.
- Remove the Cloudflare record, the IIS site, and the Ergo WebSocket listener to
  fully undo; leave 993/6697 untouched throughout.

## 5. Record

Approved endpoint: `wss://<ws-host><path>`.

`DEFAULT_IRC_WS_URL` in `airc/scripts/airc_console_service.py` must hold this
value before release. Do not release until Slab confirms the route on walrus and
the constant matches.
