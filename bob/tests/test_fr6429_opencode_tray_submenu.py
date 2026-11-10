"""FR #6429: Agents > OpenCode free/paid submenu; child-only BOB_OPENCODE_MODEL."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAY_CS = ROOT / "tray" / "dialogs" / "BobTray.cs"
DEFAULT_JSON = ROOT / "tray" / "config" / "default.json"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
WORKER = ROOT / "scripts" / "bob_worker.py"

FREE_DEFAULT = "opencode/deepseek-v4.1-flash-free"
PAID_DEFAULT = "opencode-go/deepseek-v4-pro"


def test_fr6429_default_json_has_opencode_free_and_paid():
    doc = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    models = doc["models"]
    assert models["opencodeFree"] == FREE_DEFAULT
    assert models["opencodePaid"] == PAID_DEFAULT


def test_fr6429_tray_submenu_tags_and_labels():
    tray = TRAY_CS.read_text(encoding="utf-8")
    assert "AddOpencodeModelSubmenu" in tray
    assert "opencode|free" in tray
    assert "opencode|paid" in tray
    assert "Start free model" in tray
    assert "Start paid model" in tray
    assert 'DefaultOpencodeFreeModel = "%s"' % FREE_DEFAULT in tray
    assert 'DefaultOpencodePaidModel = "%s"' % PAID_DEFAULT in tray
    seed = tray[tray.index("void SeedAgentChoices") : tray.index("void SeedAgentChoices") + 900]
    assert "AddOpencodeModelSubmenu" in seed
    assert 'AddAgentChoice(parent, "opencode", "OpenCode"' not in seed
    assert 'AddAgentChoice(parent, "auto"' in seed
    assert 'AddAgentChoice(parent, "grok"' in seed
    assert 'AddAgentChoice(parent, "cursor"' in seed


def test_fr6429_launch_uses_child_env_block_only():
    tray = TRAY_CS.read_text(encoding="utf-8")
    assert "BuildChildEnvironmentBlock" in tray
    assert "CreateUnicodeEnvironment" in tray
    assert "IDictionary childEnv" in tray
    click = tray[tray.index("void OnAgentChoiceClick") : tray.index("void OnAgentChoiceClick") + 1400]
    assert 'env["BOB_OPENCODE_MODEL"]' in click
    assert "SetEnvironmentVariable(\"BOB_OPENCODE_MODEL\"" not in click
    assert "SetEnvironmentVariable(\"BOB_OPENCODE_MODEL\"" not in tray
    # tray-env.json must not receive the slot model
    launch = tray[tray.index("public static int Launch(string root, string mode, string machine, string agent, IDictionary childEnv") :]
    launch = launch[: launch.index("static IntPtr BuildChildEnvironmentBlock") + 800]
    assert "tray-env.json" not in launch or "never" in tray.lower()
    assert "RememberOpencodeSlotLaunch" in tray
    assert "OpencodeSlotRunning" in tray
    assert "ResolveOpencodeSlotModel" in tray
    assert "tray-models.json" in tray


def test_fr6429_cap_still_two_agent_seats():
    tray = TRAY_CS.read_text(encoding="utf-8")
    assert "MaxWorkers = 2" in tray
    assert "CapRefusal" in tray


def test_fr6429_region_unavailable_surfaces_clear_error():
    tray = TRAY_CS.read_text(encoding="utf-8")
    assert "IsOpencodeModelUnavailableMessage" in tray
    assert "region Global" in tray
    worker = WORKER.read_text(encoding="utf-8")
    assert "format_opencode_model_unavailable_error" in worker
    assert "No substitute model was selected" in worker
    # launch-opencode.ps1 string embeds the clear message
    assert "OpenCode model unavailable:" in worker
    assert "set OpenCode console region to Global" in worker


def test_fr6429_format_helper_region_and_missing():
    sys.path.insert(0, str(WORKER.parent))
    import bob_worker as bw

    region = bw.format_opencode_model_unavailable_error(
        "Error: model not available in your region",
        model=PAID_DEFAULT,
    )
    assert region is not None
    assert PAID_DEFAULT in region
    assert "Global" in region
    assert "No substitute" in region

    missing = bw.format_opencode_model_unavailable_error(
        "provider_model_not_found: nope",
        model="opencode/nope",
    )
    assert missing is not None
    assert "opencode/nope" in missing
    assert "No substitute" in missing

    assert bw.format_opencode_model_unavailable_error("ok run finished") is None
    assert bw.format_opencode_model_unavailable_error("Payment Required 402") is None


def test_fr6429_docs_pin_submenu_and_child_env():
    text = DOCS.read_text(encoding="utf-8")
    assert "FR #6429" in text
    assert "Start free model" in text
    assert "Start paid model" in text
    assert FREE_DEFAULT in text
    assert PAID_DEFAULT in text
    assert "child seat process only" in text or "CreateProcessW" in text
    assert "tray-env.json" in text
    assert "test_fr6429_opencode_tray_submenu.py" in text
    # old FR #6301 "no submenu" sentence must be gone
    assert "OpenCode has `/model`" not in text
    assert "no OpenCode models submenu" not in text.lower()
