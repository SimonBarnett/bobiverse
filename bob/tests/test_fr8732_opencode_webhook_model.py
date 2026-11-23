"""FR #8732 / BOB-30: Workers > Open Code launch cites Opencode webhook rows."""
import subprocess

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
FIXTURE = REPO / "bob" / "tests" / "fixtures" / "models-catalog-opencode.json"


def test_opencode_click_cites_webhook_rows():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert "OpencodeWebhookModel" in cs
    assert '"Opencode-Free"' in cs
    assert '"Opencode"' in cs
    assert '"webhook model"' in cs
    assert "BOB_OPENCODE_MODEL" in cs
    assert "Workers Open Code: webhook model" in ps
    assert "'Opencode-Free'" in ps
    assert "Get-BobTrayOpencodeWebhookModel" in ps
    assert "-Model $model" in ps or "-Model $ocModel" in ps


def test_fixture_returns_opencode_rows_not_grok():
    watch = WATCH.read_text(encoding="utf-8-sig")
    start = watch.find("function Get-BobTrayOpencodeWebhookModel {")
    end = watch.find("function Update-BobTrayWorkerAgentsMenu {", start)
    fn = watch[start:end]
    script = fn + (
        "\nWrite-Output (Get-BobTrayOpencodeWebhookModel -CatalogPath '%s' -AgentName 'Opencode')"
        "\nWrite-Output (Get-BobTrayOpencodeWebhookModel -CatalogPath '%s' -AgentName 'Opencode-Free')"
    ) % (str(FIXTURE), str(FIXTURE))
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines == ["opencode-go/deepseek-v4-pro", "opencode/deepseek-v4.1-flash-free"]
