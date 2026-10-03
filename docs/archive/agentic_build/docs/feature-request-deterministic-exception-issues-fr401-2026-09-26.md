<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-deterministic-exception-issues-fr401-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #401: deterministic exceptions open owning-repo issues (no LLM)

**Issue:** https://github.com/SimonBarnett/agentic_build/issues/401

`Report-BobDeterministicException` templates a GitHub issue via `gh` (Fake-Gh in tests).
Fingerprint dedupe under `~/.grok/bob-bridge/exception-issues/`. Owning repo map:
AgentMonitor / agentic_irc / gh-Jeeves / agentic_build.

Call from unexpected `catch` blocks in deterministic tools. Do not LLM-author bodies.
