<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-reinstall-agentic-build-skills-2026-09-20.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: reinstall-agentic-build-skills (2026-09-20)

GitHub: https://github.com/SimonBarnett/agentic_build/issues/4

Agents need a skill to reinstall/sync `agentic_build` `.grok/skills` into `~/.grok/skills` after pull/harvest, with optional single-instance tray recycle (see MRB #3).

See issue body for triggers, steps, non-goals, and acceptance.

Implemented: `.grok/skills/reinstall-agentic-build-skills/SKILL.md` and
`tools/Reinstall-AgentSkills.ps1` (`-Pull`, `-RecycleTray`). Copy path is
`Copy-BobProjectSkills`. Recycle kills Watch-BobTray only (one STA instance).
