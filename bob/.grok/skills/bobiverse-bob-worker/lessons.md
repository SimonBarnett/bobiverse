# bobiverse-bob-worker archived intake bullets

Moved so SKILL.md stays under the 65536-byte skill-dag cap (MRB #8632).

- OpenCode auto-select dialog can report opencode.exe missing while resolve_opencode_cmd finds %LOCALAPPDATA%\Programs\opencode\opencode.exe; explicit --agent opencode still starts --- make dialog use the same resolve path (FR #8412).
- When flamingo cannot SMB to redqueen, use WinRM hostname redqueen with admin creds; copy CI bob-worker artifact to C:\ai\bob\worker then restart OpenCode seats so LocalAppData run-copy unpacks opencode_seat_contract. recycleseat.disabled only blocks ear !recycleseat; hung --describe-launch blocks the tray startworker timer.
- FR #8999: ``opencode-ready: blocked gh_auth_missing`` on a host means the Windows user that runs seats must ``gh auth login -h github.com`` (or restore a working gh cred for that user). ``gh_auth_blocks`` treats Failed to log in / re-authenticate / invalid token as blocked even when Active account is true (stale hosts.yml entry). Never invent GH_TOKEN, never read hosts.yml or credential stores from a seat. A seat on another machine ACKs then GIVEUPs ``needs_human`` / operator-on-host; while OC is blocked, stamp ``empty-fill.txt`` so empty-online fill does not race auto-grok (related #9000).
