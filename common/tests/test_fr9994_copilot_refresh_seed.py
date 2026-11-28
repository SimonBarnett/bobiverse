"""FR #9994: refresh seeds Copilot even when the client omits it."""
import models_refresh as mr


def test_fr9994_seed_includes_haiku():
    clis = {}
    status = mr.seed_copilot_on_refresh(clis, "2026-11-27T00:00:00Z")
    assert status == "seeded"
    ids = [m.get("model") if isinstance(m, dict) else m for m in clis["copilot"].get("models") or []]
    # merge_cli_models stores model ids; accept either list of str or dicts
    flat = []
    for item in clis["copilot"].get("models") or []:
        if isinstance(item, str):
            flat.append(item)
        elif isinstance(item, dict):
            flat.append(str(item.get("model") or item.get("id") or ""))
    assert "claude-haiku-4.5" in flat
