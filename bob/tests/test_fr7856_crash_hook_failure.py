# -*- coding: utf-8 -*-
"""FR #7856: tray crash-hook failure must keep the exception, not a bare line."""
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "tray" / "dialogs" / "CrashHook.cs"


def test_fr7856_hook_failure_body_includes_hook_and_original():
    text = SRC.read_text(encoding="utf-8")
    catch = text.split("catch (Exception hookEx)", 1)[1].split("public static void FlushSpool", 1)[0]
    assert 'Redact("crash hook failed")' not in catch
    assert "crash hook failed: " in catch
    assert "original: " in catch
    assert "SafeExceptionMessage(hookEx)" in catch
    assert "SafeExceptionMessage(ex)" in catch
    assert "hookfail-" in catch
