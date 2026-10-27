# FR #5069 live MarchHare DCC-fail fallback retest

**When:** 2026-10-27 ~14:31 UTC  
**Host:** marchhare (`require_machine=marchhare`)  
**Tip:** `91648f9b` (PR #5068 / FR #5065 unique-seq fix on main)  
**Console:** side-by-side from-source `marchhare_t5069_console` (tip `airc_console_service.py`), production `Airc` 1.0.3 left running as `marchhare_console`.

## Procedure

1. Start tip console with own home (copy `ergo.password`, mint/reuse `console.password`), nick `marchhare_t5069_console`, `--shop-mode registered --machine marchhare`.
2. Drive via bob ear outbox `C:\ai\bob\home\outbox.txt`.
3. Smoke: `PRIVMSG marchhare_t5069_console :id=<id> hostname` -> DONE exit=0.
4. Force DCC fail: `DCCLISTEN id=<jid> host=127.0.0.1 port=1 token=<hex> tls=0` then  
   `id=<jid> 1..200 | % { 'L{0:d4} {1}' -f $_, ('x'*90) }` (200 lines / ~19.6 KB bulk threshold).

## Result (job `b6782a52`)

- 48x `out ... seq=1..48`
- `err ... seq=49 output truncated...`
- **`err ... seq=50 dcc failed: [WinError 10061] ...; falling back to IRC`** (next unused seq, not seq=1)
- `DONE id=b6782a52 exit=0`
- No `via=dcc`

## Parse

`ConvertFrom-AircRemoteReply` (tip `Invoke-AircRemote.ps1`) on the 51-line capture:

- seq count=50, unique=50
- ExitCode=0
- **PASS** (pre-fix shape failed with `duplicate seq=1`)

Artifacts: `retest-replies.txt`, `retest-parse-summary.txt`.

## Notes

- Live install `C:\ai\airc` remains 1.0.3 without the #5068 tree; this retest proves tip behaviour side-by-side before 1.0.4 pack.
- Wrapper launch (`powershell -File` + `*>> log`) kept the from-source console alive; `Start-Process -RedirectStandardOutput` alone saw silent exits after NAMES sync on this box.