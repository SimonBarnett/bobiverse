<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-invite-airc.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan - invite-airc

**Spec:** docs/feature-request-invite-airc-2026-09-19.md
**Skill:** .grok/skills/invite-airc/SKILL.md

## Phases

### P0
Keep skill accurate; link from README.

### P1
`--chair` banner prints thin one-liner:
`airc-moot-thin.exe --pin <pin> --channel "#chan" --moot <id>`
plus expires note.

### P2
Offline selftest asserts banner shape.

### P3
UAT: chair on ionos, thin command on second nick or walrus; hostname smoke; MRB back to Bob.

## Kickoff
Read FR + skill + mode3-zero-config. Implement P0-P2. Commit/push. You own UAT+MRB back to Bob per standing order. Do not claim Win95. Prefer build0.1.
