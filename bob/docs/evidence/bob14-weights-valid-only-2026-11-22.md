# BOB-14 / FR #8716 evidence — Weights valid-only dropdowns

**Date:** 2026-11-22  
**PR:** (this branch)  
**S1:** Dropdowns only offer valid combos — Invalid options absent for that CLI.

## What changed

1. `GET /bob/v1/models` includes `clis` from the BOB-03/04 allow-list (`models-valid-combos.json`) when available.
2. `BobModelsClient` parses `clis` and exposes `ModelsForCli` / `ContextsFor` / `EffortsFor`.
3. `WeightsForm` fills Model/Context/Effort from that catalog per row CLI. Hardcoded `256`/`512`/`med` are gone. Values not in the allow-list are cleared on bind.
4. Headless `--dump-weights-valid <file>` writes the allow-list TSV for acceptance.

## Tests

```
python -m pytest -q bob/tests/test_fr8716_weights_valid_only.py bob/tests/test_fr8715_weights_grid_ui.py common/tests/test_fr8707_models_webhook_get.py common/tests/test_bob03_models_catalog.py
```

## Fail-when avoided

Invalid options such as mock shorthand `med` or truncated contexts `256`/`512` are not selectable when the webhook catalog is present.
