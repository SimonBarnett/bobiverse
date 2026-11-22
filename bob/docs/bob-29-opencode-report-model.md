# BOB-29 Workers > Open Code reports the chosen model

FR #8734. S1: the session log prints the model id that the seat launches.

- `seat-<nick>.log`: `opencode model=<id>` at agent start (child `BOB_OPENCODE_MODEL` stamp).
- Same log, via the wrapper stdout tee: `opencode-run model=<id> job=<job>` immediately before `Start-Process`. `-m` is built after the pause-return model update, so the line and the launch agree.
- Tray Workers > OpenCode: `workers-opencode model=<id>` in the tray log, and the lifecycle record `action=model`, before the seat starts. Unset `BOB_OPENCODE_MODEL` uses `opencode/deepseek-v4.1-flash-free`.
- How to find the line from tray Status: `bob/docs/bob-worker.md` section "Finding the chosen OpenCode model".
