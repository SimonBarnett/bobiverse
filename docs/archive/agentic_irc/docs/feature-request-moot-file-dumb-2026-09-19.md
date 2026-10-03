<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-moot-file-dumb-2026-09-19.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request Ã¢â‚¬” agentic_irc extensions (2026-09-19)

Source PDF: [feature-request-moot-file-dumb-2026-09-19.pdf](./feature-request-moot-file-dumb-2026-09-19.pdf)

## Summary

Build proposal / engineering handoff for three extensions on the existing two-operator Libera TLS field kit:

1. **Moot** Ã¢â‚¬” multi-agent assembly (chair, roster, floor, transcript); MOOT v1 verbs; skill /agentic-moot.
2. **File sharing** Ã¢â‚¬” tiers S (SEAL), M (CHUNK), L (path drop); FILE v1 verbs; skill /agentic-file.
3. **Dumb connector** Ã¢â‚¬” non-LLM driver for ancient hosts (incl. Server 2012); DUMB v1 / CAPA v1; Python reference + .NET 4.5 irc-dumb.exe; skill /agentic-dumb.

## Constraints (from the PDF)

- Field kit, not a platform. Private Libera channel. Offline pytest only Ã¢â‚¬” do not open Libera from CI.
- Do not break existing AGPK/SEAL/protect/irc_agent behaviour unless the spec marks a compatible extension.
- Baseline at handoff: main @ 411a615 (current clone may be newer; treat as-is tests as regression suite).
- Implement in phase order Ã‚§11; phases 0Ã¢â‚¬“4 are the merge floor if .NET slips.

## Status

**Python phases 0-4:** ready for human UAT (see [mrb-2026-09-19-v2.md](./mrb-2026-09-19-v2.md)). **Phase 5 .NET clone:** present in `src/dumb_dotnet/` pending Bob MRB; **not** ready for human UAT. See [gap-vs-feature-request-2026-09-19.md](./gap-vs-feature-request-2026-09-19.md).

| Deliverable | Status |
|---|---|
| Wire CAPA/MOOT/FILE/DUMB parsers | Implemented; W1–W6 covered offline |
| Moot chair/roster/floor + skill | Implemented; 3-nick non-floor SAY drop via `handle_privmsg` |
| FILE FileBag + hash-before-`complete/` | Implemented; F1–F8 offline including AIRC-FILE v1 envelope on tier S |
| Dumb Python jail/PSK/busy/timeout | Job runner + `dumb_agent.py` listen (connect/join/flood/CAPA/jobs); D2 no result on wire; truncated spill |
| Skills + `install_skill.py` | Present (`agentic-moot` / `agentic-file` / `agentic-dumb`) |
| `.NET` `airc-dumb.exe` | net45 protocol clone (SslStream TLS 1.2, CAPA, PSK jobs, jail, D2, truncated spill). Offline `DOTNET_DUMB_EXE`. Pending Bob MRB. Not ready for human UAT. |
| Manual Libera session | `tests/MANUAL.md` only — not run by CI |

Do not claim live Server 2012 Libera from CI. Do not claim Phase 5 ready for human UAT until Bob MRB.
