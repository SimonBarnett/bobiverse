"""FR #9053 / BOB-WEIGHTS-NO-VALIDATE: no Validate button; no client POST validate."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import REPO

WEIGHTS = REPO / "bob" / "tray" / "dialogs" / "WeightsForm.cs"
CLIENT = REPO / "bob" / "tray" / "dialogs" / "BobModelsClient.cs"
TRAY_DIALOGS = REPO / "bob" / "tray" / "dialogs"
MOCK = REPO / "bob" / "docs" / "mocks" / "systray-agents-workers" / "weights.html"
MOCK_HOME = REPO / "bob" / "docs" / "mocks" / "weights-no-validate" / "home.html"


def _strip_cs_comments(text: str) -> str:
    # Drop // line comments so documentary mentions do not fail the grep.
    return re.sub(r"//.*?$", "", text, flags=re.M)


def test_fr9053_weights_form_has_no_validate_button():
    text = _strip_cs_comments(WEIGHTS.read_text(encoding="utf-8-sig"))
    assert 'Text = "Validate"' not in text
    assert "weightsValidate" not in text
    assert 'Text = "Save"' in text
    assert 'Text = "Cancel"' in text
    assert "models/validate" not in text
    assert "GET|PUT /bob/v1/models" in text
    assert "BobModelsClient.Get" in text
    assert "BobModelsClient.Save" in text


def test_fr9053_models_client_get_put_only():
    text = _strip_cs_comments(CLIENT.read_text(encoding="utf-8-sig"))
    assert "models/validate" not in text
    assert 'Method = "GET"' in text
    assert 'Method = "PUT"' in text
    assert 'Method = "POST"' not in text
    assert 'ModelsPath = "/bob/v1/models"' in text


def test_fr9053_tray_dialogs_grep_clean_of_models_validate():
    hits: list[str] = []
    for path in TRAY_DIALOGS.glob("*.cs"):
        raw = _strip_cs_comments(path.read_text(encoding="utf-8-sig"))
        if "models/validate" in raw:
            hits.append(path.name)
    assert hits == []


def test_fr9053_weights_mock_matches_no_validate_chrome():
    mock = MOCK.read_text(encoding="utf-8")
    home = MOCK_HOME.read_text(encoding="utf-8")
    assert "GET|PUT /bob/v1/models" in mock
    assert 'class="bad">Validate</span>' in mock  # struck-through note only
    assert ">Save</button>" in mock
    assert ">Cancel</button>" in mock
    assert "Agent" in mock and "Effort" in mock
    assert "GET|PUT /bob/v1/models" in home
