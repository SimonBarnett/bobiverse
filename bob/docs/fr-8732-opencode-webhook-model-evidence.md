# FR #8732 / BOB-30 evidence

Workers > Open Code launch uses the models webhook rows.

- Catalog: `home/models-catalog.json`, or `BOB_MODELS_CATALOG`.
- Paid slot and the PowerShell Open Code click read agent `Opencode`.
- Free slot reads agent `Opencode-Free`.
- Compiled log: event `workers-opencode` action `webhook model` with `agent` and `path`.
- PowerShell log: `Workers Open Code: webhook model <model> agent Opencode path <catalog>` and the same line for `Opencode-Free`.
- A non-empty webhook model is `BOB_OPENCODE_MODEL`. An empty row still logs the path, then the existing slot default is used.

Fixture `bob/tests/fixtures/models-catalog-opencode.json` returns `opencode-go/deepseek-v4-pro` and `opencode/deepseek-v4.1-flash-free` (the Grok row is ignored).

`python -m pytest -q bob/tests/test_fr8732_opencode_webhook_model.py bob/tests/test_fr8735_workers_opencode_cli.py`
