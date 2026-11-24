# FR #8732 / BOB-30 evidence (+ FR #9586)

Workers > Open Code launch uses Weights rows from live GET `/bob/v1/models`.

- SoT: GET `/bob/v1/models` via `WeightsLaunchField` / `Get-BobTrayWeightsLaunchField`.
- Fixture/offline fallback only: `BOB_MODELS_CATALOG` or `home/models-catalog.json`.
- Paid slot reads agent `Opencode`; free slot reads `Opencode-Free`.
- Compiled log: event `workers-opencode` action `webhook model` with `source=models-webhook`.
- PowerShell log: `Workers Open Code: webhook model … context=… effort=… agent … source=models-webhook`.
- A non-empty webhook model is `BOB_OPENCODE_MODEL` (+ effort/context SessionEnv). Empty model falls back to slot default.

Fixture `bob/tests/fixtures/models-catalog-opencode.json` returns `opencode-go/deepseek-v4-pro` and `opencode/deepseek-v4.1-flash-free` (the Grok row is ignored).

`python -m pytest -q bob/tests/test_fr8732_opencode_webhook_model.py bob/tests/test_fr9586_weights_launch_env.py`
