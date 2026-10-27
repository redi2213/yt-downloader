import re

import pytest

from core import config, fa_strings, i18n


@pytest.fixture(autouse=True)
def english_after_each_test():
    i18n.set_language("en")
    yield
    i18n.set_language("en")


def test_english_is_untouched():
    assert i18n.tr("Settings") == "Settings"


def test_persian_exact_pattern_and_phrase():
    i18n.set_language("fa")
    assert i18n.tr("Settings") == fa_strings.EXACT["Settings"]
    assert "3" in i18n.tr("Selected: 3 of 10")
    assert i18n.tr("Last check: 10:00") != "Last check: 10:00"
    assert i18n.tr("Totally unknown sentence") == "Totally unknown sentence"
    assert i18n.tr(5) == 5


def test_whitespace_and_lines_are_kept():
    i18n.set_language("fa")
    out = i18n.tr("  Settings\n")
    assert out.startswith("  ") and out.endswith("\n")
    assert "\n" in i18n.tr("Settings\nBack")


def test_every_pattern_compiles_and_uses_existing_groups():
    for pattern, template in fa_strings.PATTERNS:
        rx = re.compile(pattern)
        used = [int(n) for n in re.findall(r"\{(\d+)\}", template)]
        assert all(n < rx.groups for n in used), (pattern, template)


def test_no_empty_translations():
    assert all(v.strip() for v in fa_strings.EXACT.values())


def test_new_texts_and_about_note_are_translated():
    for key in ("Paste any link here", "Go", "Paste a link first"):
        assert key in fa_strings.EXACT
    assert "7 days" in config.ABOUT_TEXT_TEMPLATE
    assert "Note: video files are auto-deleted after 7 days" in fa_strings.EXACT
