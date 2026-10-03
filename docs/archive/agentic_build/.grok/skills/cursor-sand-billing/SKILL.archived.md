<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/cursor-sand-billing/SKILL.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: cursor-sand-billing
description: >
  Grok Bot / Cursor Sand is silent until the customer has paid. Use when the
  user says paid their bill, unpaid invoice, Open invoice, Stripe Link,
  NEEDS_AUTH, Grok Bot deaf after 100% Sand, or /cursor-sand-billing. Numbers
  live in box-usage. Named-bot hangs that are not billing are unstick-grok-bot.
---

# Cursor Sand billing (customer paid?)

When every Grok Bot turn is `ACCEPTED_TEMPORAL` with **no** assistant `send-message` and RecreateSandBox does nothing, check billing **before** another sandbox recycle.

1. `GetSandUsageStatus` — `usagePercent: 100` (weekly Sand empty). Reset `nextResetTimestampUtc`.
2. `ListGrokBotStripeLinkPaymentMethods` — `OUTCOME_NEEDS_AUTH` means on-demand cannot charge (box send 503).
3. Cursor **Billing & Invoices** (not Spending): https://cursor.com/dashboard/billing  
   Spending (`https://cursor.com/dashboard/spending`) is meters only. Pay **Open** invoices there, or **Manage Subscription** → Stripe. Banner: **You may have an unpaid invoice.**

After invoices show **Paid** and Stripe is no longer `NEEDS_AUTH`, one ping to the named bot. Do not RecreateSandBox for this. Do not print dashboard/Stripe URLs that look like session tokens.

Owner of remaining % / overage GBP: `box-usage`.
