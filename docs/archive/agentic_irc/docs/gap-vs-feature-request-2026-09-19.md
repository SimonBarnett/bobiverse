<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/gap-vs-feature-request-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Gap vs feature-request PDF (2026-09-19)

**Spec:** [feature-request-moot-file-dumb-2026-09-19.pdf](./feature-request-moot-file-dumb-2026-09-19.pdf)  
**First-audit HEAD:** `1a11e98`  
**This pass:** Bob MRB v1 blockers 1–4 only (AIRC-FILE envelope, dumb listen, D2 on the wire, truncated exec spill).  
**Method:** PDF §12 tables + Appendix C vs what offline tests assert. No Libera.

## Snapshot

| Area | Code | Tests vs §12 |
|---|---|---|
| Wire parsers | Yes | W1–W6 covered |
| Moot | Yes | M1–M7; 3-nick floor via `handle_privmsg` |
| File | Tier S AIRC-FILE v1 encode on offer / decode on receive; basename jail; hash/length gate; DONE path hashes | F1–F8 offline (F1 is envelope, not raw SEAL bytes) |
| Dumb Python | Listen loop (stdlib socket+ssl) + jail/PSK + CAPA + job path | D1–D10 including D2 no result ciphertext on connector path; truncated spill |
| Skills + installer | Yes | Not asserted in pytest |
| `.NET` | net45 protocol clone `airc-dumb.exe` + `airc-dumb.cmd` | Skip unless `DOTNET_DUMB_EXE` / built exe |
| CI | ubuntu pytest + windows Mode 3 + windows net45 dumb | Tests must not mention `irc.libera.chat` |

Do **not** treat this list as ready for human UAT.

---

## §12.1 Wire (Table 9)

| ID | Expect | Status |
|---|---|---|
| W1 | Each Table 3 verb parses | **Covered** (`test_w1_each_table3_verb`) |
| W2 | lowercase / missing v1 / extra tokens → None | **Covered** (incl. OPEN extra tokens) |
| W3 | FILE OFFER path-like name | **Covered** |
| W4 | DUMB `n=100` → None | **Covered** |
| W5 | CAPA missing `verbs=` | **Covered** |
| W6 | SEAL v2 only via `seal.parse_seal_line` | **Covered** |

## §12.2 Moot (Table 10)

| ID | Expect | Status |
|---|---|---|
| M1 | OPEN + JOIN×2 + ROSTER → roster 3 | **Covered** |
| M2 | non-floor SAY dropped | **Covered** (3-nick + `handle_privmsg`) |
| M3 | FLOOR / SAY / YIELD `*` / CLOSE; further SAY dropped | **Covered** |
| M4 | HANDOFF off-roster | **Covered** |
| M5 | PART by floor holder → floor none | **Covered** |
| M6 | two OPEN same id → first wins | **Covered** |
| M7 | seq not increasing | **Covered** |

## §12.3 File (Table 11)

| ID | Expect | Status |
|---|---|---|
| F1 | Tier S 1 KiB → `complete/` sha256 match | **Covered.** `offer --tier S` wraps `AIRC-FILE v1`; receiver decodes envelope, basename-jails, hash/length-gates, writes `complete/`. |
| F2 | Tier M 20 KiB shuffled | **Covered** |
| F3 | Hash mismatch DONE → no `complete/` | **Covered** via `handle_file` |
| F4 | offer `identity.json` | **Covered** |
| F5 | slash/space name | **Covered** (plus `..` / drive-letter jail on envelope) |
| F6 | second OFFER same id ignored | **Covered** |
| F7 | ABORT mid-bag | **Covered** |
| F8 | disk cap → ACCEPT not sent / refuse | **Covered** (`FILES_HOME_CAP` monkeypatch) |

## §12.4 Dumb (Table 12)

