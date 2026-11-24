# FR #8725 / BOB-17 evidence (+ FR #9586)

Workers > Grok launch uses the Grok row from live GET `/bob/v1/models` (Weights SoT) and logs model/context/effort.

- SoT: GET `/bob/v1/models` via `BobModelsClient.ResolveAgentLaunchRow` / `Get-BobModelsWebhookAgentRow`.
- Fixture/offline fallback only: `BOB_MODELS_CATALOG` or `<install>\home\models-catalog.json`.
- Row: `agents[]` where `agent` is `Grok`. Fields `model` / `context` / `effort` pass into child env (`BOB_GROK_MODEL`, `BOB_GROK_EFFORT`, `BOB_GROK_CONTEXT`).
- Compiled log: event `workers-grok` action `webhook model` with `source=models-webhook`.
- PowerShell log: `Workers Grok: webhook model <model> context=… effort=… source=models-webhook`.
- Empty model: MessageBox refuse (`weights-model-missing`).
- Fixture: `bob/tests/fixtures/models-catalog-grok.json` returns `grok-4`.

`python -m pytest -q bob/tests/test_fr8725_grok_webhook_model.py bob/tests/test_fr9586_weights_launch_env.py`
