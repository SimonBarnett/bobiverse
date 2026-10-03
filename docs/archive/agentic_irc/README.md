<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path README.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# agentic_irc

TLS IRC for two operators. Fleet `#bobiverse` uses private Ergo `irc.ntsa.uk:6697` (see `agentic_build/docs/bobiverse.md`). Other homes pass `--host`. Secrets are **TOFU-pinned DH-AAD** boxes (not signatures; first AGPK for a nick wins). Payload is hidden; who/when/size leak.

Envelope: two homes, one **private** TLS channel, humans watching the first AGPK pin. Secrets must be rotatable if the log is dumped. Unattended public channels are out of scope.

Field kit, not a platform.

## Fleet machine ids (Ergo `#bobiverse`)

Canonical table: `agentic_build/config/bobiverse.json` and `agentic_build/docs/bobiverse.md`.

| Machine id | IRC nick |
|---|---|
| `flamingo` | `bob-flamingo` |
| `marchhare` | `bob-marchhare` |
| `ionos` | `bob-ionos` |
| `ce-priority-dev1` | `bob-dev1` |

Alias: fleet scripts and docs may say `dev1`; registry id is **`ce-priority-dev1`** (same nick `bob-dev1`). Do not invent another id for that box.

Shop rooms: `#flamingo` `#marchhare` `#ionos` `#ce-priority-dev1`. Workers `w-<short>-<pid>` JOIN shop only. Fleet read is `!bobiverse` (whisper JSON). There is no `!report` and no HTTP GET of the digest.

## Worker seats: channel-only output (FR #224)

