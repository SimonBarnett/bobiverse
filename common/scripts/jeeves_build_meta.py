"""Build-time source commit for jeeves.exe (FR #6395).

Build-Jeeves.ps1 -SourceCommit writes a shadow copy of this module into the
PyInstaller path so the frozen exe embeds the checkout SHA. Source checkouts
keep SOURCE_COMMIT = "unknown" so ``jeeves.exe --version`` still works without
a freeze. Do not put secrets here.
"""

SOURCE_COMMIT = "unknown"
