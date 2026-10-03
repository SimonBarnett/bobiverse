<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-git-webhook-jeeves-announce-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: git webhook → Jeeves announce (park-only)

1. Read this FR. Do not implement until Simon says go.
2. When dispatched: extend `bobcallback` (or sibling path) for git
   payloads; Jeeves announces; keep `/bob/v1/report` digest path.
3. Tests without live GitHub. No secrets. No UAT.
