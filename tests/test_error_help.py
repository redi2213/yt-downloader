import re

from core import error_help as eh


def test_bot_check_is_recognised():
    found = eh.find_help("ERROR: Sign in to confirm you\u2019re not a bot. Use --cookies")
    assert found and found[0]["id"] == "bot_check"


def test_at_most_two_matches_and_none_for_clean_text():
    assert len(eh.find_help("HTTP Error 403: Forbidden, timed out, 429 too many requests")) <= 2
    assert eh.find_help("everything fine") == []


def test_regex_rules_and_text():
    patterns = [{"id": "x", "match": ["re:\\bfoo\\d+\\b"], "title": "T", "tip": "tip"}]
    assert eh.find_help("a foo12 b", patterns)[0]["id"] == "x"
    assert eh.find_help("a foo b", patterns) == []
    assert eh.help_text(eh.find_help("foo1", patterns)) == "T\ntip"


def test_every_built_in_pattern_is_valid():
    ids = set()
    for pattern in eh.DEFAULT_PATTERNS:
        assert pattern["id"] not in ids
        ids.add(pattern["id"])
        assert pattern["tip"] and pattern["match"]
        for rule in pattern["match"]:
            if rule.startswith("re:"):
                re.compile(rule[3:])
