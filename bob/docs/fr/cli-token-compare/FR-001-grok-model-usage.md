# FR-001 Grok modelUsage on the DONE stamp

GitHub: #6781. Stays open. Docs park Refs this issue.

## Goal

A Grok CLI job whose `usage.json` has one `modelUsage` entry stamps that entry's model and token counts on DONE, and the ledger row matches.

## Deliverables

- `done_usage.read_grok_usage` (or a sibling used by the worker) reads `modelUsage`.
- One counted entry wins over a different `primaryModelId`.
- Worker `measure_done_usage` for kind `grok` uses that result.
- Fixture: input 100, output 20, cached 5.

## Testable

`pytest` covers the fixture. The stamp contains `tokens_in=100`, `tokens_out=20`, `tokens_cached=5`, and `model=` equal to that `modelUsage` key (provider prefix `xai/` is fine when the key has no slash). A missing file still stamps `tokens=unknown`.

## Out of scope

Cursor, the status graph, dollar cost, and more than one counted `modelUsage` entry. That multi-entry case stays UNKNOWN.
