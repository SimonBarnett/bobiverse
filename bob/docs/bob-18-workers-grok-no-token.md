# BOB-18 Workers > Grok no-token dialog

FR #8726. Workers > Grok reads `BOB_GROK_FUEL_FILE` or `run/grok-fuel.json`. When `remaining_pct` is 0 or less, the tray shows "No tokens on this box. Grok will quit." and does not start the seat. A missing file does not block the start. Other worker rows are unchanged.
