<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mrb-mode3-zero-config-2026-09-19.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB / plan - Mode 3 zero-config onboarding (2026-09-19)

**Repo:** SimonBarnett/agentic_irc
**Surface:** `src/moot_thin/` (`airc-moot-thin.exe`)
**Trigger:** Walrus human UAT worked (hostname `walrus`) but required flag soup, manual ini, off-channel key copy, and chair OPEN first. Simon: technically good, UX savage. Target env may feel like 1995; the product must not.

## Verdict

**FAIL** on operator UX / first-run. Functional Mode 3 (Win8+ Schannel) remains UAT-capable. This ticket is a **zero-config onboarding** plan + implementation hand-off.

## Charge

**I click the exe. Some magic (PIN). I am in.**

No mandatory `--nick --channel --moot --home --allow-path --operators --key`. No treasure hunt for `connector.key`. Optional advanced flags remain for agents/power users.

## What hurt in walrus UAT (evidence)

1. Bare exe / `--config` failed until ini-wipe fix; operators still needed a long CLI.
2. Key generated on IONOS, copied by hand, fingerprint checked with `certutil`.
3. Chair must OPEN moot before thin JOINs - ordering is invisible to a double-click user.
4. Paths/nicks hardcoded in ini (`cm-thin-walrus`, `C:\airc\...`) instead of derived from the box.
5. Release lag / wrong exe revision caused `90320` before the right build landed.

## Locked product rules

| ID | Rule |
|---|---|
| Z0 | Double-click (or run with zero args) is a supported path on Win8+ / Server 2012+. |
| Z1 | Self-heal defaults: `home` = directory of the exe; `allow_path` = `{home}\jail`; `nick` = sanitized hostname (IRC-safe, <=32); `hello` = `{nick}-online`; auto-load `{exeDir}\airc-moot-thin.ini` if present **without** wiping after load (already fixed in 4af0f49 - keep). |
| Z2 | **PIN pairing** is the primary magic: short numeric PIN (6 digits), human-readable, short TTL (e.g. 10 minutes), single use. |
| Z3 | PIN ceremony does **not** put long-term PSK in chat as cleartext. Prefer: chair shows PIN; thin enters PIN; both derive a session wrapping key or fetch a sealed bootstrap blob over the already-joined channel using a short-lived join secret. Document the crypto sketch in `/docs` - no invented Awin-style APIs. |
| Z4 | Operators allowlist: after pair, thin accepts jobs from the pairing chair nick automatically (and optional extra ops in ini). Empty operators still refused for unattended/agent installs. |
| Z5 | Moot id: chair OPEN creates/displays PIN+moot; thin JOIN that moot after pair. Zero-config thin may wait in "lobby" until PIN validates. |
| Z6 | Ancient OS honesty unchanged: Win95/98/NT4/XP live Libera still blocked (U1). Zero-config is UX for capable Schannel boxes, not a TLS miracle. |
| Z7 | No secrets in git or release assets. PIN is ephemeral. |
| Z8 | Offline `--selftest` still green; CI still no Libera. |

## Suggested UX (operator story)

### Chair (modern box / agent)

```
airc-moot-thin.exe --chair   # or python moot/dumb helper
-> prints: PIN 482917   moot=<16hex>   channel=#cm-...   expires 10m
```

### Thin (walrus / field box)

```
airc-moot-thin.exe
-> "Enter PIN: ____"
-> creates home/jail beside exe, derives nick from hostname
-> TLS join, PIN complete, JOIN moot, CAPA, ready for exec
```

Optional: `--pin 482917` for scripting without prompt (still no long flags).

## Phases for build agent

### P0 - Docs + crypto sketch
Write `docs/mode3-zero-config-2026-09-19.md` with PIN state machine, threat notes (PIN brute force / channel MitM), and acceptance IDs Z0-Z8.

### P1 - Self-heal zero-arg path (no PIN yet)
- Zero args: auto home/jail/nick/hello; load sibling ini if present without wipe.
- If ini incomplete, prompt minimally or fail with one clear line (not a usage dump).
- Offline tests for defaults + ini auto-load.

### P2 - PIN pair MVP
- Chair mode emits PIN + moot OPEN.
- Thin prompts for PIN (console; Win32 ANSI).
- Complete pair so thin has operators=chair and shared job key without USB key copy when both on same Libera channel and PIN matches.
- Document fallback: `--key` still works for air-gap.

### P3 - Polish
- Quiet success banner: `joined as <nick> moot=<id> pin=ok`
- `--once` for smoke; reconnect backoff unchanged.
- Bump VERSION; rolling `mode3-thin` release picks up binary.
- Update README + skill: "click the exe / enter PIN".

## Pass bar (Bob re-MRB)

1. On a clean folder with only the exe (+ optional channel default in a tiny companion or baked test default for lab): double-click / zero-arg reaches PIN prompt or joins when PIN supplied.
2. Walrus-style box: no hand-edited 8-flag command line required for happy path.
3. Hostname-derived nick; jail under exe dir.
4. PIN path avoids cleartext long-term PSK on the channel.
5. pytest / `--selftest` green; no Libera in CI.
6. Docs state Win95 TLS still not claimed.

## Non-goals

- GUI Win32 dialogs (console PIN is enough for v1).
- Completing .NET Phase 5 live 2012 smoke.
- True Win95 TLS.

## Hand-off

Build agent on **ionos**, cwd `C:\ai\agentic_irc`: implement P0 then P1 then as much of P2 as fits; commit/push; do not claim ready for human UAT until Bob re-MRBs zero-config. Prefer build0.1. Leave unrelated jobs alone.
