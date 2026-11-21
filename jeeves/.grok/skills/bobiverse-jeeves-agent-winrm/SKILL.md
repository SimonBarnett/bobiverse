---
name: bobiverse-jeeves-agent-winrm
description: >
  Jeeves agent: check and (only if missing) enable WinRM / PSRemoting on fleet Windows machines, one machine at a
  time. Read-only check first (service, listeners, firewall rules per profile, NIC profile, Test-WSMan local and from
  redqueen by IP and by name) with a saved before-state, minimal enable with a ROLLBACK.ps1, known fleet pitfalls
  (two-NIC MarchHare, stale DNS A record, walrus Public profile, Avast on joker, unreachable joker/newver, Ubuntu n/a),
  and the per-machine report. Use for "can we remote to X", Test-WSMan failures, PSSession errors, or /bobiverse-jeeves-agent-winrm.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-winrm

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, credential, key, private IP or private hostname in a filing, a skill, IRC or a log.

Jeeves agent skill (BOB-38 #8682). Distilled from the fleet WinRM run of 21 Nov 2026. Every other Jeeves agent skill
that touches a remote machine (install, rollback, monitor from redqueen) relies on PSRemoting working; this node is
how to prove it does, and how to fix it minimally when it does not. Machine addresses are written as placeholders
(`<host-ip>`); read the real values live, never from memory.

## Rules

- **One machine at a time.** Check, (maybe) enable, verify, report; then the next machine.
- **Read-only first.** Always capture the before-state before any change. No change if WinRM already works.
- **Never invent access.** An unreachable machine is reported as unreachable with the evidence; do not try other
  credentials, other routes, elevation tricks, or sign-in files copied from another seat.
- **Never:** set `TrustedHosts` to `*`; touch `LocalAccountTokenFilterPolicy`; change GPO / domain policy; change a
  customer's security policy; force a **Public** network to Private; disable or reconfigure antivirus (Avast);
  reboot; read or print credentials or any passwords folder.
- Always `Remove-PSSession` in `finally`. Never launch anything into session 0 or start seats/trays.
- Changes need Si's go for that machine. DNS changes (walrus DNS only) need Si's explicit OK, with a backup and rollback.

## 1. Check (read-only, on the target, elevated read where needed)

```powershell
$d = "C:\ai\_winrm-$(Get-Date -Format yyyyMMdd-HHmmss)"; New-Item -ItemType Directory -Force $d | Out-Null
$svc  = Get-Service WinRM | Select-Object Status, StartType
$lst  = winrm enumerate winrm/config/listener 2>&1 | Out-String
$fw   = Get-NetFirewallRule -Name 'WINRM-HTTP-In-TCP*' -ErrorAction SilentlyContinue |
        Select-Object Name, Profile, Enabled, Action
$nic  = Get-NetConnectionProfile | Select-Object InterfaceAlias, NetworkCategory, IPv4Connectivity
$wsl  = try { [bool](Test-WSMan localhost -ErrorAction Stop) } catch { $_.Exception.Message }
"$svc`n$lst`n$($fw | Out-String)`n$($nic | Out-String)`nTest-WSMan localhost: $wsl" | Set-Content "$d\before.txt"
[ordered]@{ service = $svc; firewall = $fw; nic = $nic; listener_present = ($lst -match 'Transport = HTTP') } |
  ConvertTo-Json -Depth 4 | Set-Content "$d\before-state.json"
```

Then from **redqueen** (the operator host), both ways:

```powershell
Test-WSMan <host-ip>           # by IP
Test-WSMan <hostname>          # by name
Resolve-DnsName <hostname>     # compare the A record(s) with the target's real addresses (Get-NetIPAddress on target)
```

Classify: **OK** (both pass), **name-only fail** (IP passes, name fails -> DNS), **blocked** (local WSMan ok, remote
fails -> firewall/profile/NIC), **off** (no listener / service stopped), **unreachable** (no route), **n/a** (not Windows).

## 2. Enable (only the missing pieces)

- Service stopped or no listener: `Enable-PSRemoting -Force` from an **elevated** shell. On MarchHare the agent shell is
  not elevated: either Si clicks the UAC prompt, or a one-shot SYSTEM scheduled task that runs exactly this command and
  deletes itself. No other elevation route.
- If `Enable-PSRemoting` refuses because a NIC is on the Public profile, stop and report it. Do not add
  `-SkipNetworkProfileCheck` or change the profile without Si's explicit OK for that machine.
- `Enable-PSRemoting` may enable firewall rules broadly; afterwards make sure only the **Domain/Private** WinRM rule is
  newly enabled, matching the NIC profile. Do not newly enable the Public rule unless the before-state already had it.
- Write `ROLLBACK.ps1` in the same folder before the change. It reads `before-state.json` and restores the service
  StartType/state and each firewall rule's `Enabled` value; it removes the listener only if `listener_present` was false.
- Verify: `Test-WSMan localhost`, then from redqueen by IP and by name, then a real
  `New-PSSession` / `Invoke-Command { hostname }` / `Remove-PSSession` round trip.

## Known pitfalls (fleet, 21 Nov 2026)

| Machine / class | Pitfall | What to do |
|---|---|---|
| MarchHare | Two NICs; only one of its addresses accepts inbound WinRM | Test by each address; report which one works; target that one. Do not "fix" the other NIC's profile |
| Stale DNS A record | `Test-WSMan <name>` fails while `Test-WSMan <ip>` passes | Compare `Resolve-DnsName` with the target's real address. Fix only on walrus DNS, only with Si's OK: export the record first, write a ROLLBACK, change only that A record |
| walrus | NIC is on the **Public** profile, yet WinRM works because the Public WinRM rule is already on | Leave it. Never flip the profile to Private |
| madhatter, whiterabbit | Ubuntu, no WinRM | Mark **n/a** (use SSH skills instead) |
| joker, newver | Not reachable from the home LAN (newver is behind joker on another network) | Mark **unreachable**; never invent a route |
| joker | Avast may block WinRM/firewall changes | Report the block with evidence; never disable or reconfigure Avast |
| flamingo -> MarchHare | SMB (`\\marchhare\c$`) hangs | Do not use SMB to stage files there; use `Copy-Item -ToSession` over PSRemoting from redqueen |
| any | Reboot would "fix it" | No reboots. Report instead |

## Output (per machine, one row each)

| Machine | WinRM svc / StartType | Listener | FW rule (profile: on/off) | NIC profile | Local WSMan | From redqueen by IP | by name | Change made | ROLLBACK path | Result |
|---|---|---|---|---|---|---|---|---|---|---|

Use placeholders or names in shared reports; never paste private IPs into issues, IRC or skills.

## Escalate

- Unreachable, Avast-blocked, needs UAC, or DNS fix needed: report to Si with the evidence and the exact proposed
  change; stop there for that machine.
- Never claim access works without the `New-PSSession` round trip in the same pass.

## Verify / stop rules

- Done for a machine when its row is filled from observed output, before-state files exist, and either no change was
  needed or the change plus ROLLBACK.ps1 is in place and remote checks pass.
- Any unexpected policy, GPO or security-product state: stop, report, change nothing.
