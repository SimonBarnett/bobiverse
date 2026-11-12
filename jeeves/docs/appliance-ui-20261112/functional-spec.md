# Functional spec: Jeeves appliance UI

Baseline: origin/main modules common/scripts/jeeves_settings.py, jeeves_settings_auth.py, jeeves_settings_http.py. The live login page is a username field, a separate domain field, and a password field. Settings render as one table of text inputs. Status shows queue counts only. The listener defaults to port 7701.

## Account

- The login form posts username and password only.
- If the username contains `\`, split on the first backslash into domain and sam. This already exists when the domain argument is empty.
- If the username contains `@` and no backslash, split on the first `@`: sam is the left side, domain is the right side.
- A JSON domain property on POST /api/login still overrides an empty parse, so old clients keep working.
- CredMan is tried after Windows logon fails. Match the typed string, and also the sam account name when a split happened.
- Passwords are never logged, stored, or written into the error text.

## Settings page

- SettingSpec gains group, group_title, and group_description. Every SCHEMA key has them.
- SettingSpec gains choices, default empty. A non-empty choices tuple renders a select. Bools ignore choices and render a checkbox.
- GET /api/settings includes default for non-secret keys and an empty default for secrets. The HTML shows that default beside the control.
- Checkbox checked value is 1. The save script sends 0 for an unchecked checkbox. Empty secret fields are still skipped.
- Sections follow the group table in the feature request. Each section heading is the group title. The description is the first line under the heading.

## Queue

- GET /api/queue requires a session and a LAN client.
- Response shape: `{ "ok": true, "unaccepted": [row], "accepted": [row] }`.
- A row may contain only repo, task, id, and worker. worker is copied from the stored row's worker field, else its nick field, else omitted.
- GET /queue renders the two lists. Empty list text is "Nothing is waiting." and "Nothing is in progress."
- The payload is refused if it contains a secret-shaped value, same rule as status.

## Shell

- Login, settings, status, and queue share one header: the NTSA logo, the word Jeeves, and links Settings, Queue, Status, Log out.
- GET /assets/ntsa-gut-logo.png returns the bytes of bob/tray/assets/ntsa-gut-logo.png.
- Login is a card with the logo, one account field labelled User name, a password field, and a Sign in button.

## TLS front door

- Operator URL is https://jeeves.ntsa.uk/.
- When the front door is enabled, the settings process binds 127.0.0.1 only.
- The front door terminates TLS with a certificate the operator names (thumbprint or store). This pack does not request a public certificate and does not create public DNS.
- Port 80 on that name redirects to HTTPS.
- Client IP: if the TCP peer is loopback, read X-Forwarded-For and run the LAN check on that address. If the TCP peer is not loopback, ignore X-Forwarded-For and run the LAN check on the peer. Non-LAN fails closed.
- Docs still say the name is internal DNS only, and still say not to publish the UI on bob.ntsa.uk or irc.ntsa.uk.

## Pools

The systray TipForm on origin/main shows one Grok remaining percent per machine, one account-wide Copilot line, and an overspend line when the GBP amount is above zero. Cursor spending-group bars were removed from that card. The appliance shows those same figures and does not bring the bars back.

- GET /api/pools requires a session and a LAN client.
- machines[] keeps id, remaining_pct, fuel_stale, reset_label. remaining_pct is a number or null. 0 stays 0. null stays null.
- copilot keeps the fields the tray line needs: remaining, state, reset_at, fetched_at, unlimited, used, max_recorded_usage. Other digest fields are dropped.
- overage_gbp is a number or null.
- The page is GET /pools. It is linked from the shell. It does not edit settings.
- A stale machine shows [stale] and hides the percent. A null percent that is not stale shows n/a. A non-stale 0 shows out of tokens.
- The Copilot sentence matches the tray: Copilot - N% left, or Copilot - unknown when the pool is missing. A stale reading keeps the tray stale marker.
- The overspend line is present only when overage_gbp is greater than 0. The text is the word overspend, the pound sign, and the amount to two decimals.
- Empty machine list copy is No pool readings.

## Out of scope

- Allowing a non-LAN source. Draft only: fr/HOLD-external-access.md.
- Changing queue ordering, fuel behaviour, or the restart-when-idle rule.
- Drawing a new logo.
