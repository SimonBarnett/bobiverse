# FR #6864 / #6891 — process-local skill catalog bound

## Result (corrected by FR #6891)

S7 is measured with **`grok inspect --json`** (or a running agent prompt), not by
concatenating `worker_prompt` with a fixed sentence.

**Lever that works:** seat-local `GROK_HOME` (no credential copy; `GROK_AUTH_PATH`
is the one machine `auth.json` — FR #7183; empty
`skills.paths`; restore `bundled_skill_dirs`) **plus** a **bound agent cwd** under
the seat `run_dir` (outside the trusted install tree) that contains only
`skill-dag-core` under `.grok/skills`. MCP config on that cwd uses absolute
`--root` paths into the real install skill trees. User `~/.grok/config.toml` is
never opened for `[skills]`. `GROK_CONFIG` is not set for skills/MCP.

Vision LOCKED: Grok **bundled** platform skills may remain on the harness.

## Levers measured and rejected

| Lever | Why not / result |
|---|---|
| User `[skills]` in `~/.grok/config.toml` | Forbidden (edits Plan-seat / human Grok). |
| `GROK_CONFIG` overlay for `[skills]` or `[mcp_servers]` | Allowlist drops those tables. |
| `BOB_SKILL_DAG_BOUND` alone | Harness does not read it. |
| Project `.grok/config.toml` `disabled` / `ignore` | Does not suppress project skill discovery. |
| Seat `GROK_HOME` with cwd under trusted `C:\ai\bob` | Drops user/configToml only; still loads every install `.grok/skills`. |
| `--add-dir` to the install from a bound cwd | Harness refuses: session works only in its cwd. |

## Tests

- `bob/tests/test_fr6864_skill_dag_prompt_bound.py`
  - unit: bound cwd / seat `GROK_HOME` / launch wiring
  - S7: `grok inspect` on bound cwd with a 100-node fixture outside `.grok/skills`
