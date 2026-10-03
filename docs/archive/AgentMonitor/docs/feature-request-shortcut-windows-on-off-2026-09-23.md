<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-shortcut-windows-on-off-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: shortcut on/off shows both terminals or neither (issue #18)

https://github.com/SimonBarnett/AgentMonitor/issues/18

## LOCKED

Shortcut parameter, passed by the `.cmd` files:

- **`on`** (default) — show both terminals: the watcher console and the agent TUI. IRC `irc-in` / `forward` lines print in the watcher console.
- **`off`** — show neither. The log file still receives lines.
- One-shot `agent -p` forwards stay hidden in both modes.

`new` and `on`/`off` may be in either order. One-click `.cmd` files pass `on`. Change that `on` to `off` to hide both.

Script parameter: `-Windows on|off`, default `on`.

- `on` does not replace the current console with a hidden worker. Agent `Start-Process` uses `WindowStyle Normal`.
- `off` starts the worker hidden and the agent TUI hidden.
- `-NoExit` on the `on` launcher so a startup error stays on screen.

No UAT.

## Acceptance

| ID | Gate |
|----|------|
| A1 | Default and explicit `on` leave the watcher console visible and open the agent TUI visible. |
| A2 | `off` shows neither window. |
| A3 | One-click `.cmd` files pass `on`. README and `docs/operator-playbook.md` describe `on`/`off`. |
| A4 | No UAT stamp. |
