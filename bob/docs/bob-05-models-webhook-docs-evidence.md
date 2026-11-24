# BOB-05 / FR #8702 evidence: bob.ntsa.uk docs models webhook page

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8702  
**Slice:** bob.ntsa.uk docs: models webhook page (Success S1)

## S1

Docs page for ``GET /bob/v1/models``, linked from the webhooks index.

## How measured

1. ``jeeves/www/irc-ntsa/docs/webhooks/models.html`` documents ``/bob/v1/models``.
2. ``jeeves/www/irc-ntsa/docs/webhooks/index.html`` links to ``models.html`` with path ``/bob/v1/models``.
3. Tests assert both HTML files contain the models path.

## Fail-when

Undocumented endpoint (no page / no index link).