<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mode3-zero-config-2026-09-19.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Mode 3 zero-config onboarding (2026-09-19)

**Surface:** `src/moot_thin/` (`airc-moot-thin.exe`)
**Trigger:** Walrus human UAT worked, but first-run UX required flag soup, a hand-copied PSK, and chair OPEN before thin JOIN. This ticket is **operator UX**, not a TLS miracle.

**Status:** implemented P0–P3 in-tree. **Not** ready for human UAT until Bob re-MRBs this path. **Live IRC is Ergo `irc.ntsa.uk:6697`** (Libera legacy). **Windows 95/98/NT4/XP live TLS is still not claimed** (U1 / `docs/mode3-tls-spike.md`). **Do not pair on `#bobiverse`** — use a private channel (default `#airc-moot`).

## Charge

**I click the exe. Some magic (PIN). I am in.**

No mandatory `--nick --channel --moot --home --allow-path --operators --key` on the happy path. Advanced flags remain for agents and air-gap installs.

## Acceptance (Z0–Z8)

| ID | Rule | Notes |
|---|---|---|
| Z0 | Double-click / zero args is a supported path on Win8+ / Server 2012+. | Console PIN prompt, or `--pin`. Live Ergo (`irc.ntsa.uk:6697`) needs Schannel TLS 1.2. |
| Z1 | Self-heal defaults: `home` = directory of the exe; `allow_path` = `{home}\jail`; `nick` = `m3-<sanitized-hostname>` (IRC-safe, <=32); `hello` empty unless ini/CLI set; auto-load `{exeDir}\airc-moot-thin.ini` if present **without** wiping after load. | Also auto-load `{exeDir}\dumb\paired.ini` from a previous PIN pair (no PSK in that file). CLI still wins. |
| Z2 | PIN pairing is the primary magic: 6-digit numeric PIN, human-readable, TTL 10 minutes, single use. | Chair prints PIN on **local stdout only**. |
| Z3 | PIN ceremony does **not** put the long-term PSK in chat as cleartext. | Chair and thin derive a wrapping key from the PIN; GRANT is AES-256-GCM. See crypto sketch below. |
| Z4 | After pair, thin accepts jobs from the pairing chair nick automatically (plus any extra ops already in ini). Empty `--operators` is still refused for unattended/agent installs. | Floor alone is still not enough for exec. |
| Z5 | Chair OPEN creates/displays PIN+moot; thin JOIN that moot after pair. Zero-config thin waits in a channel lobby until PIN validates. | Default lobby channel `#airc-moot` if none in ini/CLI (override with a one-line sibling ini). |
| Z6 | Ancient OS honesty unchanged. | Win95/98/NT4/XP live TLS IRC still blocked. Zero-config is UX for capable Schannel boxes. |
| Z7 | No secrets in git or release assets. PIN is ephemeral. | Do not commit `connector.key`, PIN values from live runs, or SASL assignments. Test vector PIN `482917` is a fixture, not a live secret. |
| Z8 | Offline `--selftest` still green; CI still no live IRC (Ergo or Libera). | `--selftest` / `--offline` never open a socket. |

## Operator story

### Chair (modern box)

```
airc-moot-thin.exe --chair
-> prints: PIN 482917   moot=<16hex>   channel=#airc-moot   expires 10m
-> copy-paste thin (expires 10m):
airc-moot-thin.exe --pin 482917 --channel "#airc-moot" --moot <16hex>
```

`482917` is the fixture PIN used in `--selftest` / docs, not a live secret. Optional: `--channel "#your-private-chan" --nick cm-bob`. The PIN is **not** sent on IRC. See `.grok/skills/invite-airc/SKILL.md`.

### Thin (field box)

```
airc-moot-thin.exe
-> "Enter PIN: ____"
-> creates home/jail beside the exe, nick from hostname
-> TLS join, PAIR HELLO/GRANT, JOIN moot, CAPA, ready for exec
```

Scripted: `airc-moot-thin.exe --pin 482917` (still no long flag soup).

Quiet success line:

```
joined as <nick> moot=<id> pin=ok
```

Air-gap fallback (unchanged high-assurance path): copy a 32-byte `connector.key` off-channel and pass `--key` (or drop it at `{home}\dumb\connector.key`) with `--operators` and `--moot`.

## PIN state machine

```
Chair:
  START
    -> self-heal nick/home/jail
    -> generate PIN (6 digits), pair_id (16 hex), moot id (16 hex unless given)
    -> load or generate long-term PSK (never printed; never on the channel)
    -> CONNECT + JOIN channel
    -> MOOT v1 OPEN
    -> PAIR v1 OFFER (moot, pair_id, expires_unix)     [no PIN, no PSK]
    -> WAIT_HELLO (re-OFFER every 30s until TTL)
         valid HELLO (wrap decrypts, prefix nick matches, unused, TTL ok)
           -> PAIR v1 GRANT (sealed bootstrap) -> PAIRED (single use)
         bad HELLO
           -> count failure; after 5 failures EXPIRED
         TTL
           -> EXPIRED (run --chair again)

Thin:
  START (zero args or --pin)
    -> SELF_HEAL (home/jail/nick/hello; load sibling ini; load paired.ini)
    -> if unattended complete (key + operators + moot): LEGACY_JOIN (pin=n/a)
    -> else PROMPT_PIN (console) or use --pin
    -> CONNECT + JOIN channel (lobby; no moot JOIN yet)
    -> WAIT_OFFER
         PAIR v1 OFFER
           -> derive wrap_key; PAIR v1 HELLO (sealed nick)
           -> WAIT_GRANT
                GRANT unwraps
                  -> persist PSK + operators=chair + paired.ini
                  -> PAIR v1 ACK
                  -> MOOT v1 JOIN, CAPA, hello
                  -> READY (banner pin=ok)
                GRANT fails / TTL
                  -> one clear line, exit 2
```

Unattended/agent path **does not** prompt. Empty operators with a key and no PIN is still a hard refuse (Z4).

## Crypto sketch

Reuse the Mode 3 AES-256-GCM primitive already used for DUMB v1. No new cipher. Not a PAKE. Not signatures. Not an Awin-style API.

**Wrapping key** (both sides, never on the wire):

```
wrap_key = SHA-256( "airc-pin-v1|" || pin || "|" || lower(pair_id) || "|" || lower(channel) || "|" || lower(moot_id) )
```

`pin` is exactly six ASCII digits. `pair_id` and `moot_id` are 16 hex chars. The 16-hex `pair_id` is a public salt so two ceremonies on the same channel do not share a wrapping key.

**Blob** (same shape as DUMB): `nonce(12) || ciphertext || tag(16)`, then base64. One IRC line; no DUMB fragmentation.

**AAD**

| Box | AAD |
|---|---|
| HELLO | `lower(channel)\|lower(moot_id)\|lower(pair_id)\|pair-hello-v1` |
| GRANT | `lower(channel)\|lower(moot_id)\|lower(pair_id)\|lower(thin_nick)\|pair-grant-v1` |

**Wire** (clear headers, sealed bodies):

```
PAIR v1 OFFER <moot16hex> <pair16hex> <expires_unix>
PAIR v1 HELLO <moot16hex> <pair16hex> <b64>
PAIR v1 GRANT <moot16hex> <pair16hex> <b64>
PAIR v1 ACK   <moot16hex> <pair16hex>
```

HELLO plaintext: `{"v":1,"op":"hello","nick":"<thin>"}`
GRANT plaintext: `{"v":1,"op":"grant","psk":"<64hex>","chair":"<chair>","moot":"<16hex>"}`

The long-term PSK is the 32-byte DUMB connector key. After GRANT the thin writes it to `{home}\dumb\connector.key` (raw 32 bytes). The hex form exists only inside the GRANT ciphertext.

IRC prefix nick must equal the HELLO nick or the chair drops the line (same rule as DUMB `from_nick`).

## Threats

| Threat | What happens | Mitigation |
|---|---|---|
| PIN brute force (online) | Attacker sends HELLO guessing the PIN | 6 digits; chair decrypt-fail counter (5) then expire; 10 minute TTL; single GRANT |
| PIN brute force (offline) | Channel observer captures GRANT and tries 10^6 wrapping keys | **In scope.** A 6-digit PIN is ~20 bits. This is **not** a substitute for a private channel. Prefer a **private** pairing channel (never `#bobiverse`). Air-gap `--key` is the high-assurance path. |
| Channel MitM | Observer sees OFFER/HELLO/GRANT headers (moot, pair_id, nicks, sizes) | Headers are not secret. Bodies are GCM. MitM without the PIN cannot read the PSK. MitM **with** a captured GRANT can offline-brute the PIN (row above). |
| PIN typed on the wrong channel | Thin never sees a matching OFFER, or GRANT AAD fails | Default `#airc-moot`; chair prints the channel; sibling ini can set `channel=` |
| First HELLO wins | A same-channel party who also has the PIN can race | Same class as TOFU. Human is holding the PIN; ceremony is short. |
| PIN logged / committed | Operator pastes PIN into git or a ticket | Client does not write PIN to disk. Do not commit live PINs. `--selftest` uses fixture `482917` only. |
| Empty operators unattended | Agent install with no allowlist | Still refused. Pairing is what fills operators from the chair nick. |

The product remains a **private-channel field kit**. PIN pairing removes USB key copy when both sides are already on that channel. It does not make a public channel safe.

## Defaults (Z1)

| Field | Zero-arg default |
|---|---|
| `home` | Directory of `airc-moot-thin.exe` (`GetModuleFileNameA`) |
| `allow_path` | `{home}\jail` |
| `nick` | Sanitized `GetComputerNameA` (lowercase, IRC-safe, <=32; prefix `n` if the name would start with a digit; `thin-box` if empty) |
| `hello` | `{nick}-online` |
| `channel` | Sibling ini / CLI / previous `paired.ini`, else `#airc-moot` on the pairing path |
| `host` / `port` | `irc.ntsa.uk:6697` |
| sibling ini | `{exeDir}\airc-moot-thin.ini` loaded if present; **not** wiped after load; CLI wins |
| previous pair | `{exeDir}\dumb\paired.ini` (no PSK) fills empty fields before sibling ini |
| PSK file | `{home}\dumb\connector.key` (raw 32 or AIRC1+DPAPI). `--key` still works. |

If the pairing path is not in play and a required field is still missing, the exe prints **one** `INFO` line (not a usage dump) and exits 2. Example: `INFO missing channel (add channel=#name to airc-moot-thin.ini beside the exe)`.

## Non-goals

- GUI Win32 dialogs (console PIN is enough).
- Completing .NET Phase 5 live 2012 smoke.
- True Windows 95/98/NT4/XP Libera TLS.
- Claiming ready for human UAT from this ticket.

## Fallback

`--key` (or a `connector.key` already beside the exe) plus `--operators` plus `--moot` is the air-gap path. PIN is not required. Behaviour of Mode 1/2 Python agents is unchanged.
