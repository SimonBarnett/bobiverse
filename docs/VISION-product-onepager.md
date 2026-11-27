# Bobiverse — product one-pager

**Repo:** https://github.com/SimonBarnett/bobiverse  
**Shape:** Windows fleet **service** (MSIs for Jeeves, Bob, airc)

## One sentence

Bobiverse is a **6GL**: plain-English intent becomes shipped code through Git, with IRC as the real-time control surface.

## The loop

```text
Human / Plan agent
  -> FR digests with Gantt-style dependencies
    -> Jeeves (deterministic chair + webhooks + !assign)
      -> IRC shop #{machine}
        -> Bob worker (Grok | Cursor | OpenAI | Codex...)
          -> PR -> merge-review board (MRB) -> CI fix -> DONE
```

| Role | Job |
|------|-----|
| **Plan** | Turns intent into feature-request digests and dependency order |
| **Jeeves** | Deterministic Windows service — queues, assigns, chairs; not an LLM |
| **Bob** | Per-machine agents that open PRs, run hostile MRB, and fix CI |

## Why it is innovative

- **Git is the work product.** Specs, patches, reviews, and releases stay in the repo.
- **IRC is the shop floor.** Assign / ACK / DONE is an exact wire contract operators can watch live.
- **Deterministic dispatch.** Jeeves chairs without model drift on routing.
- **Fuel is swappable.** xAI Grok, Cursor, and OpenAI-compatible CLIs today; **Codex** next as another Bob seat.
- **Training-grade traces.** Every job leaves structured Git + IRC history (plan -> assign -> patch -> review -> CI) useful for coding-agent eval, with secrets kept off the wire.

## Evidence of active maintenance

Public signals (order-of-magnitude, tip 2026-11): thousands of commits and PRs, active releases (e.g. v2.0.1), continuous FR/MRB/UAT flow across a Windows fleet. Stars are not the load metric — PR review, triage, and CI repair are.

## What ships

| MSI | Role |
|-----|------|
| `jeeves-*.msi` | Ergo + `ircJeeves` chair |
| `bob-*.msi` | `ircBob` ear, tray, worker seats |
| `airc-*.msi` | `{machine}_console` remote shell |

Operator install, sync, and pack docs live in the root [README.md](../README.md) under **Operator docs**.

## Codex for OSS angle

Wiring Codex as first-class Bob fuel funds FR implementation, MRB, and CI-fix at volume, and produces anonymizable maintainer+agent traces for coding-agent training under public OSS workflows.
