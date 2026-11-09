"""Build-time source commit for bob-worker.exe (FR #6349).

Build-BobWorker.ps1 -SourceCommit writes a shadow copy of this module into the
PyInstaller path so the frozen exe embeds the checkout SHA. Source checkouts
keep SOURCE_COMMIT = "unknown" so ``bob-worker --version`` still works without
a freeze. Do not put secrets here.
"""

SOURCE_COMMIT = "unknown"
