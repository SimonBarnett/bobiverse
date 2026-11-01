"""FR #5874: harvest lesson tips must not land literal JSON escape backslashes."""

from __future__ import annotations

import intake


def test_unescape_harvest_lesson_strips_json_quote_escapes():
    mangled = r'Never normalize repo paths with lstrip(\"./\") --- strip only ./'
    clean = intake.unescape_harvest_lesson_text(mangled)
    assert r'lstrip(\"./\")' not in clean
    assert 'lstrip("./")' in clean


def test_unescape_harvest_lesson_replaces_emdash_with_ascii():
    raw = "wait_s>0 so DONE is not blocked\u2014async join"
    clean = intake.unescape_harvest_lesson_text(raw)
    assert "\u2014" not in clean
    assert "---" in clean


def test_extract_harvest_lessons_unescapes_before_return():
    body = (
        "Session summary:\nx\n\nLessons:\n"
        r'- Never normalize with lstrip(\"./\") --- keep the dot'
        "\n"
    )
    lessons = intake.extract_harvest_lessons(body)
    assert lessons == ['Never normalize with lstrip("./") --- keep the dot']
    assert r'lstrip(\"./\")' not in lessons[0]


def test_apply_lessons_to_skill_md_rejects_mangled_needle():
    existing = "# Harvest\n\n## Harvested lessons (intake)\n\n- older tip\n"
    mangled = r'Never normalize repo paths with lstrip(\"./\") --- strip only ./'
    out = intake.apply_lessons_to_skill_md(existing, [mangled])
    assert r'lstrip(\"./\")' not in out
    assert 'lstrip("./")' in out
    assert "\u2014" not in out
