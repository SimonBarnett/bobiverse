"""FR #7296 superseded by FR #7326: keep the module importable; assertions live in test_fr7326_."""

from test_fr7326_tray_xai_weekly_layout import (  # noqa: F401
    test_fr7326_catalog_no_cursor_grok_chat_or_free_meter,
    test_fr7326_digest_has_no_fleet_cursor,
    test_fr7326_snapshot_xai_weekly_three_channels_and_workers,
    test_fr7326_tick_does_not_fetch_cursor_or_fixed_free,
    test_fr7326_watch_restores_xai_weekly_heading,
)
