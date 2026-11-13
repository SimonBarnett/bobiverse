# Functional spec: worker skill DAG MCP

LOCKED items are copied from `bob/docs/vision-worker-skill-dag-mcp-2026-11-12.md`. This file is the build surface. It is not a skill book.

Open slices: #6860 index, #6861 edges, #6862 stdio MCP, #6863 launch, #6864 catalog bound, #6865 Cursor wire, #6866 job-worktree root.

## Purpose

Harvest keeps writing `SKILL.md` files. The worker must be able to use that library. Context for a job is the core stub plus the skills that job depends on.

## Actors

- `bob-worker.exe` starts one always-new agent in `<ai root>\bob\worker`.
- The skill-dag MCP is a local stdio process. The worker cwd `.grok/config.toml` registers it.
- Harvest and Sync remain the writers of `SKILL.md`. The MCP only reads.

## Index

- Input: configured roots. Default roots are the worker `.grok/skills` directory, the bob pack, common harvest pack, and `~/.grok/skills` (FR #6899).
- One node per unique skill id. Id is frontmatter `name`, else the directory name.
- Harvest copies of the same id across those roots keep the first configured root (worker, then bob, then common, then user). They are not `status.last_error` (FR #7076). Same-root extra paths remain collisions (FR #6921).
- Edges: frontmatter `depends_on`, a list of skill ids. Absent or empty means no edges.
- Record: id, one-line description, `depends_on`, path, byte size. No body text.
- Rebuild when a source `SKILL.md` mtime is newer than the index (S8).
- A cycle exits 1 and does not replace a good index (S3).
- A missing file under a root after rebuild fails S1.

## Resolve

- Input is one job line (the IRC text the worker already has).
- Score nodes by description and by skill-id token overlap (FR #7079). Take the matches, then add every `depends_on` ancestor (S2).
- Always include the core ids named by the launch stub when they exist in the index.
- Stop at the byte budget. Return skipped ids instead of their bodies (S4).
- A second call with a different job line returns that job's closure. It does not keep the previous job's extra skills.

## get_skill

- Input is one id.
- Return that file's body only if its path is under a configured root.
- Refuse paths outside the roots.
- Refuse a body that would exceed the remaining budget. Report it as skipped (S4).

## status

- Return index time, node count, and the last rebuild error (empty when the last rebuild succeeded).
- This is the empty and error surface the mocks show. It is not a website.

## Launch

- `worker_prompt` and agent `rules_text` tell the seat to call `resolve` on each job, then `get_skill` for the returned ids (S5).
- They do not tell the seat to read every skill in the folder.
- The MCP block is written only to the worker cwd `.grok/config.toml` (S6).
- The launch does not write `~/.grok/config.toml` and does not write the plan folder config.

## Catalog bound (S7)

The worker prompt must list only the core stub while the index holds at least 100 nodes. The mechanism is UNKNOWN. A spike measures process-local options. It must not edit the user `[skills]` table. If no lever exists, S7 stays failed and the spike reports that.

## Job worktree root

Optional later slice. After the assigned worktree path exists, `resolve` may also read that tree's `.grok/skills`. It does not scan other repos.

## Tests (must exist before the behaviour is called done)

| Success | Test idea |
|---------|-----------|
| S1 | Fixture root with N skills; index node count is N |
| S2 | FR node depends on job-irc; UAT node is absent from an FR resolve |
| S3 | A cycle exits 1; previous index file unchanged |
| S4 | Fat body is skipped; response length stays `<=` cap |
| S5 | `worker_prompt` and `rules_text` contain the resolve instruction and do not contain the read-all-skills sentence |
| S6 | Launch fixture leaves plan cwd and `~/.grok/config.toml` byte-identical |
| S7 | Seat prompt fixture or `grok inspect` with 100 indexed nodes shows only the core stub |
| S8 | Rewrite a description; next resolve returns the new line |

## Out of scope

Plan seats. Monitor. Maintenance. HTTP MCP. User-global skill config edits. Deleting skills. Copying lesson text into the index. A tray page or a website. `gh repo create`.
