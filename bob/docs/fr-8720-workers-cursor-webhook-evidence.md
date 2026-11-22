# FR #8720 / BOB-22 evidence

Workers > Cursor uses the Cursor row from the models webhook.

Dry-run log path: `%LOCALAPPDATA%\Bobiverse\worker\launch-dryrun.jsonl` (one JSON line from `bob-worker --dry-run` when the decision kind is cursor).

The line's `settings_source` is `webhook` and `cli_args` contains `--model` plus the Cursor row model. A tray `workerStartModels.cursor` value does not win. An env pin `BOB_CURSOR_MODEL` still wins (BOB-15).

Context stays `not-passed: unsupported` until a Cursor context flag is verified. Empty webhook effort is `not-passed: empty` (Cursor argv is model only).

Test: `common/tests/test_fr8720_cursor_webhook_dryrun.py`.
