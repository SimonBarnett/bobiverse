<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path .grok/skills/agentic-dumb/SKILL.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: agentic-dumb
description: >
  Drive an ancient host (Server 2012) from IRC. Connector only, no LLM. Use for
  Server 2012, dumb agent, cmd.exe on the other box. Install only on machines you administer.
---

# agentic-dumb

Foundation: harvest-agent-skills (honesty box) -> report back to https://github.com/SimonBarnett/agentic_irc

Not an agent. **Not a git-task worker** â€" no Form Prep, no hostile MRB loop, no UAT stamp from this connector. Operators drive allowlisted exec on a box they administer (e.g. Server 2012); fleet build jobs stay on grok/Cursor workers.

**Two chairs:** fleet digest **Jeeves** (`irc_agent.py --chair` on `#bobiverse`) is not the Mode 3 PIN chair. Elder pairing uses **`airc-moot-thin.exe --chair`** on a **private** channel (never `#bobiverse`). Mode 3/DUMB must not POST `/bob/v1/report`, answer `!bobiverse`, or impersonate fleet talk nicks (`bob-*`, `{machine}-{pid}`). Default thin nick is `m3-<hostname>`; default hello on JOIN is empty.

Connectors share the same PSK DUMB v1 protocol:

- **Python reference:** `scripts/dumb_agent.py` joins the channel (stdlib socket+ssl), announces CAPA on join and every 10 minutes, and runs **allowlisted** ping/sysinfo/exec/get/put from `--operators` only.
- **net45 adapter:** `src/dumb_dotnet/airc-dumb.exe` (TcpClient + SslStream TLS 1.2). Same CAPA, jobs, jail, and wire rules. Python remains the protocol reference.
- **Mode 3 thin CLI:** `src/moot_thin/airc-moot-thin.exe`. Click the exe / enter PIN (chair `airc-moot-thin.exe --chair`). `--pin` for scripting. `--key` still works for air-gap. Empty `--operators` refused for unattended installs. Win95 TLS is **not** claimed. See `docs/mode3-zero-config-2026-09-19.md`.

Unknown operators: no exec, no result ciphertext on the channel. Truncated exec stdout/stderr spills to `dumb/results/<id>.txt` with `truncated: true`. Empty `--operators` is refused.

Generate PSK **off-channel** (`python scripts/seal.py dumb-key`). Copy `connector.key` by RDP/USB. Never print it. Compare sha256 fingerprints out of band. The file may be raw 32 bytes or `AIRC1`+DPAPI.

`--operators` is required. Jail `--allow-path` (default `C:\agent-drop`). Default bins: cmd.exe, powershell.exe, hostname.exe, ipconfig.exe, whoami.exe. Exec policy (meta chars, `//` jail trap, 60s cap, put+spawn+poll): **`docs/mode3-dumb-ops.md`** (issue [#2](https://github.com/SimonBarnett/agentic_irc/issues/2)).

```
python scripts/dumb_ctl.py ping --home H --channel '#ops' --from-nick ME --to srv2012-box
python scripts/dumb_ctl.py exec --home H --from-nick ME --to srv2012-box --argv hostname
```

TLS 1.2 preflight on Server 2012: if SslException, enable SchUseStrongCrypto (Microsoft docs). Do not dump connector.key. Do not exec if operators empty.

Build the net45 exe: `src/dumb_dotnet/build.bat` or `msbuild airc-dumb.csproj /p:Configuration=Release /p:TargetFrameworkVersion=v4.5`. No runtime NuGet for crypto. Use `airc-dumb.cmd` as the scheduled-task wrapper. `--tls-insecure` is lab/offline only. Offline pytest: `DOTNET_DUMB_EXE`. Not ready for human UAT (no live Server 2012 claim from this tree). Production fleet IRC is Ergo `irc.ntsa.uk:6697` (Python/net45 default). Pass `--host` for any other network.

Scheduled task (operator fills paths):

```
schtasks /create /tn airc-dumb /sc onstart /ru USER /tr "C:\airc-dumb\airc-dumb.cmd"
```

## Service shape (FR #236)

Always-on DUMB as Windows Service / systemd is designed in `docs/dumb-service-fr236.md`. Account-bound operators consume FR #230 CAP account map. Not a git-task worker.
