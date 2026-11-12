# FR-002 Cursor CLI token stamp

GitHub: #6782. Stays open. Docs park Refs this issue.

## Goal

A Cursor CLI job stamps measured tokens when a non-zero local or fixture source exists for that chat, and stamps `tokens=unknown` when the source is missing or its token fields are absent or zero.

## Deliverables

- Keep the existing fixture path (`BOB_CURSOR_USAGE_PATH` or `run/cursor-usage.json`).
- Add a live read only if the seat chat directory the worker already binds contains non-zero token fields.
- If that directory has no token fields, or they are zero, the stamp stays `tokens=unknown`.
- No Cursor dashboard client and no new secret.

## Testable

`pytest`: a counts fixture stamps `tokens_in`, `tokens_out`, `tokens_cached`, and `model=`. A missing file and a zero-token store stamp `tokens=unknown` and do not emit `tokens_in=0`.

## Out of scope

Grok `modelUsage`, the by-model graph, and any cloud usage export.
