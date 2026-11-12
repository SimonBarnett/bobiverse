# FR #6864 — process-local skill catalog bound

## Result

The lever that works: **do not interpolate the skill-dag index into `worker_prompt` / `--rules`**. The captured prompt names only `skill-dag-core`. The agent child env sets `BOB_SKILL_DAG_BOUND=skill-dag-core`. `~/.grok/config.toml` is not opened.

## Levers not used

| Lever | Why not |
|---|---|
| User `[skills]` in `~/.grok/config.toml` | Forbidden (edits Plan-seat / human Grok). |
| `GROK_CONFIG` overlay for `[skills]` or `[mcp_servers]` | Allowlist drops those tables. |

S7: `bob/tests/test_fr6864_skill_dag_prompt_bound.py` — 100-node index, none of those ids appear in the captured prompt.
