<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/ergo-chanserv-enable-bob-shops.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Ionos action: enable ChanServ so bob-* REGISTER shop channels (FR #313)

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/313  
**Code (already on main):** `scripts/shop_chanserv.py`, `irc_agent._maybe_register_shop_chanserv`  
**Who acts:** **ionos** (Ergo / `BobIrcd`). Other boxes only need a bob ear recycle after Ergo is on.

## Problem

Shop channels (`#ionos`, `#flamingo`, `#marchhare`, `#ce-priority-dev1`, …) are
**ephemeral** while Ergo channel registration is off. Op only goes to the nick
that creates an empty room; when the room empties, founder/op is gone. `bob-*`
then gets numeric **482** on KICK (`INFO shop-op 482 not channel operator`).

## Goal

1. Ergo on ionos accepts **NickServ** accounts and **ChanServ** channel registration.
2. Each `bob-{machine}` ear **REGISTER**s its own `#{machine}` after JOIN so
   founder/op **persists** when the shop empties.

## CAST IRON — ionos Ergo yaml

Service **`BobIrcd`** runs `C:\ai\ergo\ergo.exe` (NSSM, Automatic, LocalSystem).
Edit the **live** Ergo ircd config that process loads (typically under
`C:\ai\ergo\` — confirm with NSSM `AppDirectory` / `AppParameters` if unsure).

Set (or merge) at least:

```yaml
accounts:
  authentication-enabled: true
  registration:
    enabled: true   # bob-* NickServ REGISTER / IDENTIFY (PASS-gated private net)

channels:
  registration:
    enabled: true   # ChanServ REGISTER #{machine}
```

Then recycle Ergo:

```powershell
Restart-Service BobIrcd
# Confirm dual-stack LISTEN on 6697 and TLS CN=irc.ntsa.uk
```

Do **not** start the removed task `BobIrcd-ionos`.

### Verify services are up (Halloy as simon)

```
/msg ChanServ HELP
/msg NickServ HELP
/msg ChanServ INFO #ionos
```

- ChanServ/NickServ must answer (even `Channel #ionos is not registered.` is OK).
- No reply / unknown command ⇒ wrong config file or registration still disabled.

## After Ergo is on — recycle bob ears

Each box on current `agentic_irc` **main** (FR #313 already merged):

1. Pull + recycle **Watch-Bobiverse** / `bob-{machine}` only (skill `bob-irc`).
   **CAST IRON (Simon 2026-09-29):** `{machine}` is Windows `COMPUTERNAME`
   lowercased (`BOB_MACHINE_ID`), not a marketing alias. Host
   `WIN-MPRE8VI4U6U` → `bob-win-mpre8vi4u6u` / `#win-mpre8vi4u6u`.
2. In that bob home `irc.log` (with `AGENTIC_IRC_DEBUG=1` if needed), expect:

   ```text
   INFO chanserv REGISTER #win-mpre8vi4u6u
   ```

   (or that box's real `#{machine}`).

What the ear does (automatic):

1. Mint/reuse `<bob-home>/nickserv.password` (or env `AGENTIC_IRC_NICKSERV_PASSWORD`).
2. Best-effort `NickServ IDENTIFY` then `REGISTER` for `bob-{machine}`.
3. `PRIVMSG ChanServ :REGISTER #{machine}` — **own shop only**.

Talk seats, `w-*`, and humans do **not** ChanServ-register.

### Confirm founder

```
/msg ChanServ INFO #win-mpre8vi4u6u
/msg ChanServ INFO #flamingo
/msg ChanServ INFO #marchhare
/msg ChanServ INFO #ce-priority-dev1
```

Founder should be the matching `bob-*` (first successful REGISTER while in-channel
with a services account **and channel op**).

If ChanServ says `You must be an oper on the channel to register it`: clear
other nicks briefly so `bob-{machine}` is **first JOIN** (gets `@`), then
REGISTER. If still **not registered**: recycle that bob while it is in the
shop (empty or with op). First REGISTER wins founder.

## Manual REGISTER (fallback only)

Only if a bob missed auto-REGISTER. Nick must be **logged into NickServ** and
present in the channel:

```
/msg ChanServ REGISTER #ionos
```

Prefer recycling `bob-ionos` so founder stays on the ear.

## Out of scope

- Transferring existing channel ownership.
- Oper `NickServ SAREGISTER` of every historical nick (only needed if account
  self-registration stays disabled — prefer enabling `accounts.registration`).
- Changing shop KICK policy beyond ChanServ founder persistence.

## Related

- FR text: `docs/feature-request-bob-chanserv-register-shop-2026-09-29.md`
- Ionos shop note: `docs/bobiverse-ionos-ircd.md`
- Skills: `bob-irc` (Ergo / BobIrcd), `agentic-irc` (shop ops / FR #313)
