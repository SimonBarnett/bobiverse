# jeeves/checks - self-test / heal check plugins (FR #2522)

`jeeves.exe --self-test` runs the builtin checks plus every `check_<name>.py` here.

## Add a check

1. Create `jeeves/checks/check_<name>.py`:

   ```python
   CHECK_NAME = "<name>"          # lowercase, must not shadow a builtin (imports/locks/http/queue/health/offer)
   INCLUDE_IN_DEFAULT = True      # False = only via --check <name>

   def run(home, chair_home):
       # deterministic, token-free, no IRC mutation, no secrets
       return {"ok": True}, [], []   # (detail, findings, errors)
   ```

2. Add pytest under `jeeves/tests/` that drives the check through `jeeves_main.run_self_test` (see `test_fr2522_plugin_checks.py`).
3. Open a PR and get MRB. `Build-Jeeves.ps1` bundles this folder into the next jeeves.exe.

Never live-edit the running jeeves.exe or its install to add a check. `JEEVES_CHECKS_DIR` points the loader at another folder (tests only).
