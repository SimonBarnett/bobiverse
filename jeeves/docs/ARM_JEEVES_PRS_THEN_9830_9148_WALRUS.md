# ARM: tip Jeeves PRs → digests #9830 + #9148 → walrus rebuild/install

**Activated by Si:** 2026-11-24  
**Tracker FR:** #9847  
**Observation check:** `tip_merge_gate` (`Test-JeevesMonitorTipMergeGate.ps1`)

## CAST IRON sequence

1. **Tip merge** — every PR in the fixed tip cohort below is **merged**.
2. **Digests** — `#9830` and `#9148` are **CLOSED**, and every recorded child on each digest is **CLOSED**. Only Si removes `hold` on a held digest; then normal `!bored` / offer flow dispatches children (`!assign` only for true starvation).
3. **Walrus rebuild + Slab install** — only after steps 1–2. Build from **main tip** after step 2 (never an older green SHA). Live `Install-JeevesWalrusWinRm.ps1` runs include `-GateIssues` covering `#9830` and `#9148`. Slab installs; Si gives her own yes.

**Never** `!build`, installer `-SiYes`, or an install/build **receipt** during steps 1 or 2.

## Tip PR cohort (locked 2026-11-24)

Keep identical to `DEFAULT_TIP_PRS` in `jeeves/tools/monitor/tip_merge_gate.py`:

| PR | Origin FR (tip path) |
|----|----------------------|
| #9788 | #9781 |
| #9789 | #9782 |
| #9829 | #9826 |
| #9834 | #9821 |
| #9839 | #9827 |
| #9842 | #9840 |

Evidence at lock: tip-path allowlist / TipPrByFr; Si note that #9788 DONE PASS. Do not grow this cohort with later step-2 child PRs.

## Digests and children

| Digest | Notes | Children (recorded) |
|--------|-------|---------------------|
| #9830 | `fr-digest` (+ `hold` while batch locked). Kind/label digest. | #9831 #9832 #9833 #9835 #9836 #9837 #9838 #9846 #9847 #9848 #9849 #9850 #9854 #9855 #9861 #9862 #9863 #9864 #9865 #9867 #9871 #9872 #9875 #9877 #9878 #9879 #9880 #9881 #9882 |
| #9148 | `Kind: fr-digest` (label digest; auto-close rules may differ for Kind-only). CLOSED when children closed. | #8775 #8777 #8778 #8780 #8781 #8782 #8783 #8784 |

Record child lists again at unhold if the digest body grows. Pre-BOB-G1 chair caveat: check for a durable `depends_open` stamp that could strand a child.

## `tip_merge_gate` verdicts

| Verdict | Exit | Meaning |
|---------|------|---------|
| `NO_INSTALL` | 1 | Tip open / closed-unmerged, digest or child open, unknown/rate-limit/404, empty cohort |
| `OK_FOR_RECEIPT` | 0 | Cohort non-empty, every tip PR merged, both digests + all listed children closed |

- `source` must be `live` with fresh `observed_at` on a receipt. **`fixture` / `dry_run` / `skipped` / `soft_ok` / `unknown` are not valid receipt evidence.**
- `watch_jeeves_tip_prs.ps1` is absent from the tree; `tip_merge_gate` is the observation mechanism.
- Expected `NO_INSTALL` during steps 1–2: comment the step on **one** deduplicated tracker (#9847 / this ARM) — do not file new intake each cycle. File intake only for `state_unknown` or `cohort_undefined`.

## Step entry / exit

| Step | Enter when | Exit when |
|------|------------|-----------|
| 1 | ARM active | All cohort PRs `merged` |
| 2 | Step 1 complete; Si unholds digests as needed | Digests + recorded children `closed` |
| 3 | Live `OK_FOR_RECEIPT` | Build from tip + walrus install receipt PASS (Si yes) |

After install receipt PASS, remove `tip_merge_gate` from the required monitor cycle in a follow-up.

## Env overrides (tests / ops)

- `JEEVES_MONITOR_TIP_MERGE_GATE_FIXTURE` — JSON `{prs, issues}`
- `JEEVES_MONITOR_TIP_MERGE_GATE_TIP_PRS` — comma ints
- `JEEVES_MONITOR_TIP_MERGE_GATE_DIGESTS` — comma ints
- `JEEVES_MONITOR_TIP_MERGE_GATE_CHILDREN` — `9830:9831|9832;9148:8775|8777`
- `JEEVES_MONITOR_TIP_MERGE_GATE_REPO` — default `SimonBarnett/bobiverse`