| ID | Expect | Status |
|---|---|---|
| D1 | PSK ping ok | **Covered** (in-process + connector path emits DUMB result) |
| D2 | unknown operator | **Covered.** Connector `handle_privmsg`: no `subprocess.run`, no result ciphertext on the wire. In-process still `error=operator`. |
| D3 | jail escape | **Covered** (`agent-drop\..\Windows\win.ini`, UNC, secret names) |
| D4 | put then get sha256 | **Covered** (asserts `hashlib.sha256(data)`) |
| D5 | exec timeout | **Covered** (`subprocess.TimeoutExpired` monkeypatch) |
| D6 | busy | **Covered** |
| D7 | argv[0] not allowed | **Covered** (split from D5) |
| D8 | meta without `--allow-meta` | **Covered** |
| D9 | prefix ≠ `from_nick` | **Covered** (`handle_dumb` drops) |
| D10 | wrong PSK | **Covered** (`pytest.raises`) |

---

## Appendix C

| # | Criterion | Status |
|---|---|---|
| 1 | pytest -q green + §12 tests | Green; F1 envelope + D2-on-wire asserted |
| 2 | Three skills + installer + safety rules | Present; not pytest-covered |
| 3 | 3-party in-process moot to CLOSE | **Covered** via `handle_privmsg` |
| 4 | 20 KiB tier M + sha256 | **Covered** |
| 5 | Jail + unknown operators | **Covered** (incl. no result on connector wire) |
| 6 | DUMB-PSK Python seal/open | **Covered** |
| 7 | .NET + MSBuild + TLS 1.2 preflight | **Clone present.** net45 `airc-dumb.exe` (SslStream TLS 1.2, CAPA, PSK jobs, jail, D2, truncated spill). Offline via `DOTNET_DUMB_EXE`. Not Bob-MRB'd; not ready for human UAT. |
| 8 | README field kit | Yes; .NET described as net45 clone pending MRB; Python connector is a listen loop |
| 9 | No CI resolves `irc.libera.chat` | Workflow is offline pytest + local exe selftest; tests forbid the hostname |

---

## Remaining PDF items (honest)

Do **not** treat this list as ready for human UAT.

1. **Phase 5 .NET protocol clone** — **Landed in tree** (`src/dumb_dotnet/`, TcpClient+SslStream TLS 1.2, CAPA, PSK DUMB v1 ping/sysinfo/exec/get/put, jail, unknown operator no result ciphertext, truncated spill). Offline tests in `tests/test_dumb_dotnet.py`. Pending Bob MRB. **Not** ready for human UAT. Live Server 2012 Libera is still human/manual.
2. **`FLOOR_IDLE_S`** — skill-only (PDF: optional chair hint in v1).
3. **`YIELD *`** — code sets `floor=None` (state-machine box). Table 3 prose says “* returns it to chair”. Left as-is.
4. **Manual Libera session** (`tests/MANUAL.md` / §12.6) — human-only; not run from this machine.
5. **install_skill / skill text** — not locked by pytest.
6. **AGPK-mode dumb jobs** — connector is PSK (PDF default on the exe). SEAL-v2 job unwrap on the connector is not implemented this pass.

Closed this pass (MRB blockers 1–4):

- Tier S AIRC-FILE v1 envelope encode/decode, basename jail, hash/length gate.
- `dumb_agent.py` connect/join/flood/CAPA/job listen loop (stdlib socket+ssl). Offline-tested via fake socket + `handle_privmsg`.
- D2: unknown operator → no exec + no result ciphertext on the connector path.
- Truncated exec writes `dumb/results/<id>.txt` and `truncated: true`.

## Non-goals (Appendix B) — correctly absent

Group SEAL, DCC, web UI, signed `airc-dumb.exe` from CI, connector as SYSTEM with no jail.

## This dispatch

WP-P5 .NET protocol clone. `pytest -q` green with or without `DOTNET_DUMB_EXE`. **Not** self-declared ready for human UAT.
