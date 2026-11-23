# BOB-35 Agents > Jeeves no-token gate

When `run/jeeves-fuel.json` or `BOB_JEEVES_FUEL_FILE` has `remaining_pct` of 0 or less, Agents > Jeeves shows "No tokens on this box. Jeeves will quit." and does not start.

The tray log line is `dialog-quit` with reason `no-tokens`. A missing fuel file does not block the start.
