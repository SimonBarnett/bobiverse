# BOB-13 / FR #8714 evidence: Weights ↔ models webhook round-trip

**Date:** 2026-11-22  
**Repo:** SimonBarnett/bobiverse  
**Branch:** `fr-8714`  
**Acceptance:** S1 — Weights load/save via `/bob/v1/models`; Save then reload matches GET; no local-only store.

## Prerequisites

- BOB-02 (`GET`/`PUT /bob/v1/models`) merged — `common/scripts/models_catalog.py` + `bobcallback.py`.
- BOB-12 Weights grid merged — `bob/tray/dialogs/WeightsForm.cs` columns Agent/CLI/Model/Context/Effort.
- Owner UNHOLD on #8714 (2026-11-22): pinned prerequisites closed.

## Contract used (BOB-02)

| Item | Value |
|------|--------|
| GET | `/bob/v1/models` → 200 `{"agents":[{agent,cli,model,context,effort},…]}` |
| PUT | full-matrix replace; peer-IP allowlist; 204 when changed, 200 when unchanged; 400/413/503 |
| Auth header | none (server peer gate) |

## Implementation

| Piece | Path |
|-------|------|
| Client | `bob/tray/dialogs/BobModelsClient.cs` |
| Form | `bob/tray/dialogs/WeightsForm.cs` (Save + async GET/PUT) |
| Headless | `bob-tray.exe --weights-get <out.json>` / `--weights-save <in.json>` |
| Build | `Build-BobDialogs.ps1` includes `BobModelsClient.cs` |
| Test | `bob/tests/test_bob13_weights_webhook_roundtrip.py` |

### URL resolution order

1. `BOB_MODELS_URL`
2. `modelsUrl` in `bobiverse.json` / `bobiverse.local.json`
3. Origin of digest/report URL + `/bob/v1/models`

### Lifecycle events (`%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log`)

- `weights_get` — host, status, rows, bodyHash, ok
- `weights_save` — method, status, bodyHash, ok
- `weights_reload_match` — match true|false  

No secrets or full bodies are logged.

## Offline proof (loopback)

```text
python -m pytest bob/tests/test_bob13_weights_webhook_roundtrip.py -q
```

Covers:

1. Source pin: Weights form has no `tray-models.json` / `worker_start_model` writes.
2. Separate processes: `--weights-save` then `--weights-get` against an in-memory BOB-02 loopback; Plan model round-trips.
3. Failure: 503 GET → non-zero exit; no `tray-models.json` under isolated `%LOCALAPPDATA%`.
4. Fake `BOB_MODELS_TOKEN` never appears in stdout/stderr/result JSON.

## Live notes

- Install: slab tray hotpatch (`tools` + `src` + `assets`) per `bob-tray-dialogs.md`; restart tray host only.
- Endpoint host for a live check is whatever `BOB_MODELS_URL` / config resolves (do not invent SaaS hosts in this evidence).
- Matching curl: `curl -sS <models-url>` after a Weights Save should equal the reloaded grid (same agent/cli/model/context/effort).

## Cross-links

- Pack: `bob/docs/feature-request-weights-bind-webhook-2026-11-21.md`
- Index: `bob/docs/feature-request-systray-agents-workers-index-2026-11-21.md`
- Depends: BOB-02 #8708, BOB-12 #8715
- Dialogs: `bob/docs/bob-tray-dialogs.md` (Weights data source)
