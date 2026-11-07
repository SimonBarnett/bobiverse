# Feature request: digest ear-publish, OpenCode/Copilot paint, fuel logos

Date: 2026-11-07
Repo: SimonBarnett/bobiverse
Plan folder: plan/work/plan-20261107-132147
Related: PR #6121 / FR #6120 (OpenCode fuel landed; display/publish gap remains)

## Goal

Make ircBob the sole publisher of fleet fuel digests to `https://bob.ntsa.uk/bob/v1/report`, keep TipForm/Status honest (MarchHare, redqueen xAI account, OpenCode pools, fresh Copilot), and identify each fuel family with a company logo.

## Success

See `docs/vision.md` Success table S1-S8 (LOCKED).

## Gap vs origin/main

See `GAP-ANALYSIS.md` at plan root (worktree tip a02e56a2).

## Deliverables (umbrella; implement via small FRs)

1. Ear fuel publish path; tray fuel POST disabled
2. bob.ntsa.uk canonical defaults + docs
3. xAI/Grok account label on digest
4. MarchHare pool/reset correctness
5. On-change / no-lag POST (incl. OpenCode + Copilot fingerprint)
6. Publish opencode-free / opencode-go
7. TipForm/Status OpenCode + restored multi-family fuel strip with logos
8. Copilot systray freshness
9. Logo assets + mocks
10. Docs/skills park

## Out of scope

- Re-implement OpenCode seat math (#6121)
- Digest as Cursor Agents fuel-gate when local Spending known
- IRC whisper as digest SoT; secrets in body; UAT stamp; Ergo/BobIrcd