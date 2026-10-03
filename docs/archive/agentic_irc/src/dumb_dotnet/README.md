<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path src/dumb_dotnet/README.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# airc-dumb (.NET 4.5 port)

Python `scripts/dumb_agent.py` is the protocol reference. This tree is the Server 2012 adapter: a behaviour-compatible clone, not an LLM.

**Status:** protocol clone of the Python connector (TcpClient + SslStream TLS 1.2, CAPA v1, PSK DUMB v1 jobs ping/sysinfo/exec/get/put, jail, unknown operator → no result ciphertext, truncated exec spill to `HOME/dumb/results/<id>.txt`). Empty `--operators` is refused. Connector key is raw 32 bytes or `AIRC1`+DPAPI. AES-256-GCM is in-tree (no runtime NuGet). Not claimed ready for human UAT. Live Server 2012 Libera is operator/manual (`tests/MANUAL.md`).

Build (2012 box or modern box; targeting pack optional — csproj falls back to the installed 4.x runtime):

```
build.bat
```

or:

```
msbuild airc-dumb.csproj /p:Configuration=Release /p:TargetFrameworkVersion=v4.5
```

CLI (same flags as Python, plus offline hooks for pytest):

```
airc-dumb.exe --nick N --channel #chan --home DIR --allow-path DIR --operators alice,bob
airc-dumb.exe --selftest
airc-dumb.exe --offline --nick N --channel #chan --home DIR --allow-path DIR --operators alice --from-nick alice --job-in job.json --job-out out.json
```

`--tls-insecure` skips certificate validation. Lab/offline only (loopback pytest). Do not use on a real network.

Wrapper: `airc-dumb.cmd` next to the exe for a scheduled task.

TLS 1.2 preflight on Server 2012: if connect fails with SslException, apply Microsoft guidance for enabling TLS 1.2 on .NET 4.5 (`SchUseStrongCrypto`). Do not downgrade TLS. Do not ship a signed exe from CI.

Offline pytest: set `DOTNET_DUMB_EXE` to a built `airc-dumb.exe`; otherwise those tests skip. CI must not open a public IRC network.
