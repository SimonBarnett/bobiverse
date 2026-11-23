# FR #9250: Bob ear reports CLI model lists

## Problem
Chair `POST /bob/v1/models/refresh` ran `grok`/`agent`/`opencode models` on walrus. Those CLIs are not installed on the domain controller; refresh returned `not_installed` and `GET /bob/v1/models` showed empty `clis`.

## Fix
- **Ear** (`models_ear_report` + `irc_agent._maybe_publish_models_cli`): collect local listings at startup, hourly, and when refresh-wanted is stamped; POST `/bob/v1/models/report` (no tokens).
- **Chair**: merge per-machine reporters into `clis` with `machines` + `refreshed_at`; TTL age-out (`BOB_MODELS_REPORTER_TTL_S`, default 2h).
- **Refresh**: stamps wanted + returns `ok` / `stale` / `no_reporter`; never spawns CLIs.
- Hand-loaded `models-valid-combos.json` remains a valid override/fallback.

## Non-goals
No VERSION bump. No chair tokens. No worker involvement (Si: ear only).
