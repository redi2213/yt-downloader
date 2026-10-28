import pytest

from core import i18n
from core import version_check as vc


def test_parse():
    assert vc.parse("2.25") == (2, 25) and vc.parse("v2.25") == (2, 25)
    assert vc.parse("2.25-dev.7") == (2, 25) and vc.parse("3") == (3, 0)
    assert vc.parse("") is None and vc.parse("garbage") is None


def test_compare_is_numeric_not_text():
    assert vc.compare("2.24", "2.25") == "newer"
    assert vc.compare("2.9", "2.10") == "newer"
    assert vc.compare("2.25", "2.25") == "same"
    assert vc.compare("2.25-dev.7", "2.25") == "same"
    assert vc.compare("2.26", "2.25") == "older"
    assert vc.compare("", "2.25") == "unknown" and vc.compare("2.25", "x") == "unknown"


@pytest.fixture
def persian():
    i18n.set_language("fa")
    yield
    i18n.set_language("en")


def test_every_message_has_a_persian_translation(persian):
    texts = [vc.describe({"ok": True, "current": "2.24", "latest": "2.25", "state": s})
             for s in ("newer", "same", "older", "unknown")]
    texts.append(vc.describe({"ok": False}))
    for text in texts + ["Check for update", "Checking..."]:
        assert i18n.tr(text) != text, text
