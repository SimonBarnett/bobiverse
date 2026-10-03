<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-mrb-merge-recycle-machines-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: #168 recycle after merge

1. Read issue #168 + FR doc. Implement skill/README text only unless tests need a string assert.
2. Sister mark on `agentic_build` `bob-hostile-mrb` if that repo owns merge duty (separate PR if needed).
3. Open PR linking #168. Do not push main. Do not live-recycle. No UAT.

## Checks

- `rg` recycle + ionos in the named skills.
- pytest or Test-Pack fails if the duty line is deleted.
