"""FR #9992: classify a public models PUT probe. Does not call live IIS."""


def classify_models_put_probe(status: int, body: str, content_type: str = "") -> str:
    """JSON 400 agents-must-be-a-list means BobCallback saw the PUT.

    HTML, empty 403, or 404 means IIS did not forward (web.config stale).
    """
    text = body or ""
    ctype = (content_type or "").lower()
    if status == 400 and "agents must be a list" in text:
        return "forwarded"
    if status == 404 or "text/html" in ctype or text.lstrip().startswith("<"):
        return "not-forwarded"
    if status == 403 and not text.strip():
        return "not-forwarded"
    return "other"


def test_json_400_is_forwarded():
    assert classify_models_put_probe(400, '{"error":"agents must be a list"}', "application/json") == "forwarded"


def test_html_404_is_not_forwarded():
    assert classify_models_put_probe(404, "<html>404</html>", "text/html") == "not-forwarded"


def test_empty_403_is_not_forwarded():
    assert classify_models_put_probe(403, "", "") == "not-forwarded"
