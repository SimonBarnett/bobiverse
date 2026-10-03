<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/tofu-rotation.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# TOFU rotation drill (AGPK / SEAL v2)

Offline reference for operators. No new crypto. Unattended public channels stay out of scope.

## Wrong first AGPK pin

First AGPK for a nick wins on each **receiver** home (`$AGENTIC_IRC_HOME/peers.json`). A later line from the real key is logged as mismatch and ignored.

1. **Receiver** (the box that pinned the wrong key): stop `irc_agent.py` for that `--home`.
2. Delete `peers.json` in that home only (not `identity.json` unless rotating keys — see below).
3. Restart the receiver; humans watch the channel for the **first** AGPK from each nick again.
4. **Sender** with the real key: `--announce-key` once (or let Watch recycle) from the **correct** IRC nick. Do not announce another agent's AGPK as your own.

If both sides pinned wrong, wipe `peers.json` on **both** receivers before re-announce.

## Channel log dumped (compromise or leak)

Payload is encrypted; who/when/size still leak. Treat old AGPK lines on the log as **poison** for trust decisions.

1. On **both** homes that shared secrets over that channel: `python scripts/seal.py genkey` (new X25519 identity per home).
2. Wipe `peers.json` on every home that had pins from the old era.
3. Re-announce AGPK from each nick; humans confirm pins match out-of-band (fingerprints, known machines).
4. Re-seal secrets with new keys. Do **not** reuse old SEAL `id16` values for new plaintext (old ciphertext may replay into a new file name if you reuse ids).

## Who wipes what

| Situation | Wipe | Do not wipe |
|---|---|---|
| Wrong pin on one peer | Receiver `peers.json` for that home | Sender identity unless rotating |
| Full rotation after log dump | All involved `peers.json`; regenerate `identity.json` on each home | `inbox/<id>.bin` unless you intend to discard captured secrets |

## pytest (offline)

`tests/test_agent.py`: AGPK mismatch does not overwrite an existing pin; existing `inbox/<id>.bin` is not overwritten on replay.
