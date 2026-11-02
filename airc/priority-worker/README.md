# Airc Priority worker (in-service)

FR #5283 / FR #5905 / FR #5948 / FR #5960. This folder is the **service-owned** Priority Web SDK worker layout. Priority is optional: hosts without a live allowlist never load this worker at startup; PRIORITY verbs refuse with `priority_not_installed`.

- Path: `<ai root>\airc\airc\priority-worker\` after pack (next to `airc.exe`)
- Invoke only from the Airc Priority module (`AIRC_PRIORITY_OWNED=1` or `--from-airc`)
- No `PriorityClient.exe` and no agent `drop\` one-off clients

## Node SDK (FR #5905 / #5913 / #5946 / #5948)

Pack stages:

- `sdk/run-repprep-via-exec.mjs` --- REPPREPDIRECT2 walk used by `PRIORITY prepare` (report/procedure)
- `sdk/run-formprep-via-eform.mjs` --- FORMPREPDRCT2 walk used by `PRIORITY prepare form` (FR #5946)
- `sdk/run-formwalk-readonly.mjs` --- read-only formStart / startSubForm / getRows for `PRIORITY formStart` / `subform` / `getRows` (FR #5948)
- `node_modules/priority-web-sdk` (+ transitive deps) via **always** `npm ci --omit=dev`
  at pack time (FR #5913: never skip when a stale `node_modules` is already present)

Resolver order (see `airc_console._priority_sdk_repprep`): typed form uses
`sdk/run-formprep-via-eform.mjs` (then `AIRC_PRIORITY_FORMPREP_MJS`); report/procedure use
`sdk/run-repprep-via-exec.mjs` (then `AIRC_PRIORITY_REPPREP_MJS`). No `drop\` path.

Form-walk resolver (see `airc_console._priority_sdk_formwalk`): `priority-worker/sdk/run-formwalk-readonly.mjs`,
then `priority-worker/run-formwalk-readonly.mjs`, then `AIRC_PRIORITY_FORMWALK_MJS`. Default production path is live SDK;
fixture (`fixtures/form_walk.json`) only when console `priority_fixture` / env `AIRC_PRIORITY_WALK_FIXTURE` / kv `fixture|selftest` is set.

### Node runtime

- Default: `node` on PATH, or `AIRC_PRIORITY_NODE` / `NODE_EXE` absolute path.
- When node is missing: prepare / form-walk returns `ok=false reason=node_missing` (not a hang).
- Password: `PRIORITY_SDK_PASSWORD` env into the child only; never argv / IRC / logs.
- Walk (FR #5916 / #5927): bind one preferred name field (ENAME / Entity Name / NAME);
  if `--name` is set and no field binds, fail with `name_field_missing` (do not submit empty EditFields).
  Message steps prefer `messagetype` over `/error/i` on the text.
- Form walk (FR #5948): read-only only (no activateStart / FORMPREP). Expected errors
  (`form-not-found`, `no-access`, `subform-not-found`, …) reply on IRC and do not intake;
  genuine crashes (`sdk-fault` / uncaught) still intake.
- FR #5994: prepare SDK failures return a short `sdk_reason` (`stage:type message`) on the
  IRC reply. Formprep dumps go under `AIRC_HOME|AIRC_INSTALL_ROOT|OS tmp`/tmp/airc-formprep/sdk-run
  (never fixed `C:\Priority\tmp`). `--url` / `--user` / `--company` are required (no customer defaults).

### Local npm

```text
cd airc/priority-worker
npm ci --omit=dev
```

`package-lock.json` is committed; `node_modules/` is produced at pack (or locally for live tests).
