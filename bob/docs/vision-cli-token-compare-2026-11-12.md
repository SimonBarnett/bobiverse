# Vision: CLI token comparison on the Jeeves appliance

Feature request on `SimonBarnett/bobiverse`. Gap base: `origin/main` `b429d9b1`.
No new repo. Shape stays the chair service.

## Objective

A finished Grok or Cursor CLI job records the same measured token fields OpenCode already records, those rows can be compared by model, and the Jeeves appliance status page draws that comparison. The appliance login page is https://bob.ntsa.uk/jeeves.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Grok CLI model tokens | A fixture `usage.json` whose `modelUsage` entry has input 100, output 20, cached 5 produces a DONE stamp `tokens_in=100 tokens_out=20 tokens_cached=5` and `model=` set to that entry. The ledger row matches. | `pytest` on `done_usage` and worker `measure_done_usage` with the fixture. No live xAI call. | The file has those counts and the stamp is `tokens=unknown`, or the counts are attributed only to `primaryModelId` while `modelUsage` names a different model. |
| S2 | Cursor CLI tokens | A non-zero local or fixture source for that chat stamps the same three fields and `model=`. A missing source, or a store whose token fields are absent or zero, stamps `tokens=unknown`. | `pytest` with a counts fixture and a zero or missing fixture. | A zero local store becomes `tokens_in=0`, or a non-zero fixture is dropped. |
| S3 | Model comparison | Two measured Grok rows, one measured Cursor row, and one unknown row roll up to two model buckets. Token sums match the measured rows. `unknown_jobs` is 1 and is not added into the token sums. | `pytest` on the ledger rollup in `common/scripts/job_cost_ledger.py`. | Models are merged into one bucket, or unknown jobs are counted as zero tokens. |
| S4 | Appliance token graph | The status page renders three states: a by-model token series when rows exist, an empty state when no measured row exists, and an error state when the ledger cannot be read. | `pytest` renders the three HTML bodies. Mocks: `bob/docs/mocks/cli-token-compare/home.html`, `empty.html`, `error.html`. | `/status` still shows only fuel names, or the empty ledger draws a zero-valued series. |
| S5 | Appliance login URL | GET https://bob.ntsa.uk/jeeves returns the login page. The page shows `jeeves/assets/jeeves-butler.ico`. `jeeves/www/irc-ntsa/index.html` links to `/jeeves`. Settings and status still require the session cookie. | Rendered login HTML contains `jeeves-butler.ico` and a password field. `index.html` contains `href="/jeeves"`. A route test maps GET `/jeeves` to that HTML and the response is not 403. Settings and status without the session cookie are rejected. The appliance doc contains `https://bob.ntsa.uk/jeeves`. | The login page is only on `jeeves.ntsa.uk` or port 7701, the butler image is a new drawing, the Bob home page has no `/jeeves` link, settings or status open without the session cookie, or the appliance doc still tells the operator to browse `jeeves.ntsa.uk`. |

LOCKED

## Shape

Primary: **service**

Hybrid note: ircJeeves remains the product. The appliance status page is an existing chair companion. These graphs extend that page.

LOCKED

## Stack

Default: chair Python in `common/scripts/done_usage.py`, `common/scripts/job_cost_ledger.py`, and `common/scripts/jeeves_settings_http.py`, plus the worker DONE stamp in `bob/scripts/bob_worker.py`. Graphs are inline SVG fed by a read-only JSON rollup.

Why: the stamp, the ledger, and the status page already exist.

Why-not: a chart SaaS, a new frontend, or the Cursor dashboard Admin API. Dollar cost and `costUsdTicks` stay out.

LOCKED

## Architecture

Who talks to what. Readers take model ids and token fields only. They do not read auth files, prompts, or API keys. A missing counter stays `tokens=unknown`.

```
Grok usage.json modelUsage ----+
Cursor fixture or bound chat-dir -+--> worker measure_done_usage
OpenCode opencode.db (already) -+         |  tokens=unknown if missing/zero
                                          v
                                    DONE stamp (existing)
                                          v
                               job-cost-ledger.json (existing)
                                          |
                     +--------------------+--------------------+
                     v                                         v
          digest job_costs.by_model                    appliance /status
          (comparison rollup)                          inline SVG
                                                       home | empty | error

Cursor (FR #6782 / S2): keep BOB_CURSOR_USAGE_PATH or run/cursor-usage.json;
also live-read the seat chat directory the worker already binds when that
directory has non-zero token fields. Missing or zero fields stamp
tokens=unknown. No Cursor dashboard client and no new secret.

Login entry: https://bob.ntsa.uk/jeeves on the existing bob.ntsa.uk front.
Public GET of that page returns login HTML. Settings and status still
require the existing session cookie. /bob/v1/* is unchanged.
```

LOCKED

## Screens

HTML mocks in `bob/docs/mocks/cli-token-compare/`. No PNGs. This folder is separate from `jeeves/docs/mocks/home.html` and from `bob/docs/mocks/digest-fuel/`.

