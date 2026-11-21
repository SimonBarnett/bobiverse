# Build-and-test plan: BOB-01 models webhook GET

## Goal
Implement `GET /bob/v1/models` on the bob.ntsa.uk / BobCallback surface so it returns fleet agent rows JSON (HTTP 200), ending the current 404.

## Non-goals
PUT/PATCH, Weights UI, tray menu, seed matrix (later BOB-02..04).

## Phase 0
1. Find existing webhook routing for `/bob/v1/report`, `/bob/v1/intake`, etc.
2. Add `/bob/v1/models` GET handler returning a stable JSON shape with agent rows (Plan, Priority, Jeeves, Grok, Cursor, Opencode, Opencode-Free) and placeholder model/context/effort fields.
3. Document the shape in code comments or adjacent docs page stub if trivial.

## Tests
- `curl` / Invoke-WebRequest against local or documented endpoint returns 200 JSON.
- Not 404.

## Done
Open a PR against bobiverse main. Do not merge. Paste test evidence in the PR.
