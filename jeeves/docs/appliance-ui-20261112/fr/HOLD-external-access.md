# HOLD - external access (not filed)

Do not open a GitHub issue for this draft until the operator says yes.

## Goal

Say whether a non-RFC1918 client may ever reach https://jeeves.ntsa.uk/ .

## Status

UNKNOWN. This pack keeps the LAN gate on every route. No public DNS, no Cloudflare, and no front on bob.ntsa.uk or irc.ntsa.uk.

## If filed later

- Spell the allowed source ranges.
- Keep X-Forwarded-For trust limited to the loopback front door.
- Do not weaken the existing reject_non_lan helpers by default.
