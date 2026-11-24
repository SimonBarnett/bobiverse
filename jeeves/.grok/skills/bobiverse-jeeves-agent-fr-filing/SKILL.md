---
name: bobiverse-jeeves-agent-fr-filing
description: >
  File an FR or issue the fleet way: twin-check first, one issue per issue
  (anti-omnibus), right repo (product repo vs bobiverse), feature-request
  label, evidence block, no secrets; close later twins with a reference to the
  first. Use before filing anything or /bobiverse-jeeves-agent-fr-filing.
depends_on: []
---

# bobiverse-jeeves-agent-fr-filing

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

## Steps

1. **Twin-check.** Search open (and recently closed) issues in the target repo for the same symptom and cause.
   If one exists, comment the new evidence there instead of filing.
2. **Right repo.** Product bugs go to the product repo (e.g. a-search for a-search code); fleet/Jeeves/worker
   issues go to `SimonBarnett/bobiverse`. Intake: `Report-BobiverseIntakeIssue.ps1 -Repo <owner/name>`.
3. **One issue per issue.** One root cause, one acceptance row. Split anything with "and also".
4. **Body:** what / where / evidence / fix. Evidence block = exact log lines, run ids, SHAs, timestamps with
   zone, and how to reproduce. Separate observed facts from guesses. Prefer GitHub `needs-<machine>` labels
   over a body `require_machine:` line on bobiverse (FR #9637: body alone does not pin). Add `needs-<machine>`
   **only** for true host-action work. Implement-anywhere chair/worker **code** must not get `needs-*`.
   **CAST IRON #9708:** if you later `!unpin` to `any`, remove every `needs-*` label in the same turn — never
   leave `needs-*` + `rm=any`.
5. **Label** `feature-request` for FRs. Add `hold` only for parked/phase-gated work.
   **Walrus-action / chair-host children (CAST IRON #9669 / FR #9679):** also label `needs-walrus` (or
   title `chair-host: …`) so the chair does not offer them to flamingo/redqueen.
6. **Report** the URL. Do not assign or pin it yourself.

## Twins

When two issues cover the same thing, keep the **first**, close the later one with
"Duplicate of #<first>", and move any extra evidence to the first. Done issues are closed too.

## Never

Secrets, keys, tokens, oper creds, private IPs/hostnames, or `inbound-transcript.log` content in an issue.
Omnibus FRs. Filing the same thing twice because a search was too narrow.

## Digests (Si) — CAST IRON (FR #9652)

**When filing multiple related FRs in one turn/batch there MUST be a Digest parent.** Never leave a multi-FR batch as free-floating issues.

1. File (or reuse) parent first: Title `Digest: <batch>`; labels `feature-request` + `fr-digest` (add `hold` only to park the whole batch).
2. List every child in the digest body; last-child close closes the digest (#9552).
3. Each child body starts with plain `Depends-on: #<digest>`.
4. Digests stay **useful when unheld** (released drain). Unheld means the batch drains; it does not mean skip the digest.
5. Same-turn repair: if ≥2 related FRs already landed without a digest, file the digest immediately and wire children.

The CAST IRON *rule* FR itself (#9652) is a normal FR (not an `fr-digest` parent). Batch parents use the `Digest: …` title + `fr-digest` label.

## needs-walrus split — CAST IRON (FR #9669)

When work mixes **code** and **walrus host action**, file **two** FRs under one Digest (`feature-request` + `fr-digest`):

| Child | Owner | Labels / pin |
|---|---|---|
| **Code** | worker (any machine) | `feature-request` only — **no** `needs-walrus` |
| **Walrus action** | Jeeves agent (walrus) | `needs-walrus`; `Depends-on: #<code>` (+ digest) |

Rules:

1. Pure code/docs/PR FRs are never `needs-walrus` (#9637).
2. Walrus child waits until code child is CLOSED/merged tip.
3. If a seat NACK/GIVEUP is `needs-walrus` / `require_machine=walrus`, the **Jeeves agent** does the walrus action (receipt + Slab/Si-yes) — do not leave ACK→GIVEUP thrash on other machines.
4. MONITORING on needs-walrus NACK: stop wrong-machine re-offer; ensure this split exists; drive walrus child via Jeeves-agent/Slab — do not only comment.
5. **CAST IRON FR #9708:** implement-anywhere work — remove `needs-*` **and** `!unpin` together (never leave `needs-*` + `rm=any`). True host-action keeps `needs-*` + `!pin`. Chair `!unpin` refuses while `needs-*` remains on the queue row.

## remove needs-* + !unpin — CAST IRON (FR #9708)

| Work kind | Labels | Pin |
|---|---|---|
| Implement-anywhere (chair/worker **code**) | Remove every `needs-<machine>` | `!unpin` → `require_machine=any` |
| True host action (install/heal on chair host / shop) | Keep `needs-<machine>` | Keep `!pin` / `require_machine=<machine>` |

**Same turn:** never leave `needs-*` on an issue unpinned to `any` — that pair causes ACK→GIVEUP `reason=require_machine=<machine>` and wrong-shop re-offer loops (#9628/#9634 class; tip gate #9664). Never `!unpin` while a `needs-*` label remains on host-action work.
