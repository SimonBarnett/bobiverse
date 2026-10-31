---
name: bobiverse-jeeves-repos
description: >
  Onboard a GitHub repo so its issues/PRs get FR/MRB from Jeeves, and recover a given-up job for direct !assign.
  Use when adding a repo to the MRB filter, resync-repos.txt, !focus priority, clearing give-ups, or /bobiverse-jeeves-repos.
---

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://bob.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

# bobiverse-jeeves-repos (FR #5134)

Operator playbooks for the deterministic chair. Prefer this skill over rediscovering paths from live ionos files.
Cross-links: bobiverse-jeeves-commands, bobiverse-jeeves-troubleshooting, docs/jeeves-commands.md.

**Monitor seats must not run these commands** (never !assign / !focus / hand-edit the queue). Owner or bob-* ear only.

## Homes (which file is real)

| Path | Typical location | What lives there |
|---|---|---|
| Chair --home / BOB_HOME | %USERPROFILE%\.jeeves | identity, cmd-trace.log, **resync-repos.txt that configured_repos reads**, webhook-health.json |
| Digest BOB_DIGEST_HOME | %USERPROFILE%\.bobiverse | **queue.json**, **focus.json**, **ignored.json**, **seat-ledger.json**, digest.json, roster |

gitclaim / focus_ignore redirect through fleet_digest_home (digest home wins). chair_health.configured_repos(home) reads **literal** <chair --home>/resync-repos.txt (plus env JEEVES_RESYNC_REPOS). Install/start also **seeds a twin** at <digest home>/resync-repos.txt (FR #4725) so both trees stay stocked, but discovery does **not** read the digest twin when the homes differ. When hand-editing the list, edit the **chair-home** file (or keep both identical). Follow-up: collapse the twin into one source of truth.

## 1. Onboard a repo so issues/PRs get FR/MRB

Goal: open issues become FR rows and open PRs become MRB rows after !resync / webhook events, and !bored can offer them under focus.

1. **Add owner/repo to the resync list** (durable discovery even without focus):
   - Append one line to %USERPROFILE%\.jeeves\resync-repos.txt (chair home). Example: SimonBarnett/priority-branding.
   - Optional: mirror the same line in %USERPROFILE%\.bobiverse\resync-repos.txt so the twin stays aligned.
   - Or set env JEEVES_RESYNC_REPOS (comma/semicolon list) for a one-box override.
   - Fleet defaults live in code DEFAULT_RESYNC_REPOS and pack jeeves/defaults/resync-repos.txt (merged on install/start; never deletes operator extras).
2. **Set priority** with repo-level focus (writes digest-home focus.json):
   - !focus high|medium|low|N owner/repo
   - Worked example (2026-10-28): !focus low SimonBarnett/priority-branding -> PM reply `focus: SimonBarnett/priority-branding priority=9 (low)`.
   - strict: true in focus means unlisted repos are not worked (!list / !bored hide them). Prefer repo-level focus (FR #1520); item owner/repo#N is skipped when that repo is already focused.
   - FR #3146: focus.repos is **unioned** into GitHub resync discovery, so a focused repo is fetched even if missing from resync-repos.txt. Still add the file line for durable onboarding after unfocus.
3. **Run !resync** (ops: simon account or bob-* ear). Expected PM reply shape:
   `resync: roster refresh requested; GitHub FR/MRB re-sync queued; queue unaccepted=U accepted=A purged_ignored=P`
4. **GitHub webhook** (GIT events -> #bobiverse / queue): confirm the repo has the Bob/Jeeves hook (https://bob.ntsa.uk/bob/v1/git). Adding a hook needs **Simon yes**. Without the hook, hourly/gap !resync still merges open FR/MRB; webhooks remain the preferred source of truth (FR #3212).
5. Confirm with !list owner/repo / !status (github_resync: line) and a shop !bored on an idle seat.

### Quick path (priority-branding class)

```text
!focus low SimonBarnett/priority-branding
!resync
```

Then ensure %USERPROFILE%\.jeeves\resync-repos.txt contains SimonBarnett/priority-branding (or wait for the next install merge of DEFAULT_RESYNC_REPOS).

## 2. Clear give-ups and re-assign a job to a seat

After GIVEUP / NACK:

- Cooldown is **GIVEUP_COOLDOWN_S = 600** seconds (10 min) on the queue row (cooldown_until).
- !assign refuses any seat that already gave that job up (giveup_seats and durable seat-ledger).
- Once needs_human is stamped, auto-offer blocks **every** seat; only explicit !assign may hand the row out (FR #4336). Owner GitHub issue_comment after giveup_ts can clear needs_human (FR #4711). Self-MRB / out-of-fuel GIVEUPs do not burn the needs_human budget the same way (FR #3277 / #4881).

**!resync alone does not clear give-ups.**

Give-ups live in **two** stores under the **digest home** (%USERPROFILE%\.bobiverse); clear **both**:

1. queue.json row fields: giveup_seats, cooldown_until, giveup_ts, giveup_count, needs_human (and related stamps you intend to lift).
2. seat-ledger.json -> giveup["owner/repo#n"] (key is **lower-case**).

Procedure:

1. Back up both files first (copy beside them with a timestamp). **Never restart Jeeves during a live !build.**
2. Edit under the queue lock if you can (chair process holds an in-process RLock; prefer a quiet moment). Hand-edit is the only path today.
3. Clear the row stamps and remove that seat (or all seats) from the ledger giveup entry for owner/repo#n.
4. !assign <seat-nick> owner/repo FR|MRB|UAT|FIX N (ops only). Seat must be idle, in the shop, not self-MRB/UAT-blocked, not machine-pinned elsewhere.
5. If auto-offer should resume for everyone, also clear needs_human (or wait for an owner issue comment per FR #4711).

If the seat ACK->GIVEUPs again immediately, **stop clearing** and file/report the loop (harvest #2314) instead of thrashing the ledger.

## 3. Gap (follow-up, not implemented here)

There is **no** Jeeves command that clears give-ups today, so recovery means hand-editing JSON on the live chair. Recommend an op-gated !cleargiveup owner/repo#N [seat] that clears both stores atomically under the queue lock, then document it beside this skill. Until that lands, use section 2.

## Related

- Commands / auth matrix: bobiverse-jeeves-commands
- Empty offer / ledger symptoms: bobiverse-jeeves-troubleshooting, jeeves/docs/empty-offer-playbook.md
- Architecture / homes: bobiverse-jeeves
