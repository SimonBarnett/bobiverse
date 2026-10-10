# Channel privileges and worker list (v0.1.18)

Both are enforced chair-side by Jeeves. They are deterministic, need no token, and never touch the Ergo config
(Jeeves only sends ordinary `MODE` lines, or `SAMODE` when it is an IRC operator and not +o in the channel).

## Privilege rules (`scripts/chan_privs.py`)

1. Jeeves holds +o in `#bobiverse`, `#wonderland` and in every machine channel (existing upkeep, now retried at once when it loses ops).
2. The ear `bob-<machine>` of a registered machine gets +o in its own `#<machine>`, +o in `#wonderland` (FR #3834), and +h in `#bobiverse`.
   `*_console` and worker/seat nicks never match `bob_machine` and are never opped (including in `#wonderland`).
3. Simon gets +o only while logged in to a NickServ account listed in `BOB_OP_ACCOUNTS`. The account must be learned
   this session from `extended-join`, `account-notify`, `account-tag` or `WHOIS` (numeric 330). A nick alone never earns ops:
   `simon` without a matching account is not granted, and de-opped if it holds +o. Logging out revokes what Jeeves granted.

Re-applied on JOIN, on every MODE change in the channel (drift), and on a periodic `NAMES` reconcile (every 60 s).
Every decision is logged: `INFO chan-privs GRANT|REVOKE ...`, `WARN chan-privs cannot ...`.

### Setup (manual, Simon) — Jeeves ops in `#wonderland` (FR #3834 / MRB #3840)

Never edit Ergo `ircd.yaml`. After `#wonderland` is ChanServ-registered with Simon as founder:

```
/msg ChanServ FLAGS #wonderland Jeeves +Oo
```

That gives Jeeves auto-op so it can `MODE #wonderland +o bob-<machine>` for Bob ears. Airc clients stay plain members.

Config (first match wins): env `BOB_OP_ACCOUNTS` (comma list) > `<config>/op-accounts.txt` (one per line, `#` comments;
written by `Install-Jeeves.ps1 -OpAccounts simon`) > `JEEVES_OWNER_ACCOUNT` > default `simon`.
`BOB_OP_NICKS` (default `simon`) names the nicks that are de-opped when unverified. The startup log line says which
source was used and flags the default as needing Simon's value.

## Worker list (`scripts/chan_workers.py`, ops in `bobreport.apply_callback`)

`machines.<id>.workers = [{nick, state: "doing"|"idle", work, updated}]`, maintained by Jeeves through the
`/bob/v1/report` ops `worker-upsert`, `worker-remove`, `worker-work` (same no-secret + registered-machine gate as every
report op; `bob-*`, `*_console`, `jeeves`, `simon` and IRC services are never workers).
`!bored` in `#<machine>` adds the speaker; ACK sets doing + description; DONE/NACK/GIVEUP set idle;
PART/KICK/QUIT/NICK and the periodic NAMES reconcile remove nicks that left. The tray shows one `{nick}: {doing|idle}` line per worker.