| id | file | state |
|----|------|-------|
| M1 | bob/docs/mocks/cli-token-compare/home.html | two model series, unknown count not drawn as zero |
| M2 | bob/docs/mocks/cli-token-compare/empty.html | no measured rows |
| M3 | bob/docs/mocks/cli-token-compare/error.html | ledger unreadable, no invented series |

Login mocks are in `bob/docs/mocks/jeeves-login/`. The image is the existing `jeeves/assets/jeeves-butler.ico`. No new drawing.

| id | file | state |
|----|------|-------|
| M4 | bob/docs/mocks/jeeves-login/home.html | login form and butler graphic |
| M5 | bob/docs/mocks/jeeves-login/empty.html | blank form, no error |
| M6 | bob/docs/mocks/jeeves-login/error.html | sign-in failed, password not shown |

## Already on origin/main

- OpenCode reads `opencode.db` per job directory (FR #6420) and stamps DONE (FR #6387). Per-job delta is FR #6435.
- Grok `read_grok_usage` prefers a single counted `modelUsage` entry over `primaryModelId` / session totals (FR #6781). Multi-entry `modelUsage` stays `tokens=unknown`.
- Cursor (FR #6782 / PR #6811): keeps `BOB_CURSOR_USAGE_PATH` or `run/cursor-usage.json`, and live-reads the bound seat chat directory when it has non-zero token fields. Missing or zero fields stamp `tokens=unknown`. No Cursor dashboard client.
- Digest `job_costs` includes `by_model` + `unknown_jobs` (FR #6783) alongside the last 20 PRs.
- Appliance `/status` lists version, uptime, queue, seats, and fuel names, plus the FR #6784 / S4 by-model token graph (home / empty / error; `unknown_jobs` as text).
- `jeeves/VISION.md` still says chair companions are not a website. Shape stays service.
- Open appliance pack #6751 and siblings paints pool remaining percent. FR #6759 drops token fields. That pack is not this comparison.
- Public home is `jeeves/www/irc-ntsa/index.html` on bob.ntsa.uk. FR #6818 / PR #6837 added `href="/jeeves"`.
- Login HTML is `_render_login_html` in `common/scripts/jeeves_settings_http.py`. FR #6816 / PR #6836 embeds the existing `jeeves/assets/jeeves-butler.ico` on that page (no new drawing).
- #6757 (PR #6791) added an internal `https://jeeves.ntsa.uk/` front door and left the non-RFC1918 reject in place. FR #6821 / PR #6842 set the appliance operator URL to `https://bob.ntsa.uk/jeeves`. Do not extend the old hostname.

## Out of scope

- Reworking the OpenCode sqlite reader.
- Dollar cost, pricing tables, or `costUsdTicks`.
- Cursor cloud usage export.
- Pool-percent pages (#6759, #6760, #6761, #6762).
- A new DNS name, a new butler drawing, and webhook route changes.
- Reopening #6757. That front door already merged.
- MSI rebuild, service restart, UAT stamp, IRC.

## UNKNOWN

- Whether any current Cursor CLI build writes non-zero token counts on disk. S2 accepts either outcome. A cloud export is a later request only if the owner names that source.
- Several `modelUsage` entries in one Grok session. S1 is the single-entry case: the stamp model is that entry, not a different `primaryModelId`. More than one counted entry is not this request.

## LOCKED

- Objective, Success S1-S5, Shape service, Stack, Architecture.
- Unknown counts stay unknown. Never stamp a fabricated zero.
- Comparison rollup key: `job_costs.by_model`.
- Graphs are inline SVG on the existing appliance status page, same auth as `/status`.
- Login entry is https://bob.ntsa.uk/jeeves. Public GET returns the login HTML. Settings and status still require the existing session cookie.

## Issues

Refs, not a closing keyword. Each open issue stays open for implementation. #6798 was the login bundle and is closed. Implement the six slices below.

| id | issue | mirror |
|----|-------|--------|
| S1 | #6781 | bob/docs/fr/cli-token-compare/FR-001-grok-model-usage.md |
| S2 | #6782 | bob/docs/fr/cli-token-compare/FR-002-cursor-token-source.md |
| S3 | #6783 | bob/docs/fr/cli-token-compare/FR-003-ledger-by-model.md |
| S4 | #6784 | bob/docs/fr/cli-token-compare/FR-004-appliance-token-graph.md |
| docs | #6785 | bob/docs/fr/cli-token-compare/FR-005-vision-hybrid-note.md |
| S5 route | #6815 | bob/docs/fr/cli-token-compare/FR-007-jeeves-get-login.md |
| S5 graphic | #6816 | bob/docs/fr/cli-token-compare/FR-008-butler-graphic.md |
| S5 link | #6818 | bob/docs/fr/cli-token-compare/FR-009-home-link.md |
| S5 sign-in | #6819 | bob/docs/fr/cli-token-compare/FR-010-session-login.md |
| S5 cookie | #6820 | bob/docs/fr/cli-token-compare/FR-011-session-cookie.md |
| S5 doc | #6821 | bob/docs/fr/cli-token-compare/FR-012-appliance-doc.md |
