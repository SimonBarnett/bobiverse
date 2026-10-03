<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-mode3-dumb-exec-ergonomics-2026-09-19.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Mode 3 DUMB exec ergonomics (long installs / HTTPS / meta-char argv)

**Date:** 2026-09-19  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/2  
**Raised by:** Slab (homelab / flamingo Mode 3)  
**UAT + hostile MRB owner:** Slab (standing order — originating agent)  
**Build orchestrator:** Bob  

## Context

After installing Grok Build CLI + Grok Bot desktop onto **flamingo** via Mode 3 sealed DUMB (`cm-inv` → `flamingo` on `#cm-bob-oscar`). Chair IONOS; thin jail `C:\airc\jail`. Policy from `scripts/dumb_agent.py` (`DEFAULT_BINS`, `META_CHARS`, `//` / `\\` jail checks, `timeout_s` capped 1–60).

Product FR for Mode 3 operator UX (docs + optional protocol/helpers) — not a panic bug.

## What worked

- Official `https://x.ai/cli/install.ps1` for grok/agent once backgrounded on the thin.
- DUMB **`put`** of a `.ps1` into the jail, then short **`exec`** of `powershell.exe -File <relative-in-jail.ps1>` that `Start-Process`es a longer inner script (HTTPS/pipes only in file body, not argv).

## Asks (priority)

1. **`https://` in argv → `error: jail`** — document; consider allow HTTPS URLs in-policy, or first-class `fetch`/`download` into jail, or helper so operators avoid `//` trap.
2. **Meta-chars `&|><^` → `error: bin`** — document allowlist + meta rules next to CAPA; optional `allow_meta` or documented spawn-detached recipe without `&` (`put` + `Start-Process`).
3. **Split overloaded `error: bin`** — distinguish empty argv / non-allowlisted argv0 / meta (`bin` / `meta` / `empty_argv` or `hint` field).
4. **60s exec ceiling** — document put→spawn→poll log; optional higher timeout for allowlisted bins or `spawn` op (returns immediately, pid/log under jail); optional `get` jail log without another exec.
5. **Cookbook:** Mode 3 “install arbitrary HTTPS payload on elder thin” via `put` + spawn + poll (flamingo-scale example: Grok Bot Setup silent `/S`).
6. **Prefer `put` over IRC-chunked `echo >>` / `-EncodedCommand`** — document put size limits + multi-put assemble if needed.

## Acceptance

1. `docs/mode3-dumb-ops.md` (or README section) lists allowlisted bins, `META_CHARS`, `//` jail rule, timeout cap, and `put`+spawn+poll pattern.
2. Operator-facing errors distinguish meta vs bin vs jail.
3. (Stretch) `download` / `spawn` helpers so HTTPS install does not require reinventing char-code URL assembly.
4. Tests where applicable; commit/push. Slab UAT on flamingo thin + hostile MRB.

## Non-goals

- Weakening jail for UNC / `..` / path escape.
- Dumping `connector.key` or live PINs into chat.
- Claiming Win95 TLS.
