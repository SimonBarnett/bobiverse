"""FR #994 detect helpers remain; inject-to-agent policy superseded by FR #2554.

See test_fr2554_nothing_queued_no_inject.py for CAST IRON skip-not-inject coverage.
"""
from __future__ import annotations

import bob_worker as bw

# Re-export helper tests used by older suites via this module name historically.
from test_fr2554_nothing_queued_no_inject import (  # noqa: F401
    test_is_nothing_queued_helper,
    test_relay_skips_nothing_queued_not_injected,
    test_relay_still_injects_real_assign,
)
