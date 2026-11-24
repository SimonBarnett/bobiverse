"""FR #8725 / BOB-17 + FR #9586: Workers > Grok launch cites Weights GET /bob/v1/models."""
import subprocess
from pathlib import Path

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
WEBHOOK = REPO / "bob" / "tray" / "src" / "Private" / "Get-BobModelsWebhook.ps1"
FIXTURE = REPO / "bob" / "tests" / "fixtures" / "models-catalog-grok.json"


def test_grok_click_cites_webhook_model():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert '"webhook model"' in cs
    assert "ResolveAgentLaunchRow" in cs or "WeightsLaunchField" in cs
    assert "source" in cs and "models-webhook" in cs
    assert "BOB_GROK_MODEL" in cs
    assert "BOB_GROK_EFFORT" in cs
    assert "Workers Grok: webhook model" in ps
    assert "source=models-webhook" in ps
    assert "Get-BobTrayWeightsLaunchField" in ps
    assert "-Model $model" in ps
    assert "-Effort $effort" in ps
    assert "-Context $context" in ps
    assert "weights-model-missing" in ps


def test_fixture_returns_grok_row_not_cursor():
    """Offline fixture path still resolves Grok model (catalog fallback)."""
    script = (
        ". '%s'\n"
        "$row = Get-BobModelsWebhookAgentRow -AgentId 'Grok' -FixturePath '%s'\n"
        "Write-Output ([string]$row.model)\n"
    ) % (str(WEBHOOK).replace("'", "''"), str(FIXTURE).replace("'", "''"))
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "grok-4"
