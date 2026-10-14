"""Windows-safe text kwargs for subprocess (FR #3943).

On Windows, ``subprocess`` ``text=True`` without ``encoding=`` uses the
locale codec (often cp1252) with strict errors. Child stdout that contains
byte ``0x9d`` (undefined in cp1252; common inside UTF-8) raises
``UnicodeDecodeError`` inside ``subprocess._readerthread`` and crash-hooks
``bob-ear``.

Prefer::

    subprocess.run(..., capture_output=True, **subprocess_utf8.TEXT)

or add ``encoding="utf-8", errors="replace"`` next to every ``text=True``.
"""

from __future__ import annotations

TEXT: dict[str, object] = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}
