# FR #8987 / BOB-HOVER-XAI evidence

NotifyIcon hover shows this machine's **xAI weekly** remaining % equal to the Status/Usage `Format-BobTrayXaiWeeklyRow` `remaining_pct`, labeled **xAI** (never **SG**).

## Changes
- `Get-BobTrayHoverXaiPoolLabel`: SuperGrok / empty / SG → `xAI`; Premium → `P+`.
- `Format-BobTrayHoverXaiShort`: builds NotifyIcon.Text (≤63) with that label and the Status %.
- Hover `remainPct` takes digest `machines.<id>.xai_weekly.remaining_pct` even when stale (same as Status last %).

## Test
`python -m pytest -q bob/tests/test_fr8987_hover_xai_weekly_match_usage.py`
