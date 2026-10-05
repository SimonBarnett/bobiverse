# Focused-repo FR vs queue snapshot (FR #2454)

Verification chore after the pin-starve incident (#2446) and empty-offer playbook (#2448 / PR #2455).
**Heal PR #2450 was still open** at snapshot time (MRB in progress on another seat) — this is a pre-heal baseline plus gap notes, not a claim that ledger heal has landed.

Source: live `GET https://irc.ntsa.uk/bob/v1/report` → `queue` (chair mirror), plus `gh issue list` on focused repos.

## Snapshot (2026-10-05 ~10:02 UTC)

### Queue unaccepted (7)

| Row | require_machine | Notes |
|-----|-----------------|-------|
| agentic_fomprep#56 FR | ce-priority-dev1 | pin; DEV1 shop workers=0 in digest |
| bobiverse#1102 FR | ce-priority-dev1 | pin |
| bobiverse#2451 FR | ionos | stamp follow-up |
| bobiverse#2452 FR | ionos | stamp follow-up |
| bobiverse#2447 FR | ionos | release pack |
| bobiverse#2455 MRB | — | **stale: PR merged 09:59Z** |
| bobiverse#2456 FR | — | via-intake worktrees bug |

### Queue accepted (4)

| Row | require_machine | offered_to |
|-----|-----------------|------------|
| bobiverse#1993 FR | ionos | win-mpre8vi4u6u-14452 |
| bobiverse#2450 MRB | — | win-mpre8vi4u6u-7764 (heal PR) |
| bobiverse#2453 FR | — | marchhare-35016 |
| bobiverse#2454 FR | — | marchhare-40208 (this verify) |

### Open bobiverse issues (GitHub) vs queue

| Issue | In queue? | Gap? |
|-------|-----------|------|
| #2456 | unaccepted | no |
| #2454 | accepted | no |
| #2453 | accepted | no |
| #2452 | unaccepted | no |
| #2451 | unaccepted | no |
| #2449 | **absent** | held by open PR #2450 `Closes` (heal folds tests); OK until #2450 merges |
| #2447 | unaccepted | no |
| #2446 | **absent** | superseded by accepted MRB #2450; OK |
| #1993 | accepted | no |
| #1102 | unaccepted | no |

Open agentic_fomprep feature-request living work: **#56** present as unaccepted pin (other open issues are mrb-home / historical boards — not expected as FR offer rows).

## Remaining gaps (filed / tracked)

1. **Stale merged MRB in unaccepted:** `bobiverse#2455` still listed after merge — follow-up #2458.
2. **Heal not merged yet:** re-check offerable vs pins after #2450 lands; playbook monitor (#2448) already on main.
3. **Pins-only ungated empty:** unaccepted still dominated by `require_machine` (ce-priority-dev1 + ionos); unpinned living FRs (#2453/#2454/#2456) are accepted or new — fleet still pin-heavy for idle non-pin machines once current ACKs complete.

## Method (repeatable)

```powershell
$r = Invoke-RestMethod https://irc.ntsa.uk/bob/v1/report
$r.queue.unaccepted | Select-Object task, repo, id, require_machine
$r.queue.accepted   | Select-Object task, repo, id, require_machine, offered_to
gh issue list --repo SimonBarnett/bobiverse --state open --json number,title,labels
```

See also: `empty-offer-playbook.md` (FR #2448), root-cause #2446 / PR #2450.