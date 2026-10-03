<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/mrb-bob-fleet-tray-follow-cursor-2026-09-19.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - Bob tray hover follows cursor (2026-09-19)

**Repo:** SimonBarnett/agentic_build
**Tip reviewed:** f1f3ac6 / 82234e2 (tray this-machine PASS) + live Watch-BobTray.ps1
**Reporter:** Simon - tray form follows the cursor around the screen

## Verdict

**FAIL**

The dark hover card is not a tray hover. `NotifyIcon.MouseMove` continuously sets `$tip.Location` from `[Cursor]::Position`, so the form chases the mouse across the desktop.

## Evidence (code)

`tools/Watch-BobTray.ps1` (approx lines 306-318):

```powershell
$notify.Add_MouseMove({
    ...
    $pt = [System.Windows.Forms.Cursor]::Position
    $x = $pt.X - $tip.Width
    $y = $pt.Y - $tip.Height - 12
    $tip.Location = New-Object System.Drawing.Point $x, $y
    if (-not $tip.Visible) { $tip.Show() }
    $hideTip.Stop(); $hideTip.Start()
})
```

Every mouse move over the notify icon (and any bubbled move) repositions the borderless TopMost form relative to the **cursor**, not a stable tray-icon anchor. Operator experience: card sticks to / follows the pointer.

Prior MRB `mrb-bob-fleet-tray-retest-2026-09-19.md` PASS covered NC-01..05 (copy, context bar, alert). It did **not** cover hover geometry. This FAIL is additive.

## Required fixes (ordered)

### NC-T01 (blocker) - Stop chasing the cursor

1. On show: position the tip **once** near the system tray / notify icon (or once from the first MouseMove), then **do not** update `Location` on subsequent MouseMove while Visible.
2. Preferred: resolve notify-icon rect (Shell_NotifyIconGetRect / equivalent) and place above-left of the icon; fall back to first-event cursor offset only if rect unavailable.
3. Hide on leave: MouseLeave / timeout (`hideTip`) / click-away. Restarting hideTip on MouseMove is OK; moving the form is not.

### NC-T02 (major) - Do not steal focus / block input

Confirm tip uses ShowWithoutActivation / WS_EX_NOACTIVATE (or equivalent) so hovering does not yank focus from the active window while the card is visible.

### NC-T03 (nit) - Offline regression

Add a small testable helper (e.g. `Get-BobTrayTipPlacement`) covered by Test-Pack: given icon rect + tip size, returns a stable point; given "already visible", placement function is not re-invoked with new cursor coords (document contract in skill `bob-fleet-tray`).

## Pass bar

- Hovering the robot shows a **stationary** card near the tray.
- Moving the mouse within the icon (or across the card if hit-tested) does **not** drag the card around the screen.
- Card still auto-hides on timer; left-click ack still works.
- BT0 / tray tests still green; NC-01..05 copy/bar behaviour preserved.

## Hand-off

Build agent on **ionos**, cwd `C:\ai\agentic_build`: implement NC-T01 (required), NC-T02 if straightforward, NC-T03 test helper. Commit + push. Do not claim ready for human UAT. Leave unrelated ionos jobs alone.
