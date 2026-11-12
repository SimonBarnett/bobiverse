# Vision: worker skill DAG MCP

Product: `bob/` in `SimonBarnett/bobiverse`. This pack is the new surface only.
Repo shape stays the bob product shape in `bob/VISION.md`.

## Objective

A worker seat can follow any harvest-updated skill the current job needs, and the text in its context is the core stub plus that job's dependency closure.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Index coverage | Every `SKILL.md` under the configured roots is one node | `pytest` rebuilds a fixture root and compares node count to file count | A fixture `SKILL.md` is missing from the index after rebuild |
| S2 | Closure | `resolve` on an FR job line returns the matched skill plus its `depends_on` ancestors | `pytest` fixture graph: FR skill depends on job-irc; UAT skill has no edge to that job | A declared dependency is missing, or a fixture skill with no edge is included |
| S3 | Cycle reject | A `depends_on` cycle fails the rebuild | `pytest` expects builder exit 1 and no index write | Builder exits 0 on a cycle |
| S4 | Byte budget | Resolve and get responses stay within the configured byte cap | `pytest` fat fixture; response length `<=` cap; over-cap ids listed as skipped | A body over the cap is returned |
| S5 | Prompt contract | Worker launch text tells the agent to resolve per job | `pytest` on `worker_prompt` and `rules_text` in `bob/scripts/bob_worker.py` | The launch text still says to read every skill in the folder |
| S6 | Config isolation | MCP config is written only under the worker cwd `.grok/config.toml` | `pytest` launch fixture; assert plan cwd and `~/.grok/config.toml` unchanged | Launch writes the user config or the plan folder config |
| S7 | Catalog bound | Worker process prompt lists only the core stub while the index has at least 100 nodes | Captured worker system prompt or `grok inspect` in the seat test | An unrelated fixture skill description is in that prompt |
| S8 | Freshness | A changed `SKILL.md` is visible on the next resolve | `pytest` touches description, resolve sees the new line | The next resolve still returns the old line |

LOCKED

S7's mechanism is UNKNOWN until a process-local lever is proven. Do not satisfy S7 by editing `~/.grok/config.toml` `[skills]`. That table is user-global.

## Shape

Primary: **service**

Hybrid note: reuse the bob product shape (service). The new surface is a local stdio MCP beside `bob-worker`. It is not a website and not a tray page.

LOCKED

## Stack

Default: Python stdio MCP started from the worker cwd. A Python script in the bobiverse tree builds the index. The MCP entry lives in `<ai root>\bob\worker\.grok\config.toml` under `[mcp_servers]`.

Why: `bob/scripts/bob_worker.py` is already Python. Project `.grok/config.toml` is the documented per-cwd place for MCP servers. Stdio stays on the box.

Why-not: an HTTP listener, `grok mcp add` into the user config, or a shell walk of the skill tree from the prompt.

LOCKED

## Architecture

```
harvest PR merged
  -> Sync copies SKILL.md into worker .grok/skills and ~/.grok/skills

bob-worker.exe (one window, always-new session)
  -> starts grok or cursor with cwd <ai root>\bob\worker
  -> worker .grok/config.toml registers skill-dag MCP (stdio)
  -> prompt: core stub only; on each FROM job line call resolve

skill-dag MCP (stdio, local)
  -> reads slim index (id, one-line description, depends_on, path, bytes)
  -> resolve(job line) scores descriptions, adds depends_on closure, enforces budget
  -> get_skill(id) returns one body; path must stay under configured roots
  -> status returns index time, node count, last error

roots (read):
  worker .grok/skills
  ~/.grok/skills
  optional: assigned job worktree .grok/skills after the path exists
```

Trust: path allowlist on get. No network listener. No secrets in the index. Harvest remains the only writer of skill text.

LOCKED

## Screens

No product UI. Validator requires three HTML files when Shape is LOCKED. They document resolve states for a later visual check. Tray mocks stay in `bob/mocks/`.

| id | file | state |
|----|------|-------|
| M1 | bob/docs/mocks/skill-dag/home.html | resolve hit: job line, returned ids, edges, byte use |
| M2 | bob/docs/mocks/skill-dag/empty.html | resolve matched nothing; core stub only |
| M3 | bob/docs/mocks/skill-dag/error.html | cycle rejected, or budget skipped the rest |

## LOCKED

- One node per `SKILL.md`. Edge field is frontmatter `depends_on`. Missing field means no dependencies.
- The index stores no skill body.
- MCP tools are `resolve`, `get_skill`, and `status`. No list-all tool.
- Core stub in the launch prompt: IRC FROM handling, ACK/DONE outbox path, and the rule to call `resolve` before any other skill.
- Resolver runs per job line.
- Plan seats, Jeeves monitor, and Jeeves maintenance are out of this pack.
- Grok bundled platform skills stay on the harness.
- Gap baseline: GitHub `main` `a5197856` `bob/scripts/bob_worker.py` `worker_prompt` (line 1731) says `FIRST read the skills in {worker_dir}\.grok\skills`. `rules_text` (line 1925) says `Read the skills in {folder}\.grok\skills` before doing anything.
- Implementation issues stay open: #6860 index, #6861 edges, #6862 stdio MCP, #6863 launch contract, #6864 catalog bound, #6865 Cursor wire, #6866 job-worktree root. The docs park Refs them.

## UNKNOWN

- Cursor MCP config for the seat is project `.cursor/mcp.json` (same as the editor; CLI `--workspace` = seat cwd). There is no process-local Cursor skill catalog drop; do not rewrite `~/.cursor/skills`.

## KNOWN (FR #6891)

- S7 Grok lever: seat-local `GROK_HOME` (auth copy only; empty `skills.paths`; restore `bundled_skill_dirs`; never edit user `config.toml`) plus a bound agent cwd under the seat `run_dir` outside the trusted install tree, containing only `skill-dag-core` under `.grok/skills`. Measure with `grok inspect --json`. Bundled platform skills stay. `--add-dir` into the install is refused by the harness.
