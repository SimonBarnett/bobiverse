Ergo 2.19.1 (windows-x86_64)
Source: https://github.com/ergochat/ergo/releases/download/v2.19.1/ergo-2.19.1-windows-x86_64.zip
License: see LICENSE in win64/
Bundled for bobiverse jeeves MSI / Install-BobIrcd.ps1.

DESCRIBE ONLY — never edit Ergo config or binaries from a docs/harvest FR.

ergo.password is NOT stored in git. Pack/install paths (first match on the packer
or operator box) supply it into the private install tree under <ai root>\ergo\
or product config\; public MSIs do not embed the live PASS. Place
config\ergo.password post-install (or pack with a private -EmbedErgoPassword
build). See docs/post-install.md.
