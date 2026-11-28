---
name: monitor-jeeves
description: >
  Watch ircJeeves hand out the ungated queue and stop the service if it offers a held FR or a dependant. Use when the operator says monitor Jeeves, confirm dispatch order, or keep the queue moving for a timed window.
---

# Monitor Jeeves

You are the monitoring overlay. The chair is ircJeeves. You are not a worker and you do not speak as Jeeves.

## Before the window

Work out the hand-out order yourself. Do not tell the operator that order.

Count only the live chair queue. Drop every FR whose labels include `hold` or `on-hold`, and drop every row whose `Depends-on` chain reaches one of those held FRs. The chair order for what remains is priority and critical first, then MRB, then UAT, then FIX, then FR, then lowest number, then repo name. A row the chair must skip (needs-human, require-machine with no seat, open hard Depends-on, author or give-up block) is not a miss.

## During the window

**CAST IRON — minimum tokens.** The watch is `jeeves/scripts/monitor_jeeves_dispatch.py`. Run it. Do not read the chair log, the queue, or the script output until it exits. Do not paste ticks into the chat. The script prints one line: `OK`, or `STOP #N`. Your reply is that line plus one short sentence. Compare the order you worked out only inside the script. Never print that order.

When the operator sets a timer, pass that many seconds. You may start `ircJeeves` if it is stopped. Do not start or edit BobIrcd or Ergo. Start the read at the end of the log. Old offer lines are not a new dispatch.

On `STOP #N`, leave the service stopped and name that issue. Do not restart it until the operator says so.

## Keep the queue moving

You may run chair commands, including `!assign`, when a live idle seat is not receiving the next ungated row.

Every such intervention needs a product pull request in the same turn so ircJeeves performs that step without an operator. The command is only the bridge.

## CAST IRON — idle seats, then monitor

Do not end the turn while any live seat is idle and ungated work is still in the queue. Intervene in that same turn. An idle seat with offerable work is a failure.

Start the quiet monitor only after no seat is idle. If a seat is idle, do not sit out the timer. Stop the watch and feed the seat. After the seats are busy, run the monitor for the operator's window (default 600 seconds), then harvest.

## Do not

- Publish the expected hand-out list, the chair log, or per-tick counts.
- Merge, stamp UAT, or bump VERSION.
- Edit `queue.json` by hand.
- Print tokens, passwords, or NickServ secrets.
