<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path src/moot_thin/README.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# airc-moot-thin (Mode 3)

Win32 **ANSI** 32-bit console PE. Not an LLM. Not 16-bit DOS. Not the net45 `airc-dumb.exe` connector (that lives in `src/dumb_dotnet/`).

Joins a moot, accepts **DUMB v1** sealed jobs from `--operators`, runs allowlisted bins inside `--allow-path`, returns stdout/stderr/rc.

## Toolchain (primary)

MSVC x86 (Visual Studio 2022 Build Tools / GitHub `windows-latest`):

```
# x86 developer prompt, or GHA ilammy/msvc-dev-cmd arch=x86
cd src\moot_thin
build.bat
airc-moot-thin.exe --selftest
```

Defines: `WINVER=0x0501`, `_WIN32_WINNT=0x0501`, no `UNICODE`. Subsystem CONSOLE. Links `ws2_32 secur32 crypt32 advapi32`.

Optional: MinGW-w64 i686 (`make` / `gcc -m32`).

## WINVER / known floors

| Macro | Value | Meaning |
|---|---|---|
| `WINVER` / `_WIN32_WINNT` | `0x0501` | XP-era SDK surface (Winsock2, Schannel, CryptoAPI) |
| Character set | ANSI (`*A` APIs) | Not Unicode; intended 9x-era *feel*, but **not** a 9x binary |
| Machine | x86 | 32-bit PE |

**Windows 95/98/NT4 will not load this PE.** **Windows ME excluded.** Live fleet IRC is private Ergo **`irc.ntsa.uk:6697`** (Schannel TLS 1.2, same class as legacy Libera). Expected floor: **Windows 8 / Server 2012+**. Libera is legacy only. See `docs/mode3-tls-spike.md`. This README does **not** claim a Win95 pass.

Mode 3 is **not** a fleet talk seat: do not pair on `#bobiverse`, do not use `bob-*` or `{machine}-{pid}` nicks by default, and do not POST digest `/bob/v1/report` or answer `!bobiverse`. PIN chair is `airc-moot-thin.exe --chair` on a **private** pairing channel; digest chair **Jeeves** is `irc_agent.py --chair` on `#bobiverse` only.

## Task visibility (console)

When a chair sends a DUMB job and this box has a real console, the thin client prints an English task line, animates `\\|/-` while the job runs, then **`DONE`** (green) or **`FAIL`** (red) plus a one-line error. Redirected stdout (`--selftest`, log capture) stays plain `INFO` lines. The built exe carries `airc-moot-thin.ico` for Explorer.

## First run (zero-config)

Click the exe, or run it with no flags. It fills `home` from the exe directory, `allow_path` from `{home}\jail`, and `nick` as `m3-<sanitized-hostname>` (unless ini/CLI set). Default `hello` is **empty** (no `{nick}-online` on JOIN); set `--hello` or `hello=` only if an operator explicitly wants a channel line. If `airc-moot-thin.ini` sits beside the exe it is loaded **without** wiping those values; CLI still wins.

Chair (modern box):

```
airc-moot-thin.exe --chair
-> PIN 482917   moot=<16hex>   channel=#airc-moot   expires 10m
-> copy-paste thin (expires 10m):
airc-moot-thin.exe --pin 482917 --channel "#airc-moot" --moot <16hex> --host irc.ntsa.uk
```

`482917` above is the **fixture** PIN from `--selftest`, not a live secret. Live `--chair` prints a fresh PIN.

Thin (field box): copy the `airc` folder and run **that one line**. Self-heal fills nick/home/jail. Interactive fallback: type the PIN at `Enter PIN:`. The long-term PSK is **not** sent as cleartext. After GRANT the thin writes `{home}\dumb\connector.key` and `{home}\dumb\paired.ini` (no PIN, no PSK) and joins the moot. Success line: `joined as <nick> moot=<id> pin=ok`. Ritual: `.grok/skills/invite-airc/SKILL.md`.

Air-gap fallback: copy a 32-byte key off-channel and use `--key` / `--operators` / `--moot` as before. Empty `--operators` is still refused for unattended installs.

Default pairing channel is `#airc-moot` when none is set (**never** `#bobiverse`). Put `channel=#your-private-chan` in a sibling ini for a real room. See `docs/mode3-zero-config-2026-09-19.md`.

## CLI (advanced / air-gap)

```
airc-moot-thin.exe --nick thin-box --channel #ops --moot 0123456789abcdef ^
  --home C:\airc-thin --allow-path C:\airc-thin\jail --operators cm-bob ^
  --key C:\airc-thin\dumb\connector.key
```

`--config airc-moot-thin.ini` may supply the same keys; CLI wins. Empty `--operators` is refused (no exec, no result ciphertext). `--selftest` and `--offline` never open a socket. `--once` is one session (no reconnect); chair `--once` exits after GRANT.

## Protocol

- IRC: NICK/USER/JOIN, flood 0.8s, CAPA every 600s, reconnect backoff unless `--once`.
- Moot: `MOOT v1 JOIN <id>` (chair should OPEN first).
- Jobs: DUMB v1 `ping` / `sysinfo` / `exec` / `get` / `put`. AES-256-GCM PSK, AAD `lower(channel)|lower(to)|lower(from)|lower(id)|dumb-v1`.
- Exec bins: `cmd.exe`, `hostname.exe`, `ipconfig.exe`, `whoami.exe` (+ names without `.exe`). `powershell.exe` only if present on the box.
- Jail: path must resolve under `--allow-path`. UNC and `..` escapes refused. Truncation: `truncated: true` and spill `HOME\dumb\results\<id>.txt` over 8192 bytes.

## Secrets

Do not commit keys. Do not print the PSK. Fingerprint = SHA-256 of the 32 raw key bytes (logged as `keyfp=`). `AIRC1`+DPAPI files from Python `protect.py` unprotect on the same Windows user; raw 32-byte files are portable.
