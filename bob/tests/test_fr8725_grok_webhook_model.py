"""FR #8725 / BOB-17: Workers > Grok launch cites the models webhook row."""
import subprocess

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
FIXTURE = REPO / "bob" / "tests" / "fixtures" / "models-catalog-grok.json"


def test_grok_click_cites_webhook_model():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert '"webhook model"' in cs
    assert 'GrokWebhookModel' in cs
    assert 'BOB_GROK_MODEL' in cs
    assert "Workers Grok: webhook model" in ps
    assert "-Model $model" in ps


def test_fixture_returns_grok_row_not_cursor():
    watch = WATCH.read_text(encoding="utf-8-sig")
    start = watch.find("function Get-BobTrayGrokWebhookModel {")
    end = watch.find("function Update-BobTrayWorkerAgentsMenu {", start)
    fn = watch[start:end]
    script = fn + "\nWrite-Output (Get-BobTrayGrokWebhookModel -CatalogPath '%s')" % str(FIXTURE)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "grok-4"
