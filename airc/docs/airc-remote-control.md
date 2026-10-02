# Airc remote control (protocol sketch)

See **[feature-request-airc-remote-control-2026-10-01.md](./feature-request-airc-remote-control-2026-10-01.md)** for LOCKED success metrics.

## Today (FR #75 shell ergonomics shipped; PUT/RUN/UPDATE still pending)

Authenticated PRIVMSG to `{machine}_console` runs a **oneshot** job (default **PowerShell 5.1** `-NoProfile -NonInteractive -EncodedCommand`). Replies are Query-only:

```text
out id=<job> seq=<n> <chunk>
err id=<job> seq=<n> <chunk>
DONE id=<job> exit=<code>
```

Long lines are chunked to ~350 payload chars (no silent 400 clip). Verbs:

| Verb | Purpose |
|------|---------|
| plain line | PowerShell (default) |
| `cmd: …` | COMSPEC `/d /c` escape hatch |
| `psb64:<b64>` | EncodedCommand; UTF-16LE native or UTF-8 script bytes |
| `STATUS` / `PUT` / `RUN` / `GET` / `UPDATE` | Still FR #78 / #77 — not in #75 |

```text
PRIVMSG marchhare_console :Write-Output $PSVersionTable.PSVersion
PRIVMSG marchhare_console :cmd: echo %COMSPEC%
PRIVMSG marchhare_console :psb64:<utf16le-or-utf8-base64>
```

## Encoding policy

- Short ops: **plain text** (readable in Halloy / irc.log).
- Scripts / `$` / spaces: **base64** (`psb64`; PUT later).
- Secrets: **never** clear IRC — local files or agentic-file SEAL.
- Large logs/MSI: HTTPS allowlist or path drop — IRC is control plane.

## CAST IRON ops notes (until UPDATE FR ships)

- Do not `Restart-Service Airc` / msiexec **airc** mid-playbook over airc — the transport dies.
- Prefer `start /wait msiexec` and install **airc last/alone**.
- LocalSystem ConsoleHome must not be `C:\Users\Default\.airc` (see post-install §8b).
- Reserved nick + wrong GUID → oper `PASSWD {machine}_console <guid>` then restart Airc.
