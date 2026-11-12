# Feature request: Jeeves appliance UI

Existing repo: SimonBarnett/bobiverse. Parent surface: closed FR #6436 and PRs #6444, #6446, #6450, #6449, #6454, #6459 on origin/main (tip ea2a40ca at planning time).

The chair already serves a LAN settings UI. This request makes that UI clearer and gives it a hostname with TLS, without opening it to the public internet.

## Objective

An operator on the LAN signs in to https://jeeves.ntsa.uk/ with one Windows account box, edits grouped settings that show their defaults, and reads the current queue on its own page.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Published URL | https://jeeves.ntsa.uk/ | jeeves/docs/jeeves-settings-appliance.md states that URL, and rendered login HTML contains no :7701 | doc or login HTML still tells the operator to open port 7701 |
| S2 | Account field | one account input | login HTML has a single account text input and no name="domain" input; unit test splits DOMAIN\user and user@domain | a domain field remains, or user@domain is passed to LogonUser as the whole username |
| S3 | Bool control | checkbox, saved as 1 or 0 | renderer test for every type=bool key; save test sends 0 when unchecked | a bool renders type=text, or an unchecked box is omitted |
| S4 | Defaults visible | schema default on every non-secret row | HTML test for BOB_CODERABBIT_WAIT_MIN shows 12; secret row for GH_TOKEN has an empty default | a non-secret default is missing, or a secret default is echoed |
| S5 | Groups | 8 groups, 100% of keys assigned | test walks SCHEMA and the settings HTML headings | any key has an empty group, or a heading has no description |
| S6 | Queue page | authed GET /queue is 200 | fixture with one unaccepted row and zero accepted rows; empty state test with both lists empty | /queue is 404, or a row field outside repo/task/id/worker is returned |
| S7 | Logo | git PNG on login, settings, and queue | GET /assets/ntsa-gut-logo.png body equals bob/tray/assets/ntsa-gut-logo.png; those three pages include that path | the img is missing, or the bytes differ from the git file |
| S8 | LAN gate | non-RFC1918 rejected | existing LAN test extended to /queue, /api/queue, and the asset route | a non-LAN client receives 200 |
| S9 | External access | still closed | docs keep the internal-DNS instruction; no issue in this batch enables public clients | a merged change tells the operator to publish public DNS |
| S10 | Machine pool percent | same remaining percent the tray row shows | GET /api/pools fixture: remaining_pct 0 stays 0; null stays null; /pools HTML shows out of tokens for 0 and n/a for null | null is rendered as 0, or a Cursor spending-group bar is drawn |
| S11 | Copilot line | the tray sentence | fixture remaining 37 renders Copilot - 37% left; a missing pool renders Copilot - unknown | the page invents a percent, or omits the Copilot line |
| S12 | Overspend line | shown only when GBP is above 0 | fixture overage_gbp 1.5 renders the overspend line; null and 0 render no line | a zero overspend is shown, or the amount is dropped |

## Shape

Primary: **service**

The pages are a surface of the ircJeeves chair. The product remains the chair service.

LOCKED

## Stack

Default: the existing chair Python modules common/scripts/jeeves_settings.py, jeeves_settings_auth.py, and jeeves_settings_http.py, plus a TLS front door on the chair host.

Why: the listener, schema, sessions, and LAN gate already exist. A new web framework would rewrite a working appliance.

Why-not: a separate website repo, a public CDN, or a new identity provider. Windows logon and CredMan already authenticate the page.

LOCKED

## Architecture

The browser speaks TLS to the chair front door for jeeves.ntsa.uk. The front door talks to 127.0.0.1:7701 and passes the browser address. The app trusts X-Forwarded-For only from that loopback peer, then applies the existing RFC1918 check. Sessions, the settings file, and the queue read stay inside the chair process.

```
browser -- TLS 443 --> chair front door (jeeves.ntsa.uk)
                          | loopback + client IP
                          v
                     settings HTTP 127.0.0.1:7701
                          | session cookie
                          v
                     SCHEMA / appliance-settings.json
                     gitclaim queue (whitelist fields)
```

LOCKED

## Screens

HTML mocks in docs/mocks/. No generated PNGs. The logo file is a copy of bob/tray/assets/ntsa-gut-logo.png so the mocks can show the mark already in git.

