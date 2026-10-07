what: Plan seat reading Trutex Deposco xlsx on M:\ hung Excel COM (~5+ min, no output).
where: C:\ai\bob\plan work folder; source M:\docs\trutex\deposco\*.xlsx
evidence: COM Workbooks.Open/SaveAs stuck; Copy-Item to plan work folder + pip openpyxl 3.1.5 exported 14 sheets in seconds.
fix: For plan-seat workbook → CSV: Copy-Item xlsx into work\plan-*\ then openpyxl load_workbook data_only + csv.writer per sheet; avoid Excel COM on network paths. Install openpyxl if missing. Never commit secrets.
---
_via-intake id=`in_479651acde5b488e` ts=`2026-10-07T10:53:40Z`_
_source machine=`marchhare` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_
