# Airc Priority worker (in-service)

FR #5283 / FR #5905. This folder is the **service-owned** Priority Web SDK worker layout.

- Path: `<ai root>\airc\airc\priority-worker\` after pack (next to `airc.exe`)
- Invoke only from the Airc Priority module (`AIRC_PRIORITY_OWNED=1` or `--from-airc`)
- No `PriorityClient.exe` and no agent `drop\` one-off clients

## Node SDK (FR #5905 / #5913)

Pack stages:

- `sdk/run-repprep-via-exec.mjs` --- REPPREPDIRECT2 walk used by `PRIORITY prepare`
- `node_modules/priority-web-sdk` (+ transitive deps) via **always** `npm ci --omit=dev`
  at pack time (FR #5913: never skip when a stale `node_modules` is already present)

Resolver order (see `airc_console._priority_sdk_repprep`): `priority-worker/sdk/run-repprep-via-exec.mjs`,
then `priority-worker/run-repprep-via-exec.mjs`, then `AIRC_PRIORITY_REPPREP_MJS`. No `drop\` path.

### Node runtime

- Default: `node` on PATH, or `AIRC_PRIORITY_NODE` / `NODE_EXE` absolute path.
- When node is missing: prepare returns `ok=false reason=node_missing` (not a hang).
- Password: `PRIORITY_SDK_PASSWORD` env into the child only; never argv / IRC / logs.

### Local npm

```text
cd airc/priority-worker
npm ci --omit=dev
```

`package-lock.json` is committed; `node_modules/` is produced at pack (or locally for live tests).
