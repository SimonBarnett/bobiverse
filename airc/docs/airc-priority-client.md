# Airc Priority Client (allowlist + PRIORITY connect/status)

**Priority is optional (FR #5960).** Airc installs, starts, and runs CMD/UPDATE/CRED/LEGION/EXTENSION/NETWORK/DCC with no Priority product, no live `priority-instances.json`, and no Priority SDK. PRIORITY verbs then return `reason=priority_not_installed` (no crash, no FR #5775 intake). Live `config/priority-instances.json` with at least one instance (or `AIRC_PRIORITY_ALLOWLIST`) opts Priority support in; empty `instances: []` is treated as absent (`priority_allowlist_empty`). Schema field errors (e.g. missing `credentialTarget`) stay distinct from `priority_not_installed`. The shipped `priority-instances.example.json` is docs/tests only.

Parent vision: [feature-request-airc-priority-client-2026-10-31.md](./feature-request-airc-priority-client-2026-10-31.md) (Success **S1** / **S2** / **S6**).

Issues: FR-A schema [#5275](https://github.com/SimonBarnett/bobiverse/issues/5275); FR-C verbs [#5284](https://github.com/SimonBarnett/bobiverse/issues/5284). FR-B live Web SDK packaging remains [#5283](https://github.com/SimonBarnett/bobiverse/issues/5283) (SelfTest uses a mock connector until then).

## Allowlist schema (FR-A)

Live file (not in git): <ai root>\airc\config\priority-instances.json

Shipped example (no secrets): airc/config/priority-instances.example.json

Root object:

```json
{
  "instances": [
    {
      "id": "example-dev",
      "url": "https://prioritydev.example.invalid",
      "company": "live1",
      "user": "api-user",
      "credentialTarget": "PriorityWeb/example-dev",
      "sqlServer": ".\\PRI",
      "systemDb": "system",
      "prepDir": "E:\\priority\\system\\prep"
    }
  ]
}
```

Required per instance: id, url (must be https://), company, user, credentialTarget (Windows CredMan generic target). Optional: sqlServer, systemDb, priorityRoot (Priority install root), prepDir. **`prepDir` is an optional override** for `PRIORITY prepare` (absolute `.prp` folder, e.g. `E:\priority\system\prep`). When unset, prepare derives `<priorityRoot>\system\prep`, then `tabula.ini` Priority Directory, then `PRIORITY_PREP_DIR` / `PRIORITY_ROOT` (FR #5943). Reply includes `prep_dir` + `prep_dir_source` (`override`|`derived`). If derivation fails (and no valid override), `reason=prep_dir_missing` with `prep_dir_tried` --- never a false `prp_unchanged` (FR #5932 / #5937).
 FR #5946 / #6003: `PRIORITY prepare form|report|procedure <ENAME>` selects the exact T$EXEC type (form uses `FORMPREPDRCT2`; report/procedure use `REPPREPDIRECT2`); untyped `prepare <ENAME>` remains procedure-only. Default form prepare uses Priority WINRUN (`WINACTIV -P FORMPREP <ENAME>`; no `priority-web-sdk` / API Licence). Unscoped FORMPREP is refused (`ename_missing`) so sibling pending forms are not prepared (FR #6017). WINRUN has no documented non-argv password (FR #6019): default refuses `winrun_password_argv`. Set the WINRUN argv-password opt-in environment flag only if process-list / 4688 command-line audit risk is accepted. EFORM/`formStart` is opt-in via `AIRC_PRIORITY_FORM_VIA_EFORM=1`; EXEC `procStart` FORMPREPDRCT2 is opt-in via `AIRC_PRIORITY_FORM_VIA_EXEC=1`. On SDK failure the reply keeps `reason=sdk_not_ok` and adds a short secret-free `sdk_reason` (`stage:type message`) so the caller does not need the runner dump (FR #5994).

Loader rules (airc/scripts/airc_priority.py):

- Live Priority only: `config/priority-instances.json`, `AIRC_PRIORITY_ALLOWLIST`, or an explicit override (FR #5960). The shipped `priority-instances.example.json` is documentation/tests only and never enables live PRIORITY verbs. Form walk uses the same live resolver (FR #5535).
- Fail closed when missing, empty instances, unknown id, non-https URL, or duplicate id.
- Reject any JSON key whose name contains pass or is secret / token / pwd (CredMan only).


## PRIORITY verbs (FR-C)

Authorized PRIVMSG to {machine}_console (same ops/+h auth as other console verbs):

```text
PRIVMSG marchhare_console :PRIORITY status
PRIVMSG marchhare_console :PRIORITY status example-dev
PRIVMSG marchhare_console :id=aabbccdd PRIORITY connect example-dev
```

- PRIORITY status - list allowlisted instance ids.
- PRIORITY status <id> - public identity fields (url/company/user/credentialTarget; never the password).
- PRIORITY connect <id> - CredMan fetch for credentialTarget, then connect. Until FR-B ships the Node Web SDK worker, SelfTest/unit path uses mock_connect (non-empty password required; password never echoed).
- PRIORITY wcf GetVersion|GeneralCompanies|ProcStart|ProcContinue|ProcEnd [instance-id] [k=v] (FR #6035 / #6041): SOAP 1.1 ``IWCFService`` to ``{url}/wcf/wcf/Service.svc`` (optional ``wcfUrl`` / ``wcfPath``). Every call sends ``wsse:Security mustUnderstand=1`` with ``wsu:Timestamp`` (Created/Expires UTC, 5 min) plus PasswordText UsernameToken. ``a:InvalidSecurity`` maps to ``wcf_security_rejected``. Shared client: ``direct`` (agent/SaaS) and ``relay`` (airc console on LAN). No WINRUN, no ``priority-web-sdk``, no OData. Live proof against a customer host stays [#6026](https://github.com/SimonBarnett/bobiverse/issues/6026).
- Bare `PRIORITY` (or an unknown sub-verb) is usage, not a shell command (FR #5533): `err id= seq=1 code=usage PRIORITY connect|status|prepare|formStart|subform|getRows|wcf` then `DONE id= exit=2`.
- Fixture walks return `form-not-found` with the requested form, or `subform-not-found` with the form and path (FR #5837). Unreadable or invalid fixtures return `fixture-miss`. These failures use the shared #5775 intake helper and end with `DONE id= exit=2`, without exposing Python exception types in the reply.

Reply framing matches FR #75. Each reply is one `out` line within **350 UTF-8 bytes** (same budget as shell `IRC_SAFE_PAYLOAD`) followed by `DONE` (FR #5616). Echoed instance tokens in unknown-instance errors are shortened with ASCII `...` so the reason stays visible. Oversized replies drop optional detail first (`prep_dir_tried`, `prep_dir`, `sdk.errors`, mtimes, walk `rows`, …) so a real `ok:true` prepare keeps `ok` / `reason` / `exec_id` / `prep_file` / `prep_dir_source` and exit `0` (FR #5993), and a real `ok:true` form walk keeps `ok` / `form` / `table` / `columns` / `count` (FR #6018). Full walk rows are written to `<AIRC_HOME>/jobs/<id>/walk.json`. Only an unshrinkable `ok:false` falls back to compact `{"ok":false,"action":...,"error":"reply-too-large","bytes":n}` with exit `1` (never character-slices JSON mid-document). Form walk selects the company table from the Priority dictionary (`EXEC.TNAME` / `COLUMNS.TNAME`), not by assuming table==form name.

```text
out id=<corr> seq=1 {"action":"connect","company":"live1","ok":true,...}
DONE id=<corr> exit=0
```

shell=off capability denies PRIORITY with DONE exit=126 (same gate family as free-form shell until a dedicated Priority capability lands).

### CredMan + receive-loop isolation (FR #5526)

- Default CredMan path is native `CredReadW` via `airc/scripts/airc_credman.py` (no PowerShell / Add-Type subprocess). A missing target returns `credman-missing` in milliseconds (exit 1). LEGION / EXTENSION reuse the same helper through `read_legion_credman`.
- Live service binds `priority_reply_send` so `PRIORITY connect` runs CredMan + connector on a worker thread; the IRC receive loop keeps serving other commands. Wire shape is unchanged (no accept line; exactly one `DONE id=`).

## CAST IRON secrets

- Never put Priority passwords on IRC, in logs, intake, harvest, or git.
- Never invent a web URL / company outside the allowlist.
- CredMan only for the web user password.

## MSI / client allow-list (FR-G / #5288)

Default **on** for both `AIRC_PROFILE=client` and fleet. Not a separate MSI Feature and not opt-in.
Client `Remove-BobiverseAircClientExtraPayload` keeps `airc\priority-worker\*`, `scripts\airc_priority.py`, and `scripts\airc_credman.py` so the in-service Priority module is not stripped.
