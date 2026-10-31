# Airc Priority Client (allowlist + PRIORITY connect/status)

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

Required per instance: id, url (must be https://), company, user, credentialTarget (Windows CredMan generic target). Optional: sqlServer, systemDb, prepDir (for later prepare gates).

Loader rules (airc/scripts/airc_priority.py):

- Prefer live priority-instances.json; else example for docs/tests; override with env AIRC_PRIORITY_ALLOWLIST.
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

Reply framing matches FR #75:

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
