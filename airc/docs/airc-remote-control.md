# Airc remote control (protocol sketch)

See **[feature-request-airc-remote-control-2026-10-01.md](./feature-request-airc-remote-control-2026-10-01.md)** for LOCKED success metrics.

## Today (v0.1.x)

Authenticated PRIVMSG to `{machine}_console` pipes each line into a **cmd.exe** session. Stdout returns as Query PRIVMSG, clipped to ~400 characters. Multi-line work usually means gist + `irm` + `powershell -File`.

```text
PRIVMSG marchhare_console :sc query Airc
PRIVMSG marchhare_console :cmd /c type <ai root>\airc\VERSION
```

## Target verbs (FR)

| Verb | Purpose |
|------|---------|
| `STATUS` | Airc Running + VERSION files (bob/airc/jeeves) |
| plain line | PowerShell (default) |
| `cmd: …` | COMSPEC escape hatch |
| `psb64:<b64>` | `powershell -EncodedCommand` |
| `PUT path` + chunks | Write file (base64 seq) |
| `RUN path` | Execute; end with `DONE id=… exit=…` |
| `GET path` | hash/size + head/tail |
| `UPDATE airc\|bob\|jeeves [ver]` | Allowlisted GitHub Release MSI; airc updates defer self-recycle |

## Encoding policy

- Short ops: **plain text** (readable in Halloy / irc.log).
- Scripts / `$` / spaces: **base64** (`psb64` or PUT).
- Secrets: **never** clear IRC — local files or agentic-file SEAL.
- Large logs/MSI: HTTPS allowlist or path drop — IRC is control plane.

## CAST IRON ops notes (until FR ships)

- Do not `Restart-Service Airc` / msiexec **airc** mid-playbook over airc — the transport dies.
- Prefer `start /wait msiexec` and install **airc last/alone**.
- LocalSystem ConsoleHome must not be `C:\Users\Default\.airc` (see post-install §8b).
- Reserved nick + wrong GUID → oper `PASSWD {machine}_console <guid>` then restart Airc.
