# FR-001 Skill DAG index builder

GitHub: #6860. Stays open. Docs park Refs this issue.

## Goal

Build a slim skill index from `SKILL.md` files so later resolve calls do not read the library into the prompt.

## Deliverables

- A Python builder in the bobiverse tree.
- One node per `SKILL.md`: id, one-line description, `depends_on`, path, bytes. No body.
- Cycle: exit 1, previous index file left in place.
- Rebuild when a source mtime is newer than the index.

## Testable

- S1: fixture root node count equals `SKILL.md` count (`pytest`).
- S3: a cycle exits 1 and the previous index bytes are unchanged.
- S8: after a description edit, the next read of the index shows the new line.

## Out of scope

MCP process. Launch prompt. User grok config.