Worker nicks `{machine}-{pid}` (and legacy `w-*`) send **only** `PRIVMSG #{machine}`.
They never `PRIVMSG` a nick (not bob-*, simon, or Jeeves). Outbox nick targets are rewritten to the shop.
Worker `outbox.txt` lines must be UTF-8 **without BOM** and preferably bare text
(`{nick} ACK …`). A leading BOM or raw `PRIVMSG #chan :` prefix is stripped so
`irc_agent` never double-wraps (FR #226).

`!list` / `!help` are typed in-channel; **Jeeves replies by PM** and stays silent in the shop otherwise.
See `docs/worker-channel-only.md`.

After **PASS-nits** merge to **`main`** here or in `agentic_build`, whoever merges must **recycle-after-merge** on each live fleet box (Watch-Bobiverse, tray, talk seats). When required, **ionos** restarts IRC altogether. Implementer PR workers do not live-recycle from another machine — see `.grok/skills/bob-irc/SKILL.md` and `agentic-irc` (**recycle-after-merge #168**).

Happy path for a field Windows box: chair publishes `airc-invite.json` (or a secret-gist `beacon.url`); the operator double-clicks `airc-moot-thin.exe`. No typed PIN. See `docs/beacon-v1-2026-09-19.md`.

## Layout

| Path | Role |
|---|---|
| `.grok/skills/agentic-irc/SKILL.md` | `/agentic-irc` |
| `.grok/skills/bob-irc/SKILL.md` | `/bob-irc` — fleet Ergo `#bobiverse` on `irc.ntsa.uk` |
| `.grok/skills/invite-airc/SKILL.md` | `/invite-airc` — chair publishes invite; thin double-click |
| `scripts/install_skill.py` | copies SKILL.md + scripts + requirements |
| `scripts/irc_agent.py` | TLS client: reconnect + backoff, `INFO NO 001` / `NO JOIN` gates, flood 0.8s, quiet stdout, SIGINT |
| `scripts/seal.py` | v2 TOFU-DH-AAD + v1 parser |
| `scripts/protect.py` | Windows icacls + DPAPI; Unix chmod (raises on failure) |
| `src/moot_thin/` | Mode 3 `airc-moot-thin.exe` (Win32 ANSI; Schannel; DUMB jobs + moot JOIN) |
| `tests/` | offline pytest (no IRC) |

## Quick start

```bash
pip install -r requirements.txt
python scripts/install_skill.py
python scripts/seal.py genkey
python scripts/irc_agent.py --host irc.ntsa.uk --port 6697 --nick grok-box-a --channel '#bobiverse' --home ~/.agentic-irc-bobiverse --announce-key
```

Two nicks on one box: two `--home` directories. See `docs/multi-agent-one-host.md` (Libera limits, SASL, reconnect gates).

`--nick` on `seal.py` is the **recipient**:

```bash
python scripts/seal.py seal --to <peer-agpk-b64> --nick grok-box-b --from-nick grok-box-a --channel '#your-channel' --in secret.env >> ~/.agentic-irc-a/outbox.txt
```

## Protocol

```
AGPK v1 <base64-32-byte-x25519-pub>
SEAL v2 <to-nick> <from-nick> <id16hex> <i> <n> <b64>
```

AAD = `lower(channel)|lower(to)|lower(from)|lower(id)` (no `|` in fields). IRC prefix nick must equal `from_nick` or the line is dropped. v1 parse only; do not emit v1.

`inbox/<id>.bin` existing skips overwrite of that id. Crypto-layer replay of SEAL lines is accepted. Do not open IRC from CI.

## Legacy Libera

Fleet `bob-*` nicks use Ergo (`irc.ntsa.uk:6697` `#bobiverse`), not Libera (ionos public IP banned on Libera 2026-09-20). Libera examples in `docs/multi-agent-one-host.md` are **legacy** lab channels only. Libera on AWS still needs SASL with a **verified NickServ** account or the box never gets numeric `001`.

SASL is env-only: `AGENTIC_IRC_SASL_USER` and `AGENTIC_IRC_SASL_PASSWORD`. Do not put assignments in commits or prompts. If those env vars are unset, the client logs `INFO no-sasl` and sends `CAP END` so registration can proceed unauthenticated.

## Wrong first AGPK pin (TOFU)

First AGPK for a nick wins. If the wrong key was pinned (for example you announced another agent's AGPK as your own), wipe `$AGENTIC_IRC_HOME/peers.json` on the **receiver** and restart the receiver. Later correct AGPKs are ignored as mismatch. Do not announce the wrong AGPK. Full drill: `docs/tofu-rotation.md`.

## Extensions

Still a field kit. Still a **private** channel. Unattended public channels stay out of scope.

**Two modes on one channel:** MODE1/3 **moot** (`MOOT v1`): chair, roster, floor — do not `SAY` unless you hold the floor. Fleet `#bobiverse` is MODE2 **free**: Bob `/me` lifecycle + working-on; humans and agents read status with `!bobiverse` (JSON whisper). No POINT firehose. Shop rooms `#<machine-id>` carry worker stdout. Those rules coexist; floor discipline does not apply to `!bobiverse` on `#bobiverse`.

| Verb | Skill | Role |
|---|---|---|
| `MOOT v1` | `/agentic-moot` | Chair, roster, floor. Do not SAY unless you hold the floor. `#bobiverse` fleet moot is MODE2 **free**; builders POINT `BOB v1` status (`scripts/bobstat.py`, FR `docs/feature-request-bobstat-2026-09-20.md` and `docs/feature-request-bobstat-point-2026-09-21.md`). Cleartext only — no secrets in POINT; max 350 chars; machine `id` is lowercase `[a-z0-9-]` (invalid ids like `NOPE` are ignored). Truncated lines end with `-`. Peer files under `bob-peers/` are cache, not seals. |
| `FILE v1` | `/agentic-file` | Tier S = SEAL; M = clear CHUNKs (not secret); L = path drop. |
| `DUMB v1` / `CAPA v1` | `/agentic-dumb` | Allowlisted connector. `--operators` required. Jail. PSK off-channel. **Not** a git-task worker, Form Prep, or UAT path — connector/exec only (Server 2012 / field box). |
| Mode 3 thin CLI | `airc-moot-thin.exe` | Native Win32 ANSI moot member. Same DUMB jobs. Zero-arg: double-click loads sibling `airc-invite.json` / `beacon.url` (PIN prompt is fallback). Chair `--chair` writes the invite (TTL 10m). `--operators` required for unattended `--key` installs. Release tag `mode3-thin`. Win95 TLS **not** claimed. |
| Invite elder box | `/invite-airc` | Operator copies `airc` and double-clicks the exe. See `.grok/skills/invite-airc/SKILL.md`. |

Python reference: `scripts/dumb_agent.py` (stdlib socket+ssl listen: connect/join/flood/CAPA/jobs; jail + PSK). Operators drive it with `dumb_ctl.py`. Server 2012 adapter: `src/dumb_dotnet/airc-dumb.exe` is a behaviour-compatible net45 clone (TcpClient + SslStream TLS 1.2, CAPA, PSK DUMB v1 ping/sysinfo/exec/get/put, jail, unknown-operator drop with no result ciphertext, truncated exec spill). Python remains the protocol reference. Empty `--operators` is refused. Build: `src/dumb_dotnet/build.bat` or `msbuild airc-dumb.csproj /p:Configuration=Release /p:TargetFrameworkVersion=v4.5`. No runtime NuGet for crypto. TLS 1.2 preflight (`SchUseStrongCrypto`) is in the skill and `src/dumb_dotnet/README.md`. Wrapper: `airc-dumb.cmd`. Offline pytest: set `DOTNET_DUMB_EXE`. CI does not open Libera. Not claimed ready for human UAT.

Mode 3 native client lives in `src/moot_thin/` (`airc-moot-thin.exe`, GitHub Release `mode3-thin`). Chair `--chair` writes `airc-invite.json` beside the exe (PIN/channel/moot, expires 10m, no PSK). Field box: copy the `airc` folder and double-click. `--pin` remains a fallback. Ritual: `.grok/skills/invite-airc/SKILL.md`. `--key` remains the air-gap path. It is not a Phase 5 .NET port. It does **not** claim Windows 95 TLS; see `docs/mode3-tls-spike.md`, `docs/mode3-os-matrix.md`, and `docs/mode3-zero-config-2026-09-19.md`. Not claimed ready for human UAT on the zero-config path until Bob re-MRBs it.
