<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-house-clean-fleet-docs-skills-surface-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: house-clean fleet docs, skills, and job surface

**Date:** 2026-09-21
**FR:** `docs/feature-request-house-clean-fleet-docs-skills-surface-2026-09-21.md`
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/89
**Profile:** generic
**Fuel:** picker (`cursor-models` if remaining > 0, else `grok-build`)
**Do not:** productise, force-push `main`, implement in-session as Bob, write the hostile MRB in-session.

## Work tree

Branch `work/<jobId>` off current `main`. Open a PR. Never push `main`. Never merge.

## Steps

1. Read FR #89 and `config/fleet-registry.json`. Build the canonical machine table (id, role, clone path, fuels). Edit README and `agent_readme.md` to that table only.
2. Grep `Libera`, `dev1` (as a machine id, not as prose about Form Prep), and “machine named cursor” in README, `agent_readme.md`, `.grok/skills/grok-build-fleet/SKILL.md`. Fix or alias explicitly.
3. Collapse README skill table to the map in the FR. Turn `bob-build-loop` into a stub that points at intake / dispatch / job-loop / hostile-mrb, or delete and run harvest notes so `Reinstall-AgentSkills` drops the old copy.
4. Add a Test-Pack assertion: machine ids in README + `agent_readme.md` match registry (plus any documented alias field if you add one to JSON — do not invent ids).
5. Classify `BobBridge` exports in a short list in `agent_readme.md` (agent vs tray/irc). Remove tray paint cmdlets from `grok-build-fleet` text.
6. Move or header `tools/_Watch-*.ps1`. If kept, first line states generated-by which installer. Harvest must ignore them.
7. Job audit: if outbox / completion JSON already has the fields, document the line format. If a field is missing (`prUrl`, `mrbIssue`, `fuel`, `model`), add it to the packet schema and Fake-Grok fixture. Do not add a new store.
8. Secret fixtures in Test-Pack: one refuse `export XAI_API_KEY foo`; one pass instructional mention. Do not weaken the assignment checks.
9. Docs-only GitHub protection checklist in the PR body for Bob to tick at UAT. Worker does not need org admin.

## Prove

```powershell
powershell -NoProfile -File .\tools\Test-Pack.ps1
```

Must stay off-DEV: Fake-Grok, temp `BOB_BRIDGE_HOME`, no live bots, no `%USERPROFILE%\.grok\bob-bridge`.

## Done when

- PR open with FR + plan already on the branch (this commit may already contain them; keep them).
- Test-Pack green on Fake-Grok.
- Worker comments the PR URL on issue #89 and waits for handed-off MRB.
- FAIL → new FIX PR. PASS-nits → MRB agent merges. Only Bob stamps UAT.
