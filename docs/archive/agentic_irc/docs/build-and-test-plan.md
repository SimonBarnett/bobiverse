<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan — agentic_irc moot/file/dumb extensions

**Repo:** SimonBarnett/agentic_irc  
**Spec:** [feature-request-moot-file-dumb-2026-09-19.pdf](./feature-request-moot-file-dumb-2026-09-19.pdf) (+ [md](./feature-request-moot-file-dumb-2026-09-19.md))  
**Baseline HEAD when dispatched:** e55f501  
**Machine:** ionos

## Reality check (Bob, 2026-09-19)

The parked "Status: not started" line in the feature-request md is **stale**. On `main` @ e55f501 the tree already contains:

| PDF deliverable | Present? |
|---|---|
| `scripts/wire.py` + CAPA/MOOT/FILE/DUMB parsers | Yes |
| `scripts/moot.py` + irc_agent `handle_moot` | Yes |
| `scripts/filexfer.py` + FileBag + handle_file | Yes |
| `scripts/dumb_agent.py` + `dumb_ctl.py` | Yes |
| Skills `agentic-moot` / `agentic-file` / `agentic-dumb` | Yes |
| `install_skill.py` vendors all four skills + scripts | Yes |
| `tests/test_wire|moot|filexfer|dumb.py` + MANUAL.md | Yes |
| Offline `pytest -q` | **52 passed, 1 skipped** on IONOS |
| `src/dumb_dotnet` full protocol clone | **Stub only** (prints INFO and exits 0) |

Do **not** re-implement from scratch. Close gaps against the PDF acceptance one-pager (Appendix C / §12).

## Goals (this dispatch)

1. Audit implementation vs PDF MUST / MUST NOT (phases 0–4 merge floor).
2. Strengthen thin tests where PDF tables are under-covered (especially file F* and dumb D* jail/busy/timeout cases).
3. Keep CI offline — no Libera sockets from pytest.
4. Update `docs/feature-request-moot-file-dumb-2026-09-19.md` status to reflect reality + remaining work.
5. Document .NET honestly: stub vs Phase 5 complete; if time allows, advance beyond stub without inventing network package restores at runtime.
6. `pytest -q` stays green. Commit and push.

## Non-goals

- Opening Libera from CI or inventing a platform.
- Group SEAL / DCC / web UI (Appendix B).
- Breaking AGPK/SEAL/protect behaviour.
- Claiming PASS for Bob MRB (Bob does hostile MRB after your push).

## Phase order

### P0 — Orient (must)
- Read the PDF + existing scripts/skills/tests.
- Run `pytest -q`. Record count.
- Produce a short gap list in `docs/gap-vs-feature-request-2026-09-19.md` (what PDF requires vs what tests prove).

### P1 — Test coverage vs §12 (must)
Expand offline tests toward:
- Wire W1–W6
- Moot M1–M7 (3-nick floor discipline → CLOSE; non-floor SAY dropped)
- File F1–F8 (tier S + M, hash fail, identity.json refuse, path traversal)
- Dumb D1–D10 (PSK roundtrip, operators miss, jail escape, busy, timeout monkeypatch)
Do not require real cmd.exe outside tmp; monkeypatch process runner.

### P2 — Docs status (must)
- Rewrite feature-request md **Status** section: implemented / remaining.
- Ensure README Extensions section stays field-kit voice and accurate about .NET stub if still stub.

### P3 — .NET (should / may slip)
- If Phase 5 cannot be completed this run: leave stub, document MSBuild + TLS 1.2 preflight in skill + `src/dumb_dotnet/README.md`, mark remaining in gap doc.
- If advancing: behaviour-compatible with `dumb_agent.py`; no runtime NuGet for crypto on 2012.

### P4 — Stop for Bob MRB
- Push. Paste pytest summary + gap doc path in completion.
- Do not self-declare ready for human UAT.

## Definition of done (first ticket)

- [ ] `docs/gap-vs-feature-request-2026-09-19.md` committed
- [ ] Feature-request status section no longer says "not started"
- [ ] `pytest -q` green; new tests for at least jail refuse + moot non-floor drop + file hash mismatch if not already present
- [ ] No Libera from tests
- [ ] Completion summary lists remaining PDF items (especially .NET)

## Kickoff constraints for Start-BobBuild

- Prefer cheapest capable model if CLI supports it
- Do not set or request an API key environment variable assignment
- Do not force-push; do not commit secrets / identity.json / connector.key / irc.log