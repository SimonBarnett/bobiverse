<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-mrb-merge-recycle-machines-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: agentic_build sister of irc #168

1. Read this FR + agentic_irc #168. Implement `bob-hostile-mrb` skill
   text only unless Test-Pack needs a string assert.
2. Do not edit `agentic_irc` in this job. That half is PR 169.
3. Open PR linking this issue. Do not push main. Do not live-recycle.
   No UAT.

## Checks

- `rg recycle-after-merge .grok/skills/bob-hostile-mrb/SKILL.md`
- `rg` ionos + restart in that skill.
- Test-Pack fails if the duty line is deleted.
