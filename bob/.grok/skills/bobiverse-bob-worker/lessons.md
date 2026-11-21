# bobiverse-bob-worker archived intake bullets

Moved so SKILL.md stays under the 65536-byte skill-dag cap (MRB #8632).

- OpenCode auto-select dialog can report opencode.exe missing while resolve_opencode_cmd finds %LOCALAPPDATA%\Programs\opencode\opencode.exe; explicit --agent opencode still starts --- make dialog use the same resolve path (FR #8412).
- When flamingo cannot SMB to redqueen, use WinRM hostname redqueen with admin creds; copy CI bob-worker artifact to C:\ai\bob\worker then restart OpenCode seats so LocalAppData run-copy unpacks opencode_seat_contract. recycleseat.disabled only blocks ear !recycleseat; hung --describe-launch blocks the tray startworker timer.
