# Archived repositories

This manifest records repositories superseded by `SimonBarnett/bobiverse`. Historical links remain valid; no repository was deleted.

| Repository | Archive date | Replacement in bobiverse |
|---|---|---|
| [agentic_build](https://github.com/SimonBarnett/agentic_build) | 2026-10-03 | `\\ai\\worker` (worker skills and implementation) |
| [agentic_irc](https://github.com/SimonBarnett/agentic_irc) | 2026-10-03 | all IRC skills under `airc/` and `bob/.grok/skills/bobiverse-bob-job-irc/` |
| [AgentMonitor](https://github.com/SimonBarnett/AgentMonitor) | 2026-10-03 | watcher executable under `bob/agentwatcher/` |
| [gh-Jeeves](https://github.com/SimonBarnett/gh-Jeeves) | 2026-10-03 | `\\ai\\jeeves` / `jeeves/` (all open work resolved) |
| [bob-design-uat](https://github.com/SimonBarnett/bob-design-uat) | 2026-10-03 | worker UAT skill under `bob/.grok/skills/bobiverse-bob-job-uat/` |

All five repositories were archived on 2026-10-03 (GitHub archive, reversible; each repository description now points to bobiverse): the four smaller repositories had zero open issues/PRs, and gh-Jeeves's open issue #231 and PR #239 were ported to bobiverse FRs #782 and #781, pointed back, and closed. The specifically monitored gh-Jeeves PRs #223, #225, #227, #228, #229, #232, #233, and #234 were already merged or closed and were not altered.

## Preservation

The source URLs above are intentionally retained for historical issue, PR, and provenance links. Supersession means new work belongs in bobiverse; it does not delete the source repositories or their history.

## Live-reference follow-up

**FR #795:** intake `DEFAULT_ALLOW_REPOS` (and the harvest script fallback mirror) drop the five archived repos; help examples use `bobiverse`. The live Ionos chair is still not edited by documentation or allow-list PRs — deploy when the operator chooses.

## Archived document map (FR #794)

Every document in the five archived repositories (README, docs/, specs, briefs, runbooks, templates, skills, mocks, diagrams, screenshots, PDFs, schemas) is listed below with the archived commit it was read from and where it now lives in bobiverse. Documents are ported verbatim under `docs/archive/<repo>/<original path>` with a provenance header (`SKILL.md` copies are named `SKILL.archived.md` so skill discovery never loads them). Nothing was deleted or rewritten; where a live counterpart exists it is named, FR #806 hand-merged the ten flagged "archive richer" live counterparts (honesty-box skill, README pointers, harvest log index, functional-spec, Ergo README); remaining archive text may still use pre-bobiverse paths such as `\ai\...`

| Archived repository | Commit read | Documents | Already identical in bobiverse | Ported |
|---|---|---|---|---|
| agentic_build | `12f8758` | 188 | 1 | 187 |
| agentic_irc | `b92be96` | 162 | 0 | 162 |
| AgentMonitor | `6879d8f` | 50 | 0 | 50 |
| gh-Jeeves | `4ff29b5` | 44 | 0 | 44 |
| bob-design-uat | `1acf2a3` | 50 | 0 | 50 |
| **Total** | | **494** | **1** | **493** |

Not treated as docs (stay only in the archived repos, which remain readable): `requirements.txt` (agentic_irc, gh-Jeeves), three `docs/.*probe*.txt` scratch files and `tests/fixtures/mode3/moot_join.txt` (agentic_irc), plus source code, scripts, workflows, shortcuts and config.

### agentic_build

| Archived path | Commit | Last changed | Now lives at | Live counterpart / note |
|---|---|---|---|---|
| `.github/copilot-instructions.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/.github/copilot-instructions.md` | no live counterpart |
| `.grok/skills/agent-monitor-setup/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/agent-monitor-setup/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-build-dispatch/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/bob-build-dispatch/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-build-loop/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/bob-build-loop/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-digest-webhook/SKILL.md` | `12f8758` | 2026-09-28 | `docs/archive/agentic_build/.grok/skills/bob-digest-webhook/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-fleet-monitor/SKILL.md` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/.grok/skills/bob-fleet-monitor/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-fleet-tray/SKILL.md` | `12f8758` | 2026-09-30 | `docs/archive/agentic_build/.grok/skills/bob-fleet-tray/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-git-accept/SKILL.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/.grok/skills/bob-git-accept/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-hostile-mrb/SKILL.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/.grok/skills/bob-hostile-mrb/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-irc/SKILL.md` | `12f8758` | 2026-09-29 | `docs/archive/agentic_build/.grok/skills/bob-irc/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-jeeves-chair/SKILL.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/.grok/skills/bob-jeeves-chair/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-job-loop/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/bob-job-loop/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-mrb-worker/SKILL.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/.grok/skills/bob-mrb-worker/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-repo-pair/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/bob-repo-pair/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-restart-worker-seat/SKILL.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/.grok/skills/bob-restart-worker-seat/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-shop-worker/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/bob-shop-worker/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-spec-intake/SKILL.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/.grok/skills/bob-spec-intake/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-token-handoff/SKILL.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/.grok/skills/bob-token-handoff/SKILL.archived.md` | no live counterpart |
| `.grok/skills/box-usage/SKILL.md` | `12f8758` | 2026-09-28 | `docs/archive/agentic_build/.grok/skills/box-usage/SKILL.archived.md` | no live counterpart |
| `.grok/skills/cleanup-orphans/SKILL.md` | `12f8758` | 2026-09-27 | `docs/archive/agentic_build/.grok/skills/cleanup-orphans/SKILL.archived.md` | no live counterpart |
| `.grok/skills/cursor-mrb-dev/SKILL.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/.grok/skills/cursor-mrb-dev/SKILL.archived.md` | no live counterpart |
| `.grok/skills/cursor-sand-billing/SKILL.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/.grok/skills/cursor-sand-billing/SKILL.archived.md` | no live counterpart |
| `.grok/skills/github-irc-webhooks/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/github-irc-webhooks/SKILL.archived.md` | no live counterpart |
| `.grok/skills/grok-build-fleet/SKILL.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/.grok/skills/grok-build-fleet/SKILL.archived.md` | no live counterpart |
| `.grok/skills/harvest-agent-skills/SKILL.md` | `12f8758` | 2026-09-29 | `docs/archive/agentic_build/.grok/skills/harvest-agent-skills/SKILL.archived.md` | merged into `common/.grok/skills/harvest-agent-skills/SKILL.md` by FR #806 / PR #825 |
| `.grok/skills/killproc/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/killproc/SKILL.archived.md` | no live counterpart |
| `.grok/skills/reinstall-agentic-build-skills/SKILL.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/.grok/skills/reinstall-agentic-build-skills/SKILL.archived.md` | no live counterpart |
| `.grok/skills/setup-bob-aider/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/setup-bob-aider/SKILL.archived.md` | no live counterpart |
| `.grok/skills/setup-github-cursor/SKILL.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/.grok/skills/setup-github-cursor/SKILL.archived.md` | no live counterpart |
| `.grok/skills/setup-github-webhooks/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/setup-github-webhooks/SKILL.archived.md` | no live counterpart |
| `.grok/skills/setup-remote-grok-bot/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/setup-remote-grok-bot/SKILL.archived.md` | no live counterpart |
| `.grok/skills/setup-ssl-certs/SKILL.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/.grok/skills/setup-ssl-certs/SKILL.archived.md` | no live counterpart |
| `.grok/skills/start-bob-copilot/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/start-bob-copilot/SKILL.archived.md` | no live counterpart |
| `.grok/skills/start-bob-cursor/SKILL.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/.grok/skills/start-bob-cursor/SKILL.archived.md` | no live counterpart |
| `.grok/skills/unstick-grok-bot/SKILL.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/.grok/skills/unstick-grok-bot/SKILL.archived.md` | no live counterpart |
| `.grok/skills/visionary/SKILL.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/.grok/skills/visionary/SKILL.archived.md` | live counterpart `bob/agents/plan/.grok/skills/visionary/SKILL.md`. |
| `.grok/skills/watch-agent-health/SKILL.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/.grok/skills/watch-agent-health/SKILL.archived.md` | no live counterpart |
| `.grok/skills/wix-msi-pack/SKILL.md` | `12f8758` | 2026-09-29 | `docs/archive/agentic_build/.grok/skills/wix-msi-pack/SKILL.archived.md` | no live counterpart |
| `README.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/README.md` | merged into `README.md` by FR #806 / PR #825 |
| `agent_readme.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/agent_readme.md` | no live counterpart |
| `docs/Bob_GrokBuild_Connector_Plan.pdf` | `12f8758` | 2026-09-16 | `docs/archive/agentic_build/docs/Bob_GrokBuild_Connector_Plan.pdf` | no live counterpart |
| `docs/bob-fleet-peer-peek.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/bob-fleet-peer-peek.md` | no live counterpart |
| `docs/bob-irc-agent-supervisor-fr328.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/bob-irc-agent-supervisor-fr328.md` | no live counterpart |
| `docs/bobiverse-ionos-ircd.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/bobiverse-ionos-ircd.md` | no live counterpart |
| `docs/bobiverse.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/bobiverse.md` | no live counterpart |
| `docs/build-and-test-plan-bob-fleet-tray-all-machines-2026-09-19.md` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/build-and-test-plan-bob-fleet-tray-all-machines-2026-09-19.md` | no live counterpart |
| `docs/build-and-test-plan-bob-fleet-tray-good-systray-vs-dark-card-2026-09-19.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/build-and-test-plan-bob-fleet-tray-good-systray-vs-dark-card-2026-09-19.md` | no live counterpart |
| `docs/build-and-test-plan-bob-fleet-tray-per-machine-weekly-bars-2026-09-20.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/build-and-test-plan-bob-fleet-tray-per-machine-weekly-bars-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-bob-grok-irc-listen-talk-worker-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/build-and-test-plan-bob-grok-irc-listen-talk-worker-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-bob-two-workers-2026-09-22.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/docs/build-and-test-plan-bob-two-workers-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-bobiverse-digest-feeds-systray-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/build-and-test-plan-bobiverse-digest-feeds-systray-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-bulk-close-stale-mrb-boards-2026-09-22.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/build-and-test-plan-bulk-close-stale-mrb-boards-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-digest-webhook-producer-change-only-2026-09-21.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/build-and-test-plan-digest-webhook-producer-change-only-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-dispatcher-skip-fix-leftover-fail-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/build-and-test-plan-dispatcher-skip-fix-leftover-fail-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-empty-fuel-packet-gate-2026-09-20.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/build-and-test-plan-empty-fuel-packet-gate-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-empty-packet-neither-field-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/build-and-test-plan-empty-packet-neither-field-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-ergo-windows-service-2026-09-22.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/build-and-test-plan-ergo-windows-service-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-fleet-gh-posting-readiness-2026-09-20.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/build-and-test-plan-fleet-gh-posting-readiness-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-fuel-model-compatibility-gate-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/build-and-test-plan-fuel-model-compatibility-gate-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-git-task-capacity-dispatch-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/build-and-test-plan-git-task-capacity-dispatch-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-harvest-skills-as-pr-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/build-and-test-plan-harvest-skills-as-pr-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-house-clean-fleet-docs-skills-surface-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/build-and-test-plan-house-clean-fleet-docs-skills-surface-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-mrb-loop-automation-2026-09-20.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/build-and-test-plan-mrb-loop-automation-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-mrb-merge-recycle-machines-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/build-and-test-plan-mrb-merge-recycle-machines-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-pass-nits-close-finished-boards-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/build-and-test-plan-pass-nits-close-finished-boards-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-pr-mrb-cursor-models-transaction-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/build-and-test-plan-pr-mrb-cursor-models-transaction-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-setup-remote-grok-bot-2026-09-20.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/build-and-test-plan-setup-remote-grok-bot-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-shop-channel-worker-cc-webhook-2026-09-21.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/docs/build-and-test-plan-shop-channel-worker-cc-webhook-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-shop-channel-worker-reporturl-2026-09-21.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/build-and-test-plan-shop-channel-worker-reporturl-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-systray-cursor-groups-2026-09-22.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/build-and-test-plan-systray-cursor-groups-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-systray-cursor-overspend-help-icons-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/build-and-test-plan-systray-cursor-overspend-help-icons-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-systray-restore-agent-icons-2026-09-23.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/build-and-test-plan-systray-restore-agent-icons-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-systray-start-agent-visible-tui-2026-09-23.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/build-and-test-plan-systray-start-agent-visible-tui-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-tipform-usage-polish-2026-09-23.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/build-and-test-plan-tipform-usage-polish-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-tray-agents-menu-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/build-and-test-plan-tray-agents-menu-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-tray-cursor-pools-report-fields-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/build-and-test-plan-tray-cursor-pools-report-fields-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-validate-vision-pack-intake-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/build-and-test-plan-validate-vision-pack-intake-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-watch-grok-talk-fleet-install-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/build-and-test-plan-watch-grok-talk-fleet-install-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-watch-irc-tsr-cursor-listen-2026-09-22.md` | `12f8758` | 2026-09-25 | `docs/archive/agentic_build/docs/build-and-test-plan-watch-irc-tsr-cursor-listen-2026-09-22.md` | no live counterpart |
| `docs/copilot-offload.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/copilot-offload.md` | no live counterpart |
| `docs/feature-request-automated-gate-and-module-surface-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/feature-request-automated-gate-and-module-surface-2026-09-20.md` | no live counterpart |
| `docs/feature-request-bob-fleet-tray-all-machines-2026-09-19.md` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/feature-request-bob-fleet-tray-all-machines-2026-09-19.md` | no live counterpart |
| `docs/feature-request-bob-fleet-tray-good-systray-vs-dark-card-2026-09-19.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-bob-fleet-tray-good-systray-vs-dark-card-2026-09-19.md` | no live counterpart |
| `docs/feature-request-bob-fleet-tray-per-machine-weekly-bars-2026-09-20.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-bob-fleet-tray-per-machine-weekly-bars-2026-09-20.md` | no live counterpart |
| `docs/feature-request-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md` | no live counterpart |
| `docs/feature-request-bob-grok-irc-listen-talk-worker-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-bob-grok-irc-listen-talk-worker-2026-09-21.md` | no live counterpart |
| `docs/feature-request-bob-must-call-bobiverse-webhook-diff-2026-09-22.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/feature-request-bob-must-call-bobiverse-webhook-diff-2026-09-22.md` | no live counterpart |
| `docs/feature-request-bob-systray-start-update-2026-09-27.md` | `12f8758` | 2026-09-27 | `docs/archive/agentic_build/docs/feature-request-bob-systray-start-update-2026-09-27.md` | no live counterpart |
| `docs/feature-request-bob-two-persistent-workers-2026-09-22.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/docs/feature-request-bob-two-persistent-workers-2026-09-22.md` | no live counterpart |
| `docs/feature-request-bobiverse-channel-talk-tray-pull-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-bobiverse-channel-talk-tray-pull-2026-09-21.md` | no live counterpart |
| `docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md` | no live counterpart |
| `docs/feature-request-bobiverse-quiet-talk-2026-09-20.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/feature-request-bobiverse-quiet-talk-2026-09-20.md` | no live counterpart |
| `docs/feature-request-bulk-close-stale-mrb-boards-2026-09-22.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-bulk-close-stale-mrb-boards-2026-09-22.md` | no live counterpart |
| `docs/feature-request-cursor-handoff-no-launch-contract-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/feature-request-cursor-handoff-no-launch-contract-2026-09-20.md` | no live counterpart |
| `docs/feature-request-cursor-models-spending-meter-fetch-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/feature-request-cursor-models-spending-meter-fetch-2026-09-20.md` | no live counterpart |
| `docs/feature-request-deterministic-exception-issues-fr401-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-deterministic-exception-issues-fr401-2026-09-26.md` | no live counterpart |
| `docs/feature-request-digest-cursor-pools-period-end-2026-09-28.md` | `12f8758` | 2026-09-28 | `docs/archive/agentic_build/docs/feature-request-digest-cursor-pools-period-end-2026-09-28.md` | no live counterpart |
| `docs/feature-request-digest-ingest-merge-preserve-2026-09-22.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/feature-request-digest-ingest-merge-preserve-2026-09-22.md` | no live counterpart |
| `docs/feature-request-digest-url-fr354-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-digest-url-fr354-2026-09-26.md` | no live counterpart |
| `docs/feature-request-digest-webhook-producer-change-only-2026-09-21.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/feature-request-digest-webhook-producer-change-only-2026-09-21.md` | no live counterpart |
| `docs/feature-request-digest-weekly-fr387-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-digest-weekly-fr387-2026-09-26.md` | no live counterpart |
| `docs/feature-request-dispatcher-skip-fix-leftover-fail-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/feature-request-dispatcher-skip-fix-leftover-fail-2026-09-23.md` | no live counterpart |
| `docs/feature-request-done-then-bored-keep-going-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-done-then-bored-keep-going-2026-09-26.md` | no live counterpart |
| `docs/feature-request-empty-fuel-packet-gate-2026-09-20.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-empty-fuel-packet-gate-2026-09-20.md` | no live counterpart |
| `docs/feature-request-empty-packet-neither-field-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-empty-packet-neither-field-2026-09-21.md` | no live counterpart |
| `docs/feature-request-ergo-windows-service-2026-09-22.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/feature-request-ergo-windows-service-2026-09-22.md` | no live counterpart |
| `docs/feature-request-fleet-gh-posting-readiness-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/feature-request-fleet-gh-posting-readiness-2026-09-20.md` | no live counterpart |
| `docs/feature-request-fuel-model-compatibility-gate-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/feature-request-fuel-model-compatibility-gate-2026-09-20.md` | no live counterpart |
| `docs/feature-request-git-task-capacity-dispatch-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/feature-request-git-task-capacity-dispatch-2026-09-20.md` | no live counterpart |
| `docs/feature-request-grok-fuel-mode-at-start-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-grok-fuel-mode-at-start-2026-09-26.md` | no live counterpart |
| `docs/feature-request-harvest-bob-job-dispatcher-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-harvest-bob-job-dispatcher-2026-09-21.md` | no live counterpart |
| `docs/feature-request-harvest-skills-as-pr-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/feature-request-harvest-skills-as-pr-2026-09-23.md` | no live counterpart |
| `docs/feature-request-house-clean-fleet-docs-skills-surface-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-house-clean-fleet-docs-skills-surface-2026-09-21.md` | no live counterpart |
| `docs/feature-request-jeeves-windows-service-330.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-jeeves-windows-service-330.md` | no live counterpart |
| `docs/feature-request-mrb-loop-automation-2026-09-20.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-mrb-loop-automation-2026-09-20.md` | no live counterpart |
| `docs/feature-request-mrb-merge-recycle-machines-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/feature-request-mrb-merge-recycle-machines-2026-09-23.md` | no live counterpart |
| `docs/feature-request-mrb-separate-docs-pr-fr348-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-mrb-separate-docs-pr-fr348-2026-09-26.md` | no live counterpart |
| `docs/feature-request-mrb-vision-drift-fr351-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-mrb-vision-drift-fr351-2026-09-26.md` | no live counterpart |
| `docs/feature-request-no-tokens-dialog-fr352-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-no-tokens-dialog-fr352-2026-09-26.md` | no live counterpart |
| `docs/feature-request-pass-nits-close-finished-boards-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-pass-nits-close-finished-boards-2026-09-21.md` | no live counterpart |
| `docs/feature-request-peer-transcript-cpu-fr355-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-peer-transcript-cpu-fr355-2026-09-26.md` | no live counterpart |
| `docs/feature-request-pr-mrb-cursor-models-transaction-2026-09-20.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/feature-request-pr-mrb-cursor-models-transaction-2026-09-20.md` | no live counterpart |
| `docs/feature-request-reinstall-agentic-build-skills-2026-09-20.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-reinstall-agentic-build-skills-2026-09-20.md` | no live counterpart |
| `docs/feature-request-restart-worker-seat-fr353-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-restart-worker-seat-fr353-2026-09-26.md` | no live counterpart |
| `docs/feature-request-setup-remote-grok-bot-2026-09-20.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-setup-remote-grok-bot-2026-09-20.md` | no live counterpart |
| `docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md` | no live counterpart |
| `docs/feature-request-shop-channel-worker-reporturl-2026-09-21.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/feature-request-shop-channel-worker-reporturl-2026-09-21.md` | no live counterpart |
| `docs/feature-request-systray-agent-links-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/feature-request-systray-agent-links-2026-09-23.md` | no live counterpart |
| `docs/feature-request-systray-cursor-groups-2026-09-22.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/feature-request-systray-cursor-groups-2026-09-22.md` | no live counterpart |
| `docs/feature-request-systray-cursor-overspend-help-icons-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/feature-request-systray-cursor-overspend-help-icons-2026-09-23.md` | no live counterpart |
| `docs/feature-request-systray-digest-help-2026-09-23.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-systray-digest-help-2026-09-23.md` | no live counterpart |
| `docs/feature-request-systray-restore-agent-icons-2026-09-23.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-systray-restore-agent-icons-2026-09-23.md` | no live counterpart |
| `docs/feature-request-systray-start-agent-visible-tui-2026-09-23.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-systray-start-agent-visible-tui-2026-09-23.md` | no live counterpart |
| `docs/feature-request-tipform-usage-polish-2026-09-23.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-tipform-usage-polish-2026-09-23.md` | no live counterpart |
| `docs/feature-request-tray-agents-menu-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/feature-request-tray-agents-menu-2026-09-23.md` | no live counterpart |
| `docs/feature-request-tray-cursor-pools-report-fields-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-tray-cursor-pools-report-fields-2026-09-21.md` | no live counterpart |
| `docs/feature-request-tray-cursor-rtfm-groups-2026-09-22.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/feature-request-tray-cursor-rtfm-groups-2026-09-22.md` | no live counterpart |
| `docs/feature-request-tray-overspend-local-am150-2026-09-27.md` | `12f8758` | 2026-09-27 | `docs/archive/agentic_build/docs/feature-request-tray-overspend-local-am150-2026-09-27.md` | no live counterpart |
| `docs/feature-request-tray-seat-cwd-fr369-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-tray-seat-cwd-fr369-2026-09-26.md` | no live counterpart |
| `docs/feature-request-utf8-no-bom-fr347-2026-09-26.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/feature-request-utf8-no-bom-fr347-2026-09-26.md` | no live counterpart |
| `docs/feature-request-validate-vision-pack-intake-2026-09-23.md` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/feature-request-validate-vision-pack-intake-2026-09-23.md` | no live counterpart |
| `docs/feature-request-watch-grok-talk-fleet-install-2026-09-21.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/feature-request-watch-grok-talk-fleet-install-2026-09-21.md` | no live counterpart |
| `docs/feature-request-watch-irc-tsr-cursor-listen-2026-09-22.md` | `12f8758` | 2026-09-22 | `docs/archive/agentic_build/docs/feature-request-watch-irc-tsr-cursor-listen-2026-09-22.md` | no live counterpart |
| `docs/fr-mode-no-self-merge.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/fr-mode-no-self-merge.md` | no live counterpart |
| `docs/github-main-protection-checklist.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/github-main-protection-checklist.md` | no live counterpart |
| `docs/grok-talk-envelope-v1.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/grok-talk-envelope-v1.md` | no live counterpart |
| `docs/ionos-ops-2026-09-19.md` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/ionos-ops-2026-09-19.md` | no live counterpart |
| `docs/job-audit-line.md` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/docs/job-audit-line.md` | no live counterpart |
| `docs/mocks/bob-systray/empty.html` | `12f8758` | 2026-09-27 | `docs/archive/agentic_build/docs/mocks/bob-systray/empty.html` | live counterpart `jeeves/docs/mocks/empty.html`. |
| `docs/mocks/bob-systray/error.html` | `12f8758` | 2026-09-27 | `docs/archive/agentic_build/docs/mocks/bob-systray/error.html` | live counterpart `jeeves/docs/mocks/error.html`. |
| `docs/mocks/bob-systray/home.html` | `12f8758` | 2026-09-27 | `docs/archive/agentic_build/docs/mocks/bob-systray/home.html` | live counterpart `jeeves/docs/mocks/home.html`. |
| `docs/mocks/empty.html` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/mocks/empty.html` | live counterpart `jeeves/docs/mocks/empty.html`. |
| `docs/mocks/error.html` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/mocks/error.html` | live counterpart `jeeves/docs/mocks/error.html`. |
| `docs/mocks/home.html` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/mocks/home.html` | live counterpart `jeeves/docs/mocks/home.html`. |
| `docs/mocks/mrb-merge-recycle/empty.html` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/mocks/mrb-merge-recycle/empty.html` | live counterpart `jeeves/docs/mocks/empty.html`. |
| `docs/mocks/mrb-merge-recycle/error.html` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/mocks/mrb-merge-recycle/error.html` | live counterpart `jeeves/docs/mocks/error.html`. |
| `docs/mocks/mrb-merge-recycle/home.html` | `12f8758` | 2026-09-23 | `docs/archive/agentic_build/docs/mocks/mrb-merge-recycle/home.html` | live counterpart `jeeves/docs/mocks/home.html`. |
| `docs/mrb-bob-fleet-double-dialog-stale-list-2026-09-20.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/mrb-bob-fleet-double-dialog-stale-list-2026-09-20.md` | no live counterpart |
| `docs/mrb-bob-fleet-tray-2026-09-19.md` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/mrb-bob-fleet-tray-2026-09-19.md` | no live counterpart |
| `docs/mrb-bob-fleet-tray-2026-09-19.pdf` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/mrb-bob-fleet-tray-2026-09-19.pdf` | no live counterpart |
| `docs/mrb-bob-fleet-tray-follow-cursor-2026-09-19.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/mrb-bob-fleet-tray-follow-cursor-2026-09-19.md` | no live counterpart |
| `docs/mrb-bob-fleet-tray-follow-cursor-retest-2026-09-19.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/mrb-bob-fleet-tray-follow-cursor-retest-2026-09-19.md` | no live counterpart |
| `docs/mrb-bob-fleet-tray-no-dialog-2026-09-19.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/mrb-bob-fleet-tray-no-dialog-2026-09-19.md` | no live counterpart |
| `docs/mrb-bob-fleet-tray-no-dialog-retest-2026-09-19.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/mrb-bob-fleet-tray-no-dialog-retest-2026-09-19.md` | no live counterpart |
| `docs/mrb-bob-fleet-tray-retest-2026-09-19.md` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/mrb-bob-fleet-tray-retest-2026-09-19.md` | no live counterpart |
| `docs/mrb-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/mrb-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md` | no live counterpart |
| `docs/mrb-bob-fleet-tray-weekly-machine-tiles-2026-09-19.pdf` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/mrb-bob-fleet-tray-weekly-machine-tiles-2026-09-19.pdf` | no live counterpart |
| `docs/mrb.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/mrb.md` | no live counterpart |
| `docs/screenshots/bob-fleet-double-dialog-stale-list-2026-09-20.png` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/screenshots/bob-fleet-double-dialog-stale-list-2026-09-20.png` | no live counterpart |
| `docs/screenshots/bob-fleet-native-p-plus-idle-chip-2026-09-20.png` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/screenshots/bob-fleet-native-p-plus-idle-chip-2026-09-20.png` | no live counterpart |
| `docs/screenshots/bob-fleet-tray-crap-card-over-good-tip-1.png` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/screenshots/bob-fleet-tray-crap-card-over-good-tip-1.png` | no live counterpart |
| `docs/screenshots/bob-fleet-tray-crap-card-over-good-tip-2.png` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/screenshots/bob-fleet-tray-crap-card-over-good-tip-2.png` | no live counterpart |
| `docs/screenshots/bob-fleet-tray-single-bar-bogus-unreachable-2026-09-20.png` | `12f8758` | 2026-09-20 | `docs/archive/agentic_build/docs/screenshots/bob-fleet-tray-single-bar-bogus-unreachable-2026-09-20.png` | no live counterpart |
| `docs/skill-harvest-log.md` | `12f8758` | 2026-09-29 | `docs/archive/agentic_build/docs/skill-harvest-log.md` | merged into `common/docs/skill-harvest-log.md` by FR #806 / PR #825 |
| `docs/smoke-systray-session-api-key-and-plan-2026-09-24.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/smoke-systray-session-api-key-and-plan-2026-09-24.md` | no live counterpart |
| `docs/templates/vision.md` | `12f8758` | 2026-09-23 | `bob/agents/plan/docs/templates/vision.md` (already present) | identical copy already in bobiverse |
| `docs/test-pack-no-live-irc-fr329.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/test-pack-no-live-irc-fr329.md` | no live counterpart |
| `docs/uat-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/docs/uat-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md` | no live counterpart |
| `docs/utf8-no-bom.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/utf8-no-bom.md` | no live counterpart |
| `docs/worker-pack-fr-mode.md` | `12f8758` | 2026-09-26 | `docs/archive/agentic_build/docs/worker-pack-fr-mode.md` | no live counterpart |
| `docs/wp0-recon.md` | `12f8758` | 2026-09-16 | `docs/archive/agentic_build/docs/wp0-recon.md` | no live counterpart |
| `schemas/completion.schema.json` | `12f8758` | 2026-09-16 | `docs/archive/agentic_build/schemas/completion.schema.json` | no live counterpart |
| `schemas/health.schema.json` | `12f8758` | 2026-09-19 | `docs/archive/agentic_build/schemas/health.schema.json` | no live counterpart |
| `schemas/overlay.schema.json` | `12f8758` | 2026-09-18 | `docs/archive/agentic_build/schemas/overlay.schema.json` | no live counterpart |
| `schemas/prompt-packet.schema.json` | `12f8758` | 2026-09-21 | `docs/archive/agentic_build/schemas/prompt-packet.schema.json` | no live counterpart |
| `schemas/status.schema.json` | `12f8758` | 2026-09-18 | `docs/archive/agentic_build/schemas/status.schema.json` | no live counterpart |
| `tests/last-dev-run.md` | `12f8758` | 2026-09-16 | `docs/archive/agentic_build/tests/last-dev-run.md` | no live counterpart |
| `tools/Watch-AgentHealth/README.md` | `12f8758` | 2026-09-24 | `docs/archive/agentic_build/tools/Watch-AgentHealth/README.md` | live counterpart `README.md`. |

### agentic_irc

| Archived path | Commit | Last changed | Now lives at | Live counterpart / note |
|---|---|---|---|---|
| `.grok/skills/agentic-dumb/SKILL.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/.grok/skills/agentic-dumb/SKILL.archived.md` | no live counterpart |
| `.grok/skills/agentic-file/SKILL.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/.grok/skills/agentic-file/SKILL.archived.md` | no live counterpart |
| `.grok/skills/agentic-irc/SKILL.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/.grok/skills/agentic-irc/SKILL.archived.md` | no live counterpart |
| `.grok/skills/agentic-moot/SKILL.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/.grok/skills/agentic-moot/SKILL.archived.md` | no live counterpart |
| `.grok/skills/airc-console/SKILL.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/.grok/skills/airc-console/SKILL.archived.md` | no live counterpart |
| `.grok/skills/bob-irc/SKILL.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/.grok/skills/bob-irc/SKILL.archived.md` | no live counterpart |
| `.grok/skills/connect-bobiverse/SKILL.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/.grok/skills/connect-bobiverse/SKILL.archived.md` | no live counterpart |
| `.grok/skills/harvest-agent-skills/SKILL.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/.grok/skills/harvest-agent-skills/SKILL.archived.md` | merged into `common/.grok/skills/harvest-agent-skills/SKILL.md` by FR #806 / PR #825 |
| `.grok/skills/invite-airc/SKILL.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/.grok/skills/invite-airc/SKILL.archived.md` | no live counterpart |
| `.grok/skills/jeeves-git-webhook/SKILL.md` | `b92be96` | 2026-09-26 | `docs/archive/agentic_irc/.grok/skills/jeeves-git-webhook/SKILL.archived.md` | no live counterpart |
| `README.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/README.md` | live counterpart `README.md`. |
| `config/README.txt` | `b92be96` | 2026-09-28 | `docs/archive/agentic_irc/config/README.txt` | merged into `common/third_party/ergo/README.txt` by FR #806 / PR #825 |
| `docs/README.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/docs/README.md` | live counterpart `README.md`. |
| `docs/airc-console-domain-lobby.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/docs/airc-console-domain-lobby.md` | no live counterpart |
| `docs/airc-console-fr253.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/docs/airc-console-fr253.md` | no live counterpart |
| `docs/beacon-v1-2026-09-19.md` | `b92be96` | 2026-09-20 | `docs/archive/agentic_irc/docs/beacon-v1-2026-09-19.md` | no live counterpart |
| `docs/bob-report-callback-change-only.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/bob-report-callback-change-only.md` | no live counterpart |
| `docs/bob-stamp-invite-airc-ready-human-uat-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/bob-stamp-invite-airc-ready-human-uat-2026-09-19.md` | no live counterpart |
| `docs/bobiverse-ionos-ircd.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/docs/bobiverse-ionos-ircd.md` | no live counterpart |
| `docs/build-and-test-plan-bob-grok-irc-listen-talk-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/build-and-test-plan-bob-grok-irc-listen-talk-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-bob-listen-talk-all-seats-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/build-and-test-plan-bob-listen-talk-all-seats-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-bobiverse-digest-feeds-systray-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/build-and-test-plan-bobiverse-digest-feeds-systray-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-bobiverse-only-bobs-shop-auto-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-bobiverse-only-bobs-shop-auto-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-bobs-must-bobiverse-webhook-delta-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-bobs-must-bobiverse-webhook-delta-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-bobstat-2026-09-20.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/build-and-test-plan-bobstat-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-bobstat-point-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/build-and-test-plan-bobstat-point-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-digest-cursor-pools-cursor-only-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-digest-cursor-pools-cursor-only-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-digest-webhook-chair-change-only-2026-09-21.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/build-and-test-plan-digest-webhook-chair-change-only-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-git-webhook-jeeves-announce-2026-09-23.md` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/build-and-test-plan-git-webhook-jeeves-announce-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-health-check-tsr-session-id-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-health-check-tsr-session-id-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-house-clean-irc-kit-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/build-and-test-plan-house-clean-irc-kit-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-invite-airc.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/build-and-test-plan-invite-airc.md` | no live counterpart |
| `docs/build-and-test-plan-ionos-shop-channel-bob-ionos-2026-09-21.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-ionos-shop-channel-bob-ionos-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-irc-coordinator-listener-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/build-and-test-plan-irc-coordinator-listener-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-irc-is-a-mess-2026-09-23.md` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/build-and-test-plan-irc-is-a-mess-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-irc-multi-agent-registration-2026-09-20.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/build-and-test-plan-irc-multi-agent-registration-2026-09-20.md` | no live counterpart |
| `docs/build-and-test-plan-jeeves-recycle-command-2026-09-23.md` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/build-and-test-plan-jeeves-recycle-command-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-machine-channel-bobosphere-bobs-only-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-machine-channel-bobosphere-bobs-only-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-mode3-dumb-bobiverse-align-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-mode3-dumb-bobiverse-align-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-mode3-dumb-exec-ergonomics-2026-09-19.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/build-and-test-plan-mode3-dumb-exec-ergonomics-2026-09-19.md` | no live counterpart |
| `docs/build-and-test-plan-mode3.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/build-and-test-plan-mode3.md` | no live counterpart |
| `docs/build-and-test-plan-mrb-merge-recycle-machines-2026-09-23.md` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/build-and-test-plan-mrb-merge-recycle-machines-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-offline-nicks-stay-in-chat-users-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-offline-nicks-stay-in-chat-users-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-reply-same-call-channel-2026-09-23.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/build-and-test-plan-reply-same-call-channel-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-report-bobiverse-digest-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/build-and-test-plan-report-bobiverse-digest-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-shop-channel-worker-cc-webhook-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/build-and-test-plan-shop-channel-worker-cc-webhook-2026-09-21.md` | no live counterpart |
| `docs/build-and-test-plan-talk-seat-agent-pid-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-talk-seat-agent-pid-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-talk-seat-agent-pid-align-2026-09-22.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/build-and-test-plan-talk-seat-agent-pid-align-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-talk-seat-survival-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-talk-seat-survival-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-talk-seats-back-bobiverse-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-talk-seats-back-bobiverse-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-team-channel-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-team-channel-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-visible-nicks-umode-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/build-and-test-plan-visible-nicks-umode-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan-watch-agent-health-aider-2026-09-24.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/build-and-test-plan-watch-agent-health-aider-2026-09-24.md` | no live counterpart |
| `docs/build-and-test-plan.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/build-and-test-plan.md` | no live counterpart |
| `docs/dumb-service-fr236.md` | `b92be96` | 2026-09-26 | `docs/archive/agentic_irc/docs/dumb-service-fr236.md` | no live counterpart |
| `docs/ergo-chanserv-enable-bob-shops.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/docs/ergo-chanserv-enable-bob-shops.md` | no live counterpart |
| `docs/evidence/ce-priority-dev1-watch-written-remaining.json` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/evidence/ce-priority-dev1-watch-written-remaining.json` | no live counterpart |
| `docs/evidence/issue-128-offline-nick-drop-notes.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/evidence/issue-128-offline-nick-drop-notes.md` | no live counterpart |
| `docs/evidence/issue-140-offline-nick-fix-evidence.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/evidence/issue-140-offline-nick-fix-evidence.md` | no live counterpart |
| `docs/feature-request-airc-console-workgroup-lobby-2026-09-29.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/docs/feature-request-airc-console-workgroup-lobby-2026-09-29.md` | no live counterpart |
| `docs/feature-request-bob-chanserv-register-shop-2026-09-29.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/docs/feature-request-bob-chanserv-register-shop-2026-09-29.md` | no live counterpart |
| `docs/feature-request-bob-grok-irc-listen-talk-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-bob-grok-irc-listen-talk-2026-09-21.md` | no live counterpart |
| `docs/feature-request-bob-listen-talk-all-seats-2026-09-21.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/feature-request-bob-listen-talk-all-seats-2026-09-21.md` | no live counterpart |
| `docs/feature-request-bobiverse-channel-talk-tray-pull-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-bobiverse-channel-talk-tray-pull-2026-09-21.md` | no live counterpart |
| `docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md` | no live counterpart |
| `docs/feature-request-bobiverse-only-bobs-shop-auto-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-bobiverse-only-bobs-shop-auto-2026-09-22.md` | no live counterpart |
| `docs/feature-request-bobiverse-quiet-talk-2026-09-20.md` | `b92be96` | 2026-09-20 | `docs/archive/agentic_irc/docs/feature-request-bobiverse-quiet-talk-2026-09-20.md` | no live counterpart |
| `docs/feature-request-bobs-call-bobiverse-webhook-delta-2026-09-22.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/feature-request-bobs-call-bobiverse-webhook-delta-2026-09-22.md` | no live counterpart |
| `docs/feature-request-bobs-must-bobiverse-webhook-delta-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-bobs-must-bobiverse-webhook-delta-2026-09-22.md` | no live counterpart |
| `docs/feature-request-bobstat-2026-09-20.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-bobstat-2026-09-20.md` | no live counterpart |
| `docs/feature-request-bobstat-point-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-bobstat-point-2026-09-21.md` | no live counterpart |
| `docs/feature-request-digest-bob-url-2026-09-23.md` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/feature-request-digest-bob-url-2026-09-23.md` | no live counterpart |
| `docs/feature-request-digest-cursor-pools-cursor-only-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-digest-cursor-pools-cursor-only-2026-09-22.md` | no live counterpart |
| `docs/feature-request-digest-webhook-chair-change-only-2026-09-21.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/feature-request-digest-webhook-chair-change-only-2026-09-21.md` | no live counterpart |
| `docs/feature-request-fresh-talk-seat-fr237-2026-09-26.md` | `b92be96` | 2026-09-26 | `docs/archive/agentic_irc/docs/feature-request-fresh-talk-seat-fr237-2026-09-26.md` | no live counterpart |
| `docs/feature-request-from-account-filter-fr230-2026-09-26.md` | `b92be96` | 2026-09-26 | `docs/archive/agentic_irc/docs/feature-request-from-account-filter-fr230-2026-09-26.md` | no live counterpart |
| `docs/feature-request-git-webhook-jeeves-announce-2026-09-23.md` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/feature-request-git-webhook-jeeves-announce-2026-09-23.md` | no live counterpart |
| `docs/feature-request-health-check-tsr-session-id-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-health-check-tsr-session-id-2026-09-22.md` | no live counterpart |
| `docs/feature-request-house-clean-irc-kit-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-house-clean-irc-kit-2026-09-21.md` | no live counterpart |
| `docs/feature-request-invite-airc-2026-09-19.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/feature-request-invite-airc-2026-09-19.md` | no live counterpart |
| `docs/feature-request-ionos-shop-channel-bob-ionos-2026-09-21.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-ionos-shop-channel-bob-ionos-2026-09-21.md` | no live counterpart |
| `docs/feature-request-irc-coordinator-listener-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-irc-coordinator-listener-2026-09-21.md` | no live counterpart |
| `docs/feature-request-irc-is-a-mess-2026-09-23.md` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/feature-request-irc-is-a-mess-2026-09-23.md` | no live counterpart |
| `docs/feature-request-irc-multi-agent-registration-2026-09-20.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/feature-request-irc-multi-agent-registration-2026-09-20.md` | no live counterpart |
| `docs/feature-request-jeeves-recycle-command-2026-09-23.md` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/feature-request-jeeves-recycle-command-2026-09-23.md` | no live counterpart |
| `docs/feature-request-machine-channel-bobosphere-bobs-only-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-machine-channel-bobosphere-bobs-only-2026-09-22.md` | no live counterpart |
| `docs/feature-request-mode3-dumb-bobiverse-align-2026-09-22.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/feature-request-mode3-dumb-bobiverse-align-2026-09-22.md` | no live counterpart |
| `docs/feature-request-mode3-dumb-exec-ergonomics-2026-09-19.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/feature-request-mode3-dumb-exec-ergonomics-2026-09-19.md` | no live counterpart |
| `docs/feature-request-mode3-visibility-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-mode3-visibility-2026-09-21.md` | no live counterpart |
| `docs/feature-request-mode3-win95-thin-moot-cli-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/feature-request-mode3-win95-thin-moot-cli-2026-09-19.md` | no live counterpart |
| `docs/feature-request-mode3-win95-thin-moot-cli-2026-09-19.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/feature-request-mode3-win95-thin-moot-cli-2026-09-19.pdf` | no live counterpart |
| `docs/feature-request-moot-file-dumb-2026-09-19.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/feature-request-moot-file-dumb-2026-09-19.md` | no live counterpart |
| `docs/feature-request-moot-file-dumb-2026-09-19.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/feature-request-moot-file-dumb-2026-09-19.pdf` | no live counterpart |
| `docs/feature-request-mrb-merge-recycle-machines-2026-09-23.md` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/feature-request-mrb-merge-recycle-machines-2026-09-23.md` | no live counterpart |
| `docs/feature-request-offline-nicks-stay-in-chat-users-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-offline-nicks-stay-in-chat-users-2026-09-22.md` | no live counterpart |
| `docs/feature-request-reply-same-call-channel-2026-09-23.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/feature-request-reply-same-call-channel-2026-09-23.md` | no live counterpart |
| `docs/feature-request-report-bobiverse-digest-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-report-bobiverse-digest-2026-09-21.md` | no live counterpart |
| `docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md` | no live counterpart |
| `docs/feature-request-shop-working-on-with-webhook-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-shop-working-on-with-webhook-2026-09-22.md` | no live counterpart |
| `docs/feature-request-talk-seat-agent-pid-2026-09-22.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/feature-request-talk-seat-agent-pid-2026-09-22.md` | no live counterpart |
| `docs/feature-request-talk-seat-agent-pid-align-2026-09-22.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/feature-request-talk-seat-agent-pid-align-2026-09-22.md` | no live counterpart |
| `docs/feature-request-talk-seat-survival-2026-09-22.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/feature-request-talk-seat-survival-2026-09-22.md` | no live counterpart |
| `docs/feature-request-talk-seats-back-bobiverse-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-talk-seats-back-bobiverse-2026-09-22.md` | no live counterpart |
| `docs/feature-request-team-channel-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-team-channel-2026-09-22.md` | no live counterpart |
| `docs/feature-request-visible-nicks-umode-2026-09-22.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/feature-request-visible-nicks-umode-2026-09-22.md` | no live counterpart |
| `docs/fr2-acceptance-checklist-2026-09-20.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/fr2-acceptance-checklist-2026-09-20.md` | no live counterpart |
| `docs/gap-vs-feature-request-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/gap-vs-feature-request-2026-09-19.md` | no live counterpart |
| `docs/grok-talk-envelope-v1.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/grok-talk-envelope-v1.md` | no live counterpart |
| `docs/invite-airc-uat-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/invite-airc-uat-2026-09-19.md` | no live counterpart |
| `docs/ionos-multi-agent-registration-notes-2026-09-20.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/ionos-multi-agent-registration-notes-2026-09-20.md` | no live counterpart |
| `docs/mocks/empty.html` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/mocks/empty.html` | live counterpart `jeeves/docs/mocks/empty.html`. |
| `docs/mocks/error.html` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/mocks/error.html` | live counterpart `jeeves/docs/mocks/error.html`. |
| `docs/mocks/home.html` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/mocks/home.html` | live counterpart `jeeves/docs/mocks/home.html`. |
| `docs/mocks/mrb-merge-recycle/empty.html` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/mocks/mrb-merge-recycle/empty.html` | live counterpart `jeeves/docs/mocks/empty.html`. |
| `docs/mocks/mrb-merge-recycle/error.html` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/mocks/mrb-merge-recycle/error.html` | live counterpart `jeeves/docs/mocks/error.html`. |
| `docs/mocks/mrb-merge-recycle/home.html` | `b92be96` | 2026-09-23 | `docs/archive/agentic_irc/docs/mocks/mrb-merge-recycle/home.html` | live counterpart `jeeves/docs/mocks/home.html`. |
| `docs/mode3-dumb-ops.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/mode3-dumb-ops.md` | no live counterpart |
| `docs/mode3-live-smoke-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mode3-live-smoke-2026-09-19.md` | no live counterpart |
| `docs/mode3-os-matrix.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/mode3-os-matrix.md` | no live counterpart |
| `docs/mode3-release.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mode3-release.md` | no live counterpart |
| `docs/mode3-tls-spike.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/mode3-tls-spike.md` | no live counterpart |
| `docs/mode3-zero-config-2026-09-19.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/docs/mode3-zero-config-2026-09-19.md` | no live counterpart |
| `docs/mrb-2026-09-19-v1.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-2026-09-19-v1.md` | no live counterpart |
| `docs/mrb-2026-09-19-v1.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-2026-09-19-v1.pdf` | no live counterpart |
| `docs/mrb-2026-09-19-v2.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-2026-09-19-v2.md` | no live counterpart |
| `docs/mrb-2026-09-19-v2.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-2026-09-19-v2.pdf` | no live counterpart |
| `docs/mrb-invite-airc-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-invite-airc-2026-09-19.md` | no live counterpart |
| `docs/mrb-invite-airc-2026-09-19.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-invite-airc-2026-09-19.pdf` | no live counterpart |
| `docs/mrb-mode1-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode1-2026-09-19.md` | no live counterpart |
| `docs/mrb-mode1-2026-09-19.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode1-2026-09-19.pdf` | no live counterpart |
| `docs/mrb-mode2-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode2-2026-09-19.md` | no live counterpart |
| `docs/mrb-mode2-2026-09-19.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode2-2026-09-19.pdf` | no live counterpart |
| `docs/mrb-mode2-fix-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode2-fix-2026-09-19.md` | no live counterpart |
| `docs/mrb-mode2-fix-2026-09-19.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode2-fix-2026-09-19.pdf` | no live counterpart |
| `docs/mrb-mode2-retest-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode2-retest-2026-09-19.md` | no live counterpart |
| `docs/mrb-mode2-retest-2026-09-19.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode2-retest-2026-09-19.pdf` | no live counterpart |
| `docs/mrb-mode3-2026-09-19.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode3-2026-09-19.md` | no live counterpart |
| `docs/mrb-mode3-2026-09-19.pdf` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/docs/mrb-mode3-2026-09-19.pdf` | no live counterpart |
| `docs/mrb-mode3-a5-retest-2026-09-19.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/mrb-mode3-a5-retest-2026-09-19.md` | no live counterpart |
| `docs/mrb-mode3-zero-config-2026-09-19.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/mrb-mode3-zero-config-2026-09-19.md` | no live counterpart |
| `docs/mrb-mode3-zero-config-retest-2026-09-19.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/mrb-mode3-zero-config-retest-2026-09-19.md` | no live counterpart |
| `docs/mrb-wp-p5-dotnet-2026-09-19.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/mrb-wp-p5-dotnet-2026-09-19.md` | no live counterpart |
| `docs/multi-agent-one-host.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/multi-agent-one-host.md` | no live counterpart |
| `docs/post-merge-talk-seat-pid-restart.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/post-merge-talk-seat-pid-restart.md` | no live counterpart |
| `docs/prior-irc-clean.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/prior-irc-clean.md` | no live counterpart |
| `docs/retire-ear-bored-offer-fr233.md` | `b92be96` | 2026-09-26 | `docs/archive/agentic_irc/docs/retire-ear-bored-offer-fr233.md` | no live counterpart |
| `docs/skill-harvest-log.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/docs/skill-harvest-log.md` | merged into `common/docs/skill-harvest-log.md` by FR #806 / PR #825 |
| `docs/start-irc-pair-fr238.md` | `b92be96` | 2026-09-26 | `docs/archive/agentic_irc/docs/start-irc-pair-fr238.md` | no live counterpart |
| `docs/start-talkseat-fresh-home-fr237.md` | `b92be96` | 2026-09-26 | `docs/archive/agentic_irc/docs/start-talkseat-fresh-home-fr237.md` | no live counterpart |
| `docs/tofu-rotation.md` | `b92be96` | 2026-09-21 | `docs/archive/agentic_irc/docs/tofu-rotation.md` | no live counterpart |
| `docs/watch-agent-health-aider.md` | `b92be96` | 2026-09-24 | `docs/archive/agentic_irc/docs/watch-agent-health-aider.md` | no live counterpart |
| `docs/windows-task-scheduler-irc-pair-gotchas-fr231.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/docs/windows-task-scheduler-irc-pair-gotchas-fr231.md` | no live counterpart |
| `docs/worker-channel-only.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/worker-channel-only.md` | no live counterpart |
| `docs/wp-backlog-full-irc-2026-09-19.md` | `b92be96` | 2026-09-25 | `docs/archive/agentic_irc/docs/wp-backlog-full-irc-2026-09-19.md` | no live counterpart |
| `scripts/bootstrap-second-seat-dev1.txt` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/scripts/bootstrap-second-seat-dev1.txt` | no live counterpart |
| `scripts/bootstrap-second-seat.txt` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/scripts/bootstrap-second-seat.txt` | no live counterpart |
| `src/airc_console/README.md` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/src/airc_console/README.md` | live counterpart `README.md`. |
| `src/dumb_dotnet/README.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/src/dumb_dotnet/README.md` | live counterpart `README.md`. |
| `src/moot_thin/README.md` | `b92be96` | 2026-09-22 | `docs/archive/agentic_irc/src/moot_thin/README.md` | live counterpart `README.md`. |
| `tests/MANUAL.md` | `b92be96` | 2026-09-19 | `docs/archive/agentic_irc/tests/MANUAL.md` | no live counterpart |
| `third_party/nssm/README.txt` | `b92be96` | 2026-09-28 | `docs/archive/agentic_irc/third_party/nssm/README.txt` | live counterpart `common/third_party/nssm/README.txt`. |
| `third_party/wix/README.txt` | `b92be96` | 2026-09-29 | `docs/archive/agentic_irc/third_party/wix/README.txt` | live counterpart `common/third_party/ergo/README.txt`. |

### AgentMonitor

| Archived path | Commit | Last changed | Now lives at | Live counterpart / note |
|---|---|---|---|---|
| `.cursor/skills/agent-monitor/SKILL.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/.cursor/skills/agent-monitor/SKILL.archived.md` | no live counterpart |
| `.cursor/skills/watch-seat/SKILL.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/.cursor/skills/watch-seat/SKILL.archived.md` | no live counterpart |
| `.grok/skills/agent-monitor/SKILL.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/.grok/skills/agent-monitor/SKILL.archived.md` | no live counterpart |
| `.grok/skills/watch-seat/SKILL.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/.grok/skills/watch-seat/SKILL.archived.md` | no live counterpart |
| `README.md` | `6879d8f` | 2026-09-27 | `docs/archive/AgentMonitor/README.md` | live counterpart `README.md`. |
| `docs/build-and-test-plan-auto-pong-bare-ping-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-auto-pong-bare-ping-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-composer-tui-launch-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-composer-tui-launch-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-document-agentmonitor-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-document-agentmonitor-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-lnk-target-cmd-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-lnk-target-cmd-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-no-tui-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-no-tui-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-orphan-python-node-on-start-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-orphan-python-node-on-start-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-partial-irc-log-line-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-partial-irc-log-line-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-ping-me-from-filter-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-ping-me-from-filter-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-root-exit-teardown-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/build-and-test-plan-root-exit-teardown-2026-09-26.md` | no live counterpart |
| `docs/build-and-test-plan-run-hidden-vbs-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-run-hidden-vbs-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-shortcut-hidden-background-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-shortcut-hidden-background-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-shortcut-windows-on-off-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-shortcut-windows-on-off-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-shortcuts-not-empty-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-shortcuts-not-empty-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-stale-cursor-nodes-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-stale-cursor-nodes-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-tui-exit-irc-quit-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-tui-exit-irc-quit-2026-09-23.md` | no live counterpart |
| `docs/build-and-test-plan-utf8-irc-forward-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/build-and-test-plan-utf8-irc-forward-2026-09-23.md` | no live counterpart |
| `docs/feature-request-ack-bare-outbox-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/feature-request-ack-bare-outbox-2026-09-26.md` | no live counterpart |
| `docs/feature-request-auto-pong-bare-ping-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-auto-pong-bare-ping-2026-09-23.md` | no live counterpart |
| `docs/feature-request-composer-tui-launch-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-composer-tui-launch-2026-09-23.md` | no live counterpart |
| `docs/feature-request-document-agentmonitor-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-document-agentmonitor-2026-09-23.md` | no live counterpart |
| `docs/feature-request-done-then-bored-keep-going-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/feature-request-done-then-bored-keep-going-2026-09-26.md` | no live counterpart |
| `docs/feature-request-forward-archive-access-denied-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/feature-request-forward-archive-access-denied-2026-09-26.md` | no live counterpart |
| `docs/feature-request-irc-health-log-and-agent-field-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/feature-request-irc-health-log-and-agent-field-2026-09-26.md` | no live counterpart |
| `docs/feature-request-lnk-target-cmd-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-lnk-target-cmd-2026-09-23.md` | no live counterpart |
| `docs/feature-request-monitor-adopt-live-agent-2026-09-25.md` | `6879d8f` | 2026-09-25 | `docs/archive/AgentMonitor/docs/feature-request-monitor-adopt-live-agent-2026-09-25.md` | no live counterpart |
| `docs/feature-request-no-tui-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-no-tui-2026-09-23.md` | no live counterpart |
| `docs/feature-request-orphan-python-node-on-start-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-orphan-python-node-on-start-2026-09-23.md` | no live counterpart |
| `docs/feature-request-partial-irc-log-line-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-partial-irc-log-line-2026-09-23.md` | no live counterpart |
| `docs/feature-request-ping-me-from-filter-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-ping-me-from-filter-2026-09-23.md` | no live counterpart |
| `docs/feature-request-ps51-home-readonly-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/feature-request-ps51-home-readonly-2026-09-26.md` | no live counterpart |
| `docs/feature-request-report-watch-exception-fr131-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/feature-request-report-watch-exception-fr131-2026-09-26.md` | no live counterpart |
| `docs/feature-request-root-exit-teardown-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/feature-request-root-exit-teardown-2026-09-26.md` | no live counterpart |
| `docs/feature-request-run-hidden-vbs-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-run-hidden-vbs-2026-09-23.md` | no live counterpart |
| `docs/feature-request-seat-ended-dead-pid-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/feature-request-seat-ended-dead-pid-2026-09-26.md` | no live counterpart |
| `docs/feature-request-shortcut-hidden-background-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-shortcut-hidden-background-2026-09-23.md` | no live counterpart |
| `docs/feature-request-shortcut-windows-on-off-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-shortcut-windows-on-off-2026-09-23.md` | no live counterpart |
| `docs/feature-request-shortcuts-not-empty-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-shortcuts-not-empty-2026-09-23.md` | no live counterpart |
| `docs/feature-request-stale-cursor-nodes-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-stale-cursor-nodes-2026-09-23.md` | no live counterpart |
| `docs/feature-request-supervisor-idle-nudge-fr149-2026-09-27.md` | `6879d8f` | 2026-09-27 | `docs/archive/AgentMonitor/docs/feature-request-supervisor-idle-nudge-fr149-2026-09-27.md` | no live counterpart |
| `docs/feature-request-tui-exit-irc-quit-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-tui-exit-irc-quit-2026-09-23.md` | no live counterpart |
| `docs/feature-request-utf8-irc-forward-2026-09-23.md` | `6879d8f` | 2026-09-23 | `docs/archive/AgentMonitor/docs/feature-request-utf8-irc-forward-2026-09-23.md` | no live counterpart |
| `docs/feature-request-watch-agent-watcher-2026-09-26.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/feature-request-watch-agent-watcher-2026-09-26.md` | no live counterpart |
| `docs/monitor-reload-fr89.md` | `6879d8f` | 2026-09-25 | `docs/archive/AgentMonitor/docs/monitor-reload-fr89.md` | no live counterpart |
| `docs/operator-playbook.md` | `6879d8f` | 2026-09-26 | `docs/archive/AgentMonitor/docs/operator-playbook.md` | no live counterpart |
| `shortcuts/README.md` | `6879d8f` | 2026-09-24 | `docs/archive/AgentMonitor/shortcuts/README.md` | live counterpart `README.md`. |

### gh-Jeeves

| Archived path | Commit | Last changed | Now lives at | Live counterpart / note |
|---|---|---|---|---|
| `.grok/skills/harvest-agent-skills/SKILL.md` | `4ff29b5` | 2026-09-25 | `docs/archive/gh-Jeeves/.grok/skills/harvest-agent-skills/SKILL.archived.md` | live counterpart `common/.grok/skills/harvest-agent-skills/SKILL.md`. |
| `README.md` | `4ff29b5` | 2026-10-03 | `docs/archive/gh-Jeeves/README.md` | merged into `README.md` by FR #806 / PR #825 |
| `docs/brief/JEEVES_BRIEF.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/brief/JEEVES_BRIEF.md` | no live counterpart |
| `docs/endpoint-smoke-fr204.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/endpoint-smoke-fr204.md` | no live counterpart |
| `docs/exception-report.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/docs/exception-report.md` | no live counterpart |
| `docs/feature-request-ack-done-busy-idle-fr161-2026-09-26.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/docs/feature-request-ack-done-busy-idle-fr161-2026-09-26.md` | no live counterpart |
| `docs/feature-request-agent-payload-schema-2026-09-27.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/feature-request-agent-payload-schema-2026-09-27.md` | no live counterpart |
| `docs/feature-request-digest-worker-nick-entries-2026-09-26.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/docs/feature-request-digest-worker-nick-entries-2026-09-26.md` | no live counterpart |
| `docs/feature-request-focus-mutators-fr170-2026-09-26.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/docs/feature-request-focus-mutators-fr170-2026-09-26.md` | no live counterpart |
| `docs/feature-request-handoff-monitor-2026-09-27.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/feature-request-handoff-monitor-2026-09-27.md` | no live counterpart |
| `docs/feature-request-k1-chair-bored-fr175-2026-09-26.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/docs/feature-request-k1-chair-bored-fr175-2026-09-26.md` | no live counterpart |
| `docs/feature-request-offer-exclusive-90s-2026-09-27.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/feature-request-offer-exclusive-90s-2026-09-27.md` | no live counterpart |
| `docs/feature-request-per-machine-digest-fr159-2026-09-26.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/docs/feature-request-per-machine-digest-fr159-2026-09-26.md` | no live counterpart |
| `docs/feature-request-recycle-local-bob-fr197-2026-09-27.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/feature-request-recycle-local-bob-fr197-2026-09-27.md` | no live counterpart |
| `docs/feature-request-recycle-machine-scope-fr211-2026-09-28.md` | `4ff29b5` | 2026-09-28 | `docs/archive/gh-Jeeves/docs/feature-request-recycle-machine-scope-fr211-2026-09-28.md` | no live counterpart |
| `docs/feature-request-uat-worker-vision-fidelity-fr187-2026-09-27.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/feature-request-uat-worker-vision-fidelity-fr187-2026-09-27.md` | no live counterpart |
| `docs/functional-spec.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/functional-spec.md` | merged into `common/docs/functional-spec.md` by FR #806 / PR #825 |
| `docs/g2-live-smoke-checklist.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/g2-live-smoke-checklist.md` | no live counterpart |
| `docs/jira-webhook-customer-guide.md` | `4ff29b5` | 2026-09-28 | `docs/archive/gh-Jeeves/docs/jira-webhook-customer-guide.md` | live counterpart `jeeves/docs/jira-webhook-customer-guide.md`. |
| `docs/migration-plan.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/docs/migration-plan.md` | no live counterpart |
| `docs/mocks/empty.html` | `4ff29b5` | 2026-09-25 | `docs/archive/gh-Jeeves/docs/mocks/empty.html` | live counterpart `jeeves/docs/mocks/empty.html`. |
| `docs/mocks/error.html` | `4ff29b5` | 2026-09-25 | `docs/archive/gh-Jeeves/docs/mocks/error.html` | live counterpart `jeeves/docs/mocks/error.html`. |
| `docs/mocks/home.html` | `4ff29b5` | 2026-09-25 | `docs/archive/gh-Jeeves/docs/mocks/home.html` | live counterpart `jeeves/docs/mocks/home.html`. |
| `docs/mrb-enforcement.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/docs/mrb-enforcement.md` | no live counterpart |
| `docs/mrb-gates.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/mrb-gates.md` | no live counterpart |
| `docs/receiver-bobcallback-cutover.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/receiver-bobcallback-cutover.md` | no live counterpart |
| `docs/simon-auto-oper-runtime-fr160.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/docs/simon-auto-oper-runtime-fr160.md` | no live counterpart |
| `docs/vision.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/docs/vision.md` | live counterpart `common/docs/vision.md`. |
| `skills/README.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/skills/README.md` | live counterpart `README.md`. |
| `skills/harvest/SKILL.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/skills/harvest/SKILL.archived.md` | live counterpart `common/.grok/skills/harvest/SKILL.md`. |
| `skills/jeeves-announce-debug/SKILL.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/skills/jeeves-announce-debug/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-health/SKILL.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/skills/jeeves-health/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-install-service/SKILL.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/skills/jeeves-install-service/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-irc-roles/SKILL.md` | `4ff29b5` | 2026-09-25 | `docs/archive/gh-Jeeves/skills/jeeves-irc-roles/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-mrb-gates/SKILL.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/skills/jeeves-mrb-gates/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-queue/SKILL.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/skills/jeeves-queue/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-recycle/SKILL.md` | `4ff29b5` | 2026-09-28 | `docs/archive/gh-Jeeves/skills/jeeves-recycle/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-release/SKILL.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/skills/jeeves-release/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-shop-protocol/SKILL.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/skills/jeeves-shop-protocol/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-task-modes/SKILL.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/skills/jeeves-task-modes/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-token-less-gate/SKILL.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/skills/jeeves-token-less-gate/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-uat/SKILL.md` | `4ff29b5` | 2026-09-27 | `docs/archive/gh-Jeeves/skills/jeeves-uat/SKILL.archived.md` | no live counterpart |
| `skills/jeeves-worker-state/SKILL.md` | `4ff29b5` | 2026-09-26 | `docs/archive/gh-Jeeves/skills/jeeves-worker-state/SKILL.archived.md` | no live counterpart |
| `skills/report/SKILL.md` | `4ff29b5` | 2026-10-02 | `docs/archive/gh-Jeeves/skills/report/SKILL.archived.md` | no live counterpart |

### bob-design-uat

| Archived path | Commit | Last changed | Now lives at | Live counterpart / note |
|---|---|---|---|---|
| `.grok/skills/design-uat/SKILL.md` | `1acf2a3` | 2026-09-24 | `docs/archive/bob-design-uat/.grok/skills/design-uat/SKILL.archived.md` | no live counterpart |
| `.grok/skills/graphics-design/SKILL.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/.grok/skills/graphics-design/SKILL.archived.md` | no live counterpart |
| `.grok/skills/harvest-agent-skills/SKILL.md` | `1acf2a3` | 2026-09-24 | `docs/archive/bob-design-uat/.grok/skills/harvest-agent-skills/SKILL.archived.md` | merged into `common/.grok/skills/harvest-agent-skills/SKILL.md` by FR #806 / PR #825 |
| `.grok/skills/illustrator-design/SKILL.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/.grok/skills/illustrator-design/SKILL.archived.md` | no live counterpart |
| `.grok/skills/mrb-project-management/SKILL.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/.grok/skills/mrb-project-management/SKILL.archived.md` | no live counterpart |
| `.grok/skills/pdf-design/SKILL.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/.grok/skills/pdf-design/SKILL.archived.md` | no live counterpart |
| `.grok/skills/playwright-design/SKILL.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/.grok/skills/playwright-design/SKILL.archived.md` | no live counterpart |
| `.grok/skills/uat-video-pack/SKILL.md` | `1acf2a3` | 2026-09-24 | `docs/archive/bob-design-uat/.grok/skills/uat-video-pack/SKILL.archived.md` | no live counterpart |
| `README.md` | `1acf2a3` | 2026-09-24 | `docs/archive/bob-design-uat/README.md` | live counterpart `README.md`. |
| `docs/build-and-test-plan-screen-layout-overlap-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/build-and-test-plan-screen-layout-overlap-2026-09-22.md` | no live counterpart |
| `docs/build-and-test-plan.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/build-and-test-plan.md` | no live counterpart |
| `docs/expected-nits.schema.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/expected-nits.schema.md` | no live counterpart |
| `docs/feature-request-design-uat-skill-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/feature-request-design-uat-skill-2026-09-22.md` | no live counterpart |
| `docs/feature-request-golden-fixture-pack-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/feature-request-golden-fixture-pack-2026-09-22.md` | no live counterpart |
| `docs/feature-request-hallucination-inventory-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/feature-request-hallucination-inventory-2026-09-22.md` | no live counterpart |
| `docs/feature-request-mrb-project-management-harvest-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/feature-request-mrb-project-management-harvest-2026-09-22.md` | no live counterpart |
| `docs/feature-request-pdf-illustrator-graphics-skills-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/feature-request-pdf-illustrator-graphics-skills-2026-09-22.md` | no live counterpart |
| `docs/feature-request-pixel-perfect-deltas-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/feature-request-pixel-perfect-deltas-2026-09-22.md` | no live counterpart |
| `docs/feature-request-playwright-visual-uat-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/feature-request-playwright-visual-uat-2026-09-22.md` | no live counterpart |
| `docs/feature-request-screen-layout-overlap-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/feature-request-screen-layout-overlap-2026-09-22.md` | no live counterpart |
| `docs/feature-request-three-gates-2026-09-22.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/feature-request-three-gates-2026-09-22.md` | no live counterpart |
| `docs/functional-spec.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/functional-spec.md` | merged into `common/docs/functional-spec.md` by FR #806 / PR #825 |
| `docs/jester-uat-video-pack-harvest-2026-09-24.md` | `1acf2a3` | 2026-09-24 | `docs/archive/bob-design-uat/docs/jester-uat-video-pack-harvest-2026-09-24.md` | no live counterpart |
| `docs/skill-harvest-log.md` | `1acf2a3` | 2026-09-24 | `docs/archive/bob-design-uat/docs/skill-harvest-log.md` | live counterpart `common/docs/skill-harvest-log.md`. |
| `docs/templates/design-uat-report.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/docs/templates/design-uat-report.md` | no live counterpart |
| `fixtures/README.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/README.md` | live counterpart `README.md`. |
| `fixtures/T-A00-clean/brief.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A00-clean/brief.md` | no live counterpart |
| `fixtures/T-A00-clean/expected-nits.yaml` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A00-clean/expected-nits.yaml` | no live counterpart |
| `fixtures/T-A00-clean/screenshot.png` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A00-clean/screenshot.png` | no live counterpart |
| `fixtures/T-A01-wrong-hex/brief.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A01-wrong-hex/brief.md` | no live counterpart |
| `fixtures/T-A01-wrong-hex/expected-nits.yaml` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A01-wrong-hex/expected-nits.yaml` | no live counterpart |
| `fixtures/T-A01-wrong-hex/screenshot.png` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A01-wrong-hex/screenshot.png` | no live counterpart |
| `fixtures/T-A02-1px/brief.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A02-1px/brief.md` | no live counterpart |
| `fixtures/T-A02-1px/expected-nits.yaml` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A02-1px/expected-nits.yaml` | no live counterpart |
| `fixtures/T-A02-1px/screenshot.png` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A02-1px/screenshot.png` | no live counterpart |
| `fixtures/T-A03-invented-logo/brief.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A03-invented-logo/brief.md` | no live counterpart |
| `fixtures/T-A03-invented-logo/expected-nits.yaml` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A03-invented-logo/expected-nits.yaml` | no live counterpart |
| `fixtures/T-A03-invented-logo/screenshot.png` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-A03-invented-logo/screenshot.png` | no live counterpart |
| `fixtures/T-G01-spelling/brief.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G01-spelling/brief.md` | no live counterpart |
| `fixtures/T-G01-spelling/expected-nits.yaml` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G01-spelling/expected-nits.yaml` | no live counterpart |
| `fixtures/T-G01-spelling/screenshot.png` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G01-spelling/screenshot.png` | no live counterpart |
| `fixtures/T-G02-layout/brief.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G02-layout/brief.md` | no live counterpart |
| `fixtures/T-G02-layout/expected-nits.yaml` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G02-layout/expected-nits.yaml` | no live counterpart |
| `fixtures/T-G02-layout/screenshot.png` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G02-layout/screenshot.png` | no live counterpart |
| `fixtures/T-G03-hallucination/brief.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G03-hallucination/brief.md` | no live counterpart |
| `fixtures/T-G03-hallucination/expected-nits.yaml` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G03-hallucination/expected-nits.yaml` | no live counterpart |
| `fixtures/T-G03-hallucination/screenshot.png` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G03-hallucination/screenshot.png` | no live counterpart |
| `fixtures/T-G04-overlap/brief.md` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G04-overlap/brief.md` | no live counterpart |
| `fixtures/T-G04-overlap/expected-nits.yaml` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G04-overlap/expected-nits.yaml` | no live counterpart |
| `fixtures/T-G04-overlap/screenshot.png` | `1acf2a3` | 2026-09-22 | `docs/archive/bob-design-uat/fixtures/T-G04-overlap/screenshot.png` | no live counterpart |
