<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-harvest-skills-as-pr-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: harvest as PR (#214)

FIX after MRB https://github.com/SimonBarnett/agentic_build/issues/217.

1. Edit `harvest-agent-skills` and `tools/Harvest-AgentSkills.ps1` (goal + `-Success`).
2. Point `grok-build-fleet` harvest line at the same rule.
3. Log in `docs/skill-harvest-log.md`.
4. Open PR. Do not push main. No UAT.
