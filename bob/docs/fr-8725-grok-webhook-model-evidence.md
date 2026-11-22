# FR #8725 / BOB-17 evidence

Workers > Grok launch uses the Grok row from the models webhook catalog and the dry-run log cites that model.

- Catalog: `<install>\home\models-catalog.json`, or `BOB_MODELS_CATALOG`.
- Row: `agents[]` where `agent` is `Grok`. Field `model` is the launch model (`BOB_GROK_MODEL` / `-Model`).
- Compiled log: event `workers-grok` action `webhook model`.
- PowerShell log: `Workers Grok: webhook model <model> path <catalog>`.
- Fixture: `bob/tests/fixtures/models-catalog-grok.json` returns `grok-4`, not the Cursor row.

`python -m pytest -q bob/tests/test_fr8725_grok_webhook_model.py`
