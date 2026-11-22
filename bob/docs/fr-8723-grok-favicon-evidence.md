# FR #8723 / BOB-19 evidence

Workers > Grok uses the grok.com favicon, not a generic icon.

- Source: `https://grok.com/images/favicon.ico` and `https://grok.com/images/android-chrome-192x192.png`.
- Tray file: `bob/tray/assets/grok-favicon.ico`
- Compiled log: event `workers-grok` action `grok favicon` path `<install>\bob\tray\assets\grok-favicon.ico`
- PowerShell log: `Workers Grok: favicon <bob\tray>\assets\grok-favicon.ico`
- Docs: `jeeves/www/irc-ntsa/docs/tray/index.html` image `grok-favicon.png`

`python -m pytest -q bob/tests/test_fr8723_grok_favicon.py`
