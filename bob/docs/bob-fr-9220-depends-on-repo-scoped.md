# FR #9220: Depends-on offer gate is repo-scoped

## Problem
`row_fr_depends_blocked_reason` (FR #8754) indexed open FRs by bare `#N`. A Depends-on `#9` on `a/home#10` could false-skip when unrelated `b/other#9` was open.

## Fix
- `_open_fr_bob_and_id_index` keys open FRs as `(repo_key, #id)`
- Relative `#N` resolves against the FR row repo
- Qualified `owner/repo#N` is kept by `parse_depends_on_tokens` (no bare `#N` twin from the same span)
- BOB-* vision backlog matches stay repo-local for this gate

## Non-goals
`jeeves/tools/monitor/depends_on.py` unchanged (#9193 / #8848 / #8806).

## Tests
`jeeves/tests/test_fr9220_depends_on_repo_scoped.py` plus 8754 / 8807 / 8806 regression.