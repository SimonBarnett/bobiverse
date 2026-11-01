---
name: bobiverse-airc-commands
description: >
  Airc console command reference - PRIVMSG remote shell via {machine}_console, allowlist, safe diagnostics, staging scripts. Use when sending commands to a box through Airc.
---

# bobiverse-airc-commands

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://bob.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

## Remote shell protocol (FR #75)

An authorized sender (operators list / seeded `bob-<machine>` ear) PRIVMSGs the console:

```text
PRIVMSG <machine>_console :Get-Service Airc
PRIVMSG <machine>_console :cmd: sc query ircJeeves
PRIVMSG <machine>_console :psb64:<base64>
```

- Default is **PowerShell 5.1** (`-NoProfile`); `cmd:` uses COMSPEC; `psb64:` is `-EncodedCommand` (UTF-16LE or UTF-8 payload).
- **Job id frame (FR #5532 / #5678 / #5742):** optional leading `id=<8hex> ` pins DONE/out/err. A leading `id=` that is not exactly eight hex digits is `code=bad_id` / `DONE exit=2` (never PowerShell under a new id). Service `on_line` must send that reply (FR #5742); ear captures non-hex `id=` on err/DONE.
- Replies are Query-only: `out id=… seq=…`, `err id=… seq=…`, then `DONE id=… exit=…`. Long lines are chunked (~350 chars).
- Allowlist: nick must be in operators (installer seeds `bob-<machine>`); arbitrary `bob-*` is **not** auth (FR #3286). With `--require-account` / `--accounts`, SASL/NickServ account must match too.
- PUT/RUN/JOB/UPDATE are separate FRs - see `docs/airc-remote-control.md`. **FR #5280:** bare `UPDATE airc` (no version) schedules Check against the **latest** GitHub Release airc MSI; `UPDATE airc x.y.z` pins a tag.
- **VERSION (FR #5281):** same auth as STATUS (`+o/+h`+). `PRIVMSG {mid}_console :id=<8hex> VERSION` replies `out id= seq=1 VERSION machine=... airc_ver=... [commit=...] [built=...] [hotpatched=...] [hotpatch=1]` then `DONE id= exit=0` (FR #5534 / #5589). `built=` is BUILD.json `built_utc`; HOTPATCH overlays `commit` and adds `hotpatched=` from `hotpatched_utc` (never overwrites `built=`). Allowed when `shell=off` / `jobs=off` like STATUS. STATUS still returns the bob/airc/jeeves aggregate.
- **DCC output (FR #5003 / #5008 / #5531 / #5612 / #5613 / #5654):** caller sends `DCCLISTEN id= host= port= token= [tls=1] [relay=]` (optional leading job `id=<job> ` is accepted; bare `DCCLISTEN` still works). Unused offers expire after 60 s and the table is capped at 32; VERSION/STATUS/PRIORITY/UPDATE clear the offer. Oversized shell replies: console dials out, sends framed bytes, waits for `ACK <sha256>` (FR #5612); no ack -> IRC fallback `dcc failed: no ack`. IRC `DONE ... via=dcc` only after ACK. Handshake fail -> IRC `CONT`/`RESUME` (`dcc failed ...; falling back to IRC`). FR #5654: DCC send is wall-clock bounded (separate from shell run timeout); a never-reading receiver must fall back without DONE exit=124.
- **DCC upload (FR #5194 / #5536 / #5611):** same `DCCLISTEN`, then `PUT path= id= bytes= sha256= via=dcc`. Size cap is the DCC bulk cap (2 MiB); IRC PUT stays 256 KiB. Console dials out and **reads** the frame off the IRC thread (30s I/O timeout -> `err … code=timeout` + `DONE exit=1`), checks sha256, writes atomically under the drop sandbox (same path rules as IRC PUT, including FR #5610 reserved-device reject). Fail -> `err ... dcc failed ...; falling back to IRC` then `CHUNK`/`PUTEND`. Use `Invoke-AircRemote -Action Put` (default DCC) or `-ForceIrcPut`.

## Safe diagnostic commands

`sc query <svc>`, `sc qc <svc>`, `type <ai root>\<product>\VERSION`, `dir <ai root>\<product>\logs`, `tasklist /fi "imagename eq python.exe"`.
Do NOT: kill broad `powershell.exe`/`python.exe`, `sc stop BobIrcd`, edit Ergo files, print secrets.

## Verify the console

`Get-Service Airc`; log shows `chanserv-info status=registered` and `joined #<machine> as <machine>_console`.

## UPDATE and VERSION (FR #5282)

Prefer remote **`UPDATE airc`** over free-form `msiexec` / `Restart-Service Airc` (killing the console mid-playbook drops the transport).

```text
PRIVMSG {mid}_console :UPDATE airc
PRIVMSG {mid}_console :id=c25bd00e UPDATE airc
PRIVMSG {mid}_console :UPDATE airc 1.0.9
PRIVMSG {mid}_console :id=c25bd00e VERSION
```

- **Latest vs pin:** bare `UPDATE airc` takes the latest GitHub Release MSI. `UPDATE airc <ver>` pins `-TargetVersion` (FR #5280 / FR #77). Leading `id=<job>` is accepted (FR #5532); reply is `UPDATE accepted id=...` then `DONE id= exit=`. **FR #5670:** malformed UPDATE (extra args, `;calc`, unknown product/flags) is `code=usage` / `DONE exit=2` (never PowerShell); `release-lookup-failed` is `DONE exit=1`.
- **Restart contract (Refs #5277):** after Apply, expect Airc Running and `{mid}_console` to answer again within a **120s** reconnect budget without manual repair. If it does not, file intake; do not invent a second msiexec.
- **Failure intake (FR #5279):** each Apply/Check failure class (`download-failed`, `msiexec-exit`, `msiexec-timeout`, `stop-failed`, `backup-failed`, `spawn-failed`, `updater-missing`, `asset-url-rejected`, ...) files one `kind:issue` on `SimonBarnett/bobiverse`. `idempotency_key` = `airc-update-fail|{machine}|{product}|{tag}|{result}` so retries do not twin-flood. Title/body are redacted.
- **VERSION (FR #5281):** same auth as STATUS. Reply is `out id= seq=1 VERSION machine=... airc_ver=... [commit=...] [built=...] [hotpatched=...] [hotpatch=1]` then `DONE id= exit=0` (FR #5534 / #5589). `built=` stays BUILD.json; HOTPATCH adds `hotpatched=`. Allowed when `shell=off` / `jobs=off`.

## PRIORITY prepare (FR #5286)

Named procedure prep for TYPE=P only. Never form-prep. Never SQL-fake `UPD`.

```text
PRIVMSG {mid}_console :id=c25bd00e PRIORITY prepare FOO instance=example-dev
```

Walk: EXEC `REPPREPDIRECT2`. Success (`reason=prepared`) only when SDK `ok=true` **and** `EXECPREPLOCK.UPD=N` **and** the `.prp` mtime advanced. Other reasons: `still_unprepared`, `prp_unchanged`, `no_cred`, `name_missing`, `sdk_not_ok`. CredMan target from the instance allowlist (FR #5275); result JSON has SQL + `.prp` evidence and never a password.

See `docs/airc-remote-control.md` and `bobiverse-airc-troubleshooting`.

## Priority Client (FR #5287)

Bare `PRIORITY` (or an unknown sub-verb) is usage, not PowerShell (FR #5533): `err id= seq=1 code=usage PRIORITY connect|status|prepare|formStart|subform|getRows` then `DONE id= exit=2`.

**FR #5614:** the same usage shape applies to unknown `NETWORK` / `EXTENSION` actions and unknown flags (including `LEGION … -Force`): `err … code=usage` or `code=usage unknown-flag=-Force` then `DONE exit=2`. CTCP-framed lines (e.g. `\x01VERSION\x01`) are ignored and never run as PowerShell.

Use the **built-in** Airc Priority Client. Do not copy NAS one-off clients or drop packs. CredMan + instance allowlist only; never invent `url` / company / SQL.

```text
PRIVMSG {mid}_console :id=c25bd00e PRIORITY connect instance=example-dev
PRIVMSG {mid}_console :id=c25bd00e PRIORITY status example-dev
PRIVMSG {mid}_console :id=c25bd00e PRIORITY prepare FOO instance=example-dev
PRIVMSG {mid}_console :id=c25bd00e PRIORITY formStart instance=example-dev form=CUST
PRIVMSG {mid}_console :id=c25bd00e PRIORITY formStart example-dev CUST
```

- **Allowlist:** `config\priority-instances.json` (schema: `airc/config/priority-instances.example.json`). Unknown instance -> refuse.
- **CredMan:** password lives in the Windows credential named credentialTarget (example PriorityWeb/example-dev). Populate remotely with CRED persist ... via=https (FR #5802) or via=irc (FR #5812) when DCC is blocked. Never put a Priority password on IRC, in skills, or in intake.
- **Form walk (FR #5285 / #5803):** ormStart/subform/getRows accept instance=/orm= key=value **or** positional <instance> <form> (same bare id as PRIORITY status <id>). Named keys win when both are present. Unknown instance -> unknown-instance.
- **Form walk replies (FR #5524):** PRIORITY formStart/subform/getRows must return HandleResult.reply only (newline-separated out+DONE). Do not also JobProtocol._emit after FR #5518 on_line already sends action=priority --- that double-fires every walk line.
- **Prepare gates (S4):** TYPE=P uses EXEC `REPPREPDIRECT2`. Success only when SDK `ok=true` **and** `EXECPREPLOCK.UPD=N` **and** `.prp` mtime advanced. Reasons include `still_unprepared`, `prp_unchanged`, `no_cred`, `name_missing`. Never SQL-fake UPD; never form-prep for TYPE=P.

See `docs/airc-remote-control.md`, `docs/feature-request-airc-priority-client-2026-10-31.md`, and `bobiverse-airc-troubleshooting`.

## EXTENSION Priority web (FR #5294)

Authorized **UPDATE-class** verb. Isolated in-service worker (never a peer `*Client.exe`). Default extension id `cgmpadejahkaggjpffnhaoiafbnicgpa` (Chrome Web Store update URL for Chrome and Edge).

```text
PRIVMSG {mid}_console :id=c25bd00e DCCLISTEN id=c25bd00e host=<ip> port=<n> token=<hex> tls=1
PRIVMSG {mid}_console :id=c25bd00e EXTENSION install
PRIVMSG {mid}_console :id=c25bd00e EXTENSION install -WhatIf
PRIVMSG {mid}_console :id=c25bd00e EXTENSION status
```

- **Auth:** same as UPDATE (`+o`/`+h`; `update=off` / `shell=off` / `extension=off` refuse with `DONE id=<qid> exit=126 …` when the command carried `id=` - FR #5552).
- **GPO happy path:** worker uses GroupPolicy on GPO `Priority-web-extension` linked at domain root (`ExtensionInstallForcelist` for Chrome and Edge). `-WhatIf` is read-only (no GPO/registry/gpupdate writes). **FR #5538:** `EXTENSION status` is read-only fill-holes (no HKLM writes); install appends a free forcelist value name and never writes DCs. **FR #5645:** when RSAT GroupPolicy is missing, DC hop is `Invoke-Command`; LocalSystem computer account Access Denied is `reason=gpo_access_denied` with `need=credman:PriorityAirc/ExtensionAdmin` (retry uses that CredMan target; never on IRC).
- **Fill-holes:** after GPO (or when DC is missing), LDAP AD computers only; remote registry ForceInstall on AD hosts. Machine account first; optional CredMan target `PriorityAirc/ExtensionAdmin` on access-denied (never put that password on IRC). **FR #5659:** same identity order (passed DCC CRED / CredMan `PriorityAirc/ExtensionAdmin` / SYSTEM). **FR #5757:** when SMB/IPC is up, ConnectRegistry WinError 53/67 is `remote_registry_stopped` (never `smb_blocked`); GPO success + that error => `skipped:gpo` / `gpo_covers` (not DONE exit=1). **FR #5661:** ICMP alone is not `unreachable`; classify `remote_registry_stopped`, `smb_blocked`, `access_denied`, `host_down` (with `detail` text); `unreachable` only when nothing answers. **FR #5660:** non-Windows (Samba winreg without ProductName/CurrentBuild) -> `skipped: not_windows`, never `present`; forcelist presence matches the id before `;`.
- **Log:** same job `id=` as `DCCLISTEN` -> `DONE ... sha256= via=dcc`. No offer or DCC fail -> IRC CONT + failure lines. No secrets in the log.
- **Isolation:** in-service child (`airc_isolated` + `extension_gpo_then_fill_holes`, FR #5522); worker fault must not stop service Airc. **FR #5665:** if the isolated child dies before a result, log `worker_died` and `DONE exit=1` (never empty success).

See `docs/airc-remote-control.md` and `docs/feature-request-airc-extension-priority-web-2026-10-31.md`.

## NETWORK diagnostic (FR #5301)

Authorized **UPDATE-class** verb. Isolated worker (never LDAP/DNS/sweep on the IRC receive thread). Inventory contract: `hostname`, `ips[]`, `ou` (parent-container DN from AD `distinguishedName`; FR #5587). Runtime inventory is FR-B (#5299); this book is the wire/docs contract.

```text
PRIVMSG {mid}_console :id=c25bd00e DCCLISTEN id=c25bd00e host=<ip> port=<n> token=<hex> tls=1
PRIVMSG {mid}_console :id=c25bd00e NETWORK
PRIVMSG {mid}_console :id=c25bd00e NETWORK diag
PRIVMSG {mid}_console :id=c25bd00e NETWORK diag -WhatIf
```

- **Auth:** same as UPDATE (`+o`/`+h`; `update=off` / `shell=off` refuse with `DONE id=<qid> exit=126 update-disabled|shell-disabled` when the command carried `id=` - FR #5552). Unauthorized is `DONE exit=126 not-op`.
- **Isolation:** worker thread/child; fault must not stop service Airc; console still handles STATUS.
- **Payload:** short IRC `NETWORK accepted` + `DONE id= exit=`; full inventory + log via DCCLISTEN same job `id=` (`DONE ... via=dcc`) or IRC CONT. **FR #5519:** no-offer / DCC-fail registers a resume buffer so `CONT id=<job>` returns the log body (not `no resume buffer`). CAST IRON: no secrets on IRC or in the DCC body.
- **WhatIf:** read-only plan (no writes).

See `docs/airc-remote-control.md` and `docs/feature-request-airc-network-diagnostic-2026-10-31.md`.

## CRED staged + persist (FR #5659 / #5802 / #5812)
## CRED staged + persist (FR #5659 / #5802 / #5811)

Three paths:

1. **Stage (memory, FR #5659):** one-shot identity for LEGION/EXTENSION/NETWORK via TLS DCC.
2. **Persist HTTPS/DCC (CredMan, FR #5802):** write a lasting LocalSystem CredMan entry (e.g. Priority `credentialTarget`) over **HTTPS on 443** when DCC is firewalled, or via DCC when available.
3. **Persist IRC (CredMan, FR #5812):** same CredMan write over the **existing TLS IRC hop (993)** with E2E seal (X25519 + ChaCha20-Poly1305). Use when the box only allows 80/443/993 and no one-time HTTPS drop is hosted.

```text
# Stage (DCC) then use once
PRIVMSG {mid}_console :id=c25bd00e DCCLISTEN id=c25bd00e host=<ip> port=<n> token=<hex> tls=1
PRIVMSG {mid}_console :id=c25bd00e CRED id=c25bd00e via=dcc
# DCC body JSON: {"username":"DOMAIN\\user","password":"..."}
PRIVMSG {mid}_console :id=c25bd00e LEGION flamingo cred=c25bd00e

# Persist Priority CredMan over HTTPS (443) --- firewalled customer boxes
# Operator stages one-shot JSON at an allowlisted URL under https://bob.ntsa.uk/ (or AIRC_CRED_HTTPS_PREFIXES)
PRIVMSG {mid}_console :id=c25bd00e CRED persist target=PriorityWeb/example-dev via=https url=https://bob.ntsa.uk/bob/v1/cred-once/<token>
# Reply: out ... CRED persisted target=PriorityWeb/example-dev + DONE ... cred-persisted target=... account=... (never the password)

# Persist via DCC when outbound DCC works
PRIVMSG {mid}_console :id=c25bd00e DCCLISTEN id=c25bd00e host=<ip> port=<n> token=<hex> tls=1
PRIVMSG {mid}_console :id=c25bd00e CRED persist target=PriorityWeb/example-dev via=dcc

# Persist over existing IRC TLS (993) --- no new ports, E2E sealed (FR #5812)
PRIVMSG {mid}_console :id=c25bd00e CRED persist target=PriorityWeb/example-dev via=irc
# Reply: CRED-HELLO token= pub= exp= alg=x25519-chacha20poly1305 target=...
# Operator encrypts JSON and sends sealed chunks (never plaintext password on IRC):
PRIVMSG {mid}_console :id=c25bd00e CRED-SEAL token=<tok> seq=1/1 ct=<b64>
# Reply: CRED persisted + DONE ... cred-persisted target=... account=... (never the password)
# Failures: cred-rejected-auth, cred-expired, cred-replay, cred-target-not-allowlisted, cred-bad-payload, cred-write-failed:...

# Supported sender (FR #5825) --- never put the password on argv or in a plaintext file
# CredMan source on the driving box:
.\scripts\Send-AircCred.ps1 -MachineId hrs-priority-de -Target PriorityWeb/example-dev -CredManSource PriorityWeb/local-copy -Outbox <bob-home>\outbox.txt -ReplyFile <bob-home>\airc-replies.jsonl
# Or: python airc_cred_send.py --machine ... --target ... --credman-source ... --outbox ...
# Prompt / SecureString: -Username Tabula -Prompt  (reads SecureString; pipes via stdin to Python)
# Exit 0 only on cred-persisted; stdout is ok/err code=... (never the secret)
```

- Password never on IRC. Stage stash is in-memory, TTL ~180s, one-shot `take`. Persist uses CredWriteW LocalMachine under the Airc LocalSystem identity (`airc_credman.write_generic_credential`).
- HTTPS URL must be `https://` under the fleet public base (`bob.ntsa.uk` / `BOB_PUBLIC_BASE`) or a prefix in `AIRC_CRED_HTTPS_PREFIXES`. Rejected URL -> `cred-url-rejected`. Fetch failures surface firewall-aware tokens (`firewall-or-unreachable`, `timeout`, `ssl-error`, `dns-failed`, `http-N`).
- **via=irc (FR #5812):** console replies `CRED-HELLO` (ephemeral X25519 pub + one-time token + short expiry). Operator sends `CRED-SEAL` ciphertext chunks only (Ergo never sees plaintext). Token is single-use; wrong nick -> `cred-rejected-auth`; target must be a `credentialTarget` from `priority-instances.json`.
- **Sender helper (FR #5825):** `Send-AircCred.ps1` / `airc_cred_send.py` wait for HELLO, seal via `seal_cred_payload`, send SEAL chunks, return one named result. Credential from local CredMan or SecureString/stdin --- never `--password` argv or a plaintext file.
- Without `via=dcc` / offer on stage or persist-dcc -> `DONE ... usage cred-requires-dcc`. Persist needs `target=`; persist+https needs `url=`; persist accepts `via=https|dcc|irc`.
- HTTPS URL must be `https://` under the fleet public base (`bob.ntsa.uk` / `BOB_PUBLIC_BASE`) or a prefix in `AIRC_CRED_HTTPS_PREFIXES`. Rejected URL -> `cred-url-rejected`. Fetch failures surface firewall-aware tokens (`firewall-or-unreachable`, `timeout`, `ssl-error`, `dns-failed`, `http-N`). **FR #5811:** every persist outcome reaches IRC (`action=cred` on_line dispatch) with `cred failed: <reason>` / `DONE exit=1 <reason>`; fail-intake uses shared `airc-cred-fail|...` (never silent; never secrets). Also `non-json-body`.
- Without `via=dcc` / offer on stage or persist-dcc -> `DONE ... usage cred-requires-dcc`. Persist needs `target=`; persist+https needs `url=`.

## LEGION remote install (FR #5312 / #5758)

Authorized **UPDATE-class** verb. Isolated worker imports in-service `airc_network_installer` (FR #3991) for **one** hostname or IPv4. Latest Release MSI, timeout 900s, no `--force`. **FR #5758:** preserves the remote `config\airc-install.json` profile (fleet/workstation/client) unless `-Profile fleet|client|workstation` overrides; reports `profile_before`/`profile_after` and warns on downgrade; DONE/JSON carry `profile=` + `installed_version=` + `service=` after a successful install. Identity order (FR #5659 / amends #5594): passed DCC CRED -> CredMan `PriorityAirc/LegionAdmin` -> SYSTEM. Missing CredMan falls through to SYSTEM; wrong passed/CredMan auth is `auth_failed`. WhatIf still plans (FR #5530).

```text
PRIVMSG {mid}_console :id=c25bd00e DCCLISTEN id=c25bd00e host=<ip> port=<n> token=<hex> tls=1
PRIVMSG {mid}_console :id=c25bd00e LEGION walrus
PRIVMSG {mid}_console :id=c25bd00e LEGION 10.0.0.8 -WhatIf
PRIVMSG {mid}_console :id=c25bd00e LEGION flamingo -Profile fleet
```

- **Profile preserve (FR #5758 / #5781 / #5782):** read remote `config\airc-install.json` via CredMan WNet `IPC$` (same as install); keep unless `-Profile` set; report `profile_before`/`profile_after` / downgrade warn; unread share without `-Profile` → `error=profile_unreadable` (never silent client); success DONE carries `installed_version` + `service`. **FR #5782:** when status is `skipped` / already-current, DONE/JSON report the host profile (`profile_before`, or `profile=unchanged` if unread/missing) and clear `profile_warn` --- never imply `profile=client` for an unchanged fleet host.
- **Auth:** same as UPDATE (`+o`/`+h`; `update=off` / `shell=off` refuse with `DONE id=<qid> exit=126 update-disabled|shell-disabled` when the command carried `id=` - FR #5552). Empty/list/OU/invalid targets: `DONE id=<id> exit=126 bad-target reason=empty|list|ou|invalid` (id= omitted only when the operator sent no id; FR #5527). FR #5528: `bad_host!` is invalid, not list.
- **Identity (FR #5659 / #5711 / #5745 / amends #5594):** order is **passed** (DCC `CRED id= via=dcc` then `LEGION|EXTENSION|NETWORK … cred=<id>`) -> **CredMan** (`PriorityAirc/LegionAdmin` / `ExtensionAdmin` / `NetworkAdmin`, overridable via `airc.json` `credman_targets`) -> **SYSTEM** `DOMAIN\HOST$`. Log/DONE for LEGION, EXTENSION, and NETWORK carry `identity=passed|credman|system` and account name, never the secret. Wrong passed/CredMan auth -> `auth_failed` (no silent fallback). Missing CredMan falls through to SYSTEM with `identity_reason=credman-missing:<target>` (or `credman-read-error:<code>`) plus an `identity-fallback` console log line. Plain IRC password/pass tokens is rejected (`usage secrets-on-irc`). NETWORK uses CredMan only for the ADSI bind (DNS stays on the service token).
- **Remote failures (FR #5744):** classify `host_down` (WinError 53/67 + SMB 445 preflight), `auth_failed` (5/1326), `session_conflict` (1219) with `detail` + `step` (never credentials).
- **WhatIf:** installer dry-run plan (no remote install). Log reports `identity=system (HOST$)` (FR #5530 / #5659). Missing CredMan is logged (`credman_missing`) and falls through to SYSTEM. **FR #5655 / #5712 / #5737:** PsExec is never MSI-bundled (Sysinternals licence forbids redistribute). Install/UPDATE runs `Deploy-AircPsExec` to download the official zip with pinned SHA-256 into `%ProgramData%\bobiverse\tools\PsExec.exe` (cache under `tools\cache\`). LEGION (real and WhatIf) uses that airc-owned copy only: hash-ok = pass; missing/corrupt = redeploy from local cache; `psexec-undeployed` if the cache is absent (no network at verb time). Extract/redeploy failures surface as `psexec-download-failed:<ExcType>` (FR #5743; never silent SameFileError). Real run with failures uses `DONE exit=1`.
- **Log:** same job `id=` as `DCCLISTEN` -> `DONE ... via=dcc`. No offer or DCC fail -> IRC CONT. CAST IRON: no secrets on IRC or in the DCC body.
- **Isolation:** installer is not on the IRC receive thread; worker fault must not stop Airc.

See `docs/airc-remote-control.md` and `docs/feature-request-airc-legion-2026-10-31.md`.