| id | file | state |
|----|------|-------|
| M1 | docs/mocks/home.html | settings, grouped |
| M2 | docs/mocks/empty.html | queue, both lists empty |
| M3 | docs/mocks/error.html | login rejected |
| M4 | docs/mocks/login.html | login ready |
| M5 | docs/mocks/queue.html | queue with rows |
| M6 | docs/mocks/pools.html | pool percents, Copilot, overspend |

## Groups

| group | heading | description | keys |
|-------|---------|-------------|------|
| fuel | Fuel and review waits | Which review fuels run, and how long CodeRabbit is given | BOB_FUEL_CODERABBIT, BOB_CODERABBIT_WAIT_MIN, BOB_CODERABBIT_ABSENT_SEC, BOB_FUEL_COPILOT, BOB_FUEL_FLEET, BOB_COPILOT_OBSERVE |
| digest | Digest | Where the digest lives and when it counts as stale | BOB_DIGEST_HOME, BOB_DIGEST_URL, BOB_DIGEST_STALE_S, BOB_PUBLIC_BASE |
| irc | IRC timing | Bored idle and IRC reconnect timing. Passwords are under Secrets | BOB_BORED_IDLE_S, BOB_IRC_IDLE_DEAD_S, BOB_IRC_IDLE_PING_S, BOB_IRC_RECONNECT_MAX, BOB_IRC_RECV_TIMEOUT_S, BOB_IRC_THROTTLE_BASE_S, BOB_IRC_SASL_USER |
| homes | Chair home | Overrides for the chair home directory | JEEVES_HOME, BOB_JEEVES_HOME |
| wake | Wake and ticket closure | How Jeeves wakes Bob when work closes or stalls | JEEVES_TICKET_CLOSURE_S, JEEVES_TICKET_CLOSURE_WAKE, JEEVES_TICKET_CLOSURE_WAKE_URL, JEEVES_BOB_WAKE_URL |
| probes | Webhook probes | Bases the chair uses to probe local and public webhooks | JEEVES_PROBE_LOCAL, JEEVES_PROBE_PUBLIC |
| resync | Resync | Which repos the chair resyncs | JEEVES_RESYNC_REPOS |
| secrets | Secrets | Write-only. The page shows set or unset, never the value | JEEVES_TICKET_CLOSURE_WAKE_SECRET, JEEVES_BOB_WAKE_SECRET, GH_TOKEN, GITHUB_TOKEN, BOB_IRC_PASSWORD, BOB_IRC_SASL_PASSWORD |

Keys added to SCHEMA after ea2a40ca take a group in the same change. A key with an empty group fails the test.

## Small FR drafts

Unfiled until a later park approval. One issue each. Bodies in fr/. HOLD is not filed.

| id | draft | slice |
|----|-------|-------|
| FR-01 | #6749 | one account field |
| FR-02 | #6750 | bool checkboxes |
| FR-03 | #6751 | show defaults |
| FR-04 | #6752 | groups |
| FR-05 | #6753 | select when choices exist |
| FR-06 | #6754 | queue JSON |
| FR-07 | #6755 | queue page |
| FR-08 | #6756 | shell and logo |
| FR-09 | #6757 | HTTPS URL, no port |
| FR-10 | #6758 | appliance doc |
| FR-11 | #6759 | pool JSON |
| FR-12 | #6760 | machine pool rows |
| FR-13 | #6761 | Copilot line |
| FR-14 | #6762 | overspend line |
| HOLD | not filed | external access |

## LOCKED

- Shape is service.
- Published URL is https://jeeves.ntsa.uk/ with no port.
- Login is one account field: DOMAIN\user or user@domain.
- Eight groups above, with those descriptions.
- Bools are checkboxes saved as 1 or 0.
- Non-secret defaults are visible. Secrets stay write-only.
- Queue page and queue JSON whitelist repo, task, id, worker.
- Logo bytes are bob/tray/assets/ntsa-gut-logo.png.
- LAN rejection stays on every route.
- External access stays closed in this batch.
- Restart still restarts ircJeeves only, and only when idle.
- Do not front the UI on bob.ntsa.uk or irc.ntsa.uk.
- The pools page shows the systray figures: per-machine Grok remaining percent, the Copilot line, and the overspend line. Cursor spending-group bars stay off the page. A null percent stays n/a. Zero stays zero.

## UNKNOWN

- Whether non-LAN clients may connect. See fr/HOLD-external-access.md. Do not file until the operator says yes.
- Which CA issues the certificate. FR-09 takes a certificate the operator already has.
