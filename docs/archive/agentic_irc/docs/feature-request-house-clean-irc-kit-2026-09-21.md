<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-house-clean-irc-kit-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: house-clean IRC kit (Ergo canon, leftovers, drift)

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_irc
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/34
**Sister FR:** https://github.com/SimonBarnett/agentic_build/issues/89
**Raised by:** Simon (via originating agent review)
**UAT + hostile MRB owner:** Bob
**Build orchestrator:** Bob — `Start-BobBuild -Task git` on this repo

Field kit for the legion. Not a platform. Do not productise `seal.py` / DUMB / Mode 3.

## Problem

1. **Host drift.** README body already points fleet at private Ergo `irc.ntsa.uk:6697` `#bobiverse`. GitHub repo **description** and older docs/MRB titles still say Libera. Ionos was banned on Libera (2026-09-20). A worker that copies the About blurb will join the wrong network.

2. **Two-repo canon.** Live nicks, host, port live in `agentic_build` (`docs/bobiverse.md`, `config/bobiverse.json`) and again in `.grok/skills/bob-irc`. `bob-dev1` here vs `ce-priority-dev1` in the fleet registry is the same class of bug as build-repo issue #89.

3. **Docs attic.** `docs/` holds many `mrb-*.md` + PDFs and overlapping FRs (`bobiverse-quiet-talk`, `bobiverse-channel-talk-tray-pull`, `bobstat`, `bobstat-point`). Agents open the first match.

4. **TOFU is sharp.** First AGPK for a nick wins; wrong pin requires wiping `peers.json` on the **receiver**. Payload hidden; who/when/size leak. README says rotate if the log is dumped. There is no house drill (who wipes, which homes, how to re-announce without poisoning the other box).

5. **DUMB is not a git worker.** `airc-dumb.exe` / Mode 3 thin can `exec`. That is allowlisted operator power (`--operators` required, PSK off-channel, jail). `agentic_build` already says DUMB / 2012 is not a git-task worker. This repo must say the same in README + `agentic-dumb` so a harvest does not enqueue Form Prep on 2012.

6. **MOOT vs MODE2 free.** Extensions table: do not SAY unless you hold the floor; `#bobiverse` is MODE2 **free** with POINT / `!bobiverse`. Fine if written as two modes. Easy to read as one rule.

## Ask

### 1. One host sentence

- README first paragraph + GitHub description: fleet = Ergo `irc.ntsa.uk:6697` `#bobiverse`. Libera is **legacy only** (SASL / AWS note stays in a labelled section).
- `irc_agent.py` default host stays Ergo. Any example that uses `irc.libera.chat` is marked legacy.
- Test or grep in pytest: README and `bob-irc/SKILL.md` must contain `irc.ntsa.uk` and must not recommend Libera for `bob-*` nicks.

### 2. Nick table matches the fleet registry

- Copy the machine id ↔ IRC nick table from `agentic_build/config/bobiverse.json` / `docs/bobiverse.md` into README (or point at those files as the only table and delete the duplicate list from `bob-irc` except a one-line pointer).
- Alias `dev1` / `ce-priority-dev1` / nick `bob-dev1` in one place. Do not invent a fifth id.

### 3. Docs attic

- Add `docs/README.md` index: live specs vs historical MRB. Historical `mrb-*.pdf` stay (audit) but the skill points only at live FRs.
- `bob-irc` skill lists at most: bobiverse.md (build repo), this FR, `multi-agent-one-host.md`, `beacon-v1`.

### 4. TOFU rotation drill (docs + offline test only)

Write a short runbook in `docs/`:

- Wrong pin: wipe **receiver** `peers.json`, restart receiver, re-announce from the real nick, humans watch first AGPK.
- Log dumped: rotate X25519 keys on both homes; old AGPK lines on channel are poison; do not reuse id16.
- Pytest: mismatch AGPK is ignored; existing `inbox/<id>.bin` is not overwritten.

No new crypto. No signatures. Unattended public channels stay out of scope.

### 5. DUMB / Mode 3 guard text

README + `agentic-dumb` + `invite-airc`:

- Empty `--operators` refused (already code).
- Not a git-task worker. Not Form Prep. Not UAT.
- Win95 TLS still not claimed.

### 6. Two-mode sentence

One paragraph: MODE1/3 floor vs MODE2 free `#bobiverse` POINT / `!bobiverse` / `BOB TRAY v1` whispers. No vendor names in verbs (`SPEC WAIT BUILD PUSH MRB FIX UAT`).

## Acceptance

1. GitHub description + README + `bob-irc` agree: Ergo fleet, Libera legacy.
2. Nick/id table does not contradict `agentic_build` registry (sister work may land on #89 first; if JSON not yet unified, document the alias in both repos).
3. Skill does not point agents at historical MRB PDFs as current spec.
4. Rotation drill exists; offline pytest covers pin-mismatch and inbox id skip.
5. DUMB explicitly not a git worker.
6. Commit + PR on `work/<job>`. Hostile MRB on issue #34. Only Bob stamps UAT.

## Non-goals

- Public network, selling the kit, Win95 TLS, Phase 5 full .NET port.
- Changing SEAL v2 AAD.
- Opening IRC from CI (keep pytest offline).
- WinRM.
