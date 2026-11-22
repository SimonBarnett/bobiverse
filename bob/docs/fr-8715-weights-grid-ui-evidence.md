# FR #8715 / BOB-12 evidence: Weights form grid UI

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8715
**Slice:** Weights form: grid UI (Success S1)

## S1

Weights form shows ordered columns `Agent`, `CLI`, `Model`, `Context`, `Effort` matching `bob/docs/mocks/systray-agents-workers/weights.html`.

## How measured

1. `WeightsForm` hosts a `DataGridView` with that header order (shared `ColumnHeaders` constant).
2. BOB-06 menu **Weights** opens the form modelessly (`ShowWeights`); second click activates the open instance.
3. `--dump-weights-columns <path>` writes the five headers and exits before UI.
4. Placeholder Agent/CLI rows from the mock; Effort uses `low`/`medium`/`high` (contract); Context `256`/`512`; Model empty until BOB-13/14.
5. Tests: `bob/tests/test_fr8715_weights_grid_ui.py`.

## Fail-when

Missing columns, wrong order, or Weights still showing the BOB-06 MessageBox stub.

## Test run (fr-8715 worktree)

```
python -m pytest -q bob/tests/test_fr8715_weights_grid_ui.py
# 2 passed
```
