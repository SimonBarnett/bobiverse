# BOB-28 Workers > Open Code paid exhausted dialog + quit

When `run/opencode-fuel.json` (or `BOB_OPENCODE_FUEL_FILE` / `BOB_OPENCODE_FUEL_CACHE_FILE`) has both `free` and `go` (paid) at 0 or less, Workers > Open Code shows "OpenCode free and paid fuel are exhausted. Not starting an OpenCode seat." and does not start.

Null or missing free/go fields do not block the start (unknown is not exhausted). Headless check: `bob-tray.exe --root <root> --check-opencode-paid-exhausted <out.json> --no-engine` exits 2 when exhausted.

Compiled tray log: `workers-opencode` action `dialog-quit` reason `paid-exhausted`. PowerShell tray log: `Workers Open Code: paid exhausted dialog + quit`.
