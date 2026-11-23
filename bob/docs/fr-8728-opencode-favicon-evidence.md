# FR #8728 / BOB-31 evidence

Workers > Open Code uses the opencode.ai favicon.

- Source: `https://opencode.ai/favicon-v3.ico` and `https://opencode.ai/favicon-96x96-v3.png`.
- Tray file: `bob/tray/assets/opencode-favicon.ico` (ICO header `00 00 01 00`).
- Compiled log: event `workers-opencode` action `opencode favicon` path `<install>\bob\tray\assets\opencode-favicon.ico`.
- PowerShell log: `Workers Open Code: favicon <bob\tray>\assets\opencode-favicon.ico`.
- Docs: `jeeves/www/irc-ntsa/docs/tray/index.html` image `opencode-favicon.png` alt `opencode.ai favicon`.

`python -m pytest -q bob/tests/test_fr8728_opencode_favicon.py bob/tests/test_fr8735_workers_opencode_cli.py`
