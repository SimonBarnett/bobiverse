# FR #6470: Install-BobWebhooks.ps1 must stay BOM-less ASCII (WinPS 5.1).
from pathlib import Path

from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"


def test_fr6470_install_bobwebhooks_bomless_ascii():
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "Install-BobWebhooks.ps1 must be BOM-less"
    text = raw.decode("ascii")  # raises if non-ASCII
    # FR #6903: missing appcmd still writes web.config; only ARR enable is skipped.
    assert "appcmd.exe missing" in text
    assert "\u2014" not in text
    assert "BobJeevesAppliance" in text
