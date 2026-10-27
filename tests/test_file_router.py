from core import file_router as fr
from core.zip_tools import git_blob_sha


def index():
    main = {"core/links.py": "s1", "services/upload_service.py": "s2", "__init__.py": "e",
            "core/__init__.py": "e", "services/__init__.py": "e", ".github/workflows/download.yml": "s3"}
    return fr.RepoIndex({"main": main, "config": {"config.json": "c1"}})


def test_copy_style_names_match():
    assert fr.name_key("upload-file (1).yml") == fr.name_key("upload_file.yml")
    assert fr.name_key("Links_v2.py") == fr.name_key("links.py")


def test_exact_match_and_identical_content():
    item = fr.plan_one("links.py", b"new", "100644", index())
    assert item["status"] == fr.EXACT and item["choice"] == ("main", "core/links.py")
    idx = fr.RepoIndex({"main": {"core/links.py": git_blob_sha(b"hello\n")}, "config": {}})
    same = fr.plan_one("links.py", b"hello\n", "100644", idx)
    assert same["status"] == fr.SAME and not fr.included(same)


def test_config_json_goes_to_the_config_branch():
    assert fr.plan_one("config.json", b"{}", "100644", index())["choice"] == ("config", "config.json")


def test_same_name_in_several_folders_needs_a_choice():
    item = fr.plan_one("__init__.py", b"", "100644", index())
    assert item["status"] == fr.AMBIGUOUS and item["choice"] is None and len(item["candidates"]) > 1


def test_new_file_gets_folder_suggestions():
    item = fr.plan_one("backup_service.py", b"x", "100644", index())
    assert item["status"] == fr.NEW and "services" in item["folder_suggestions"]


def test_conflicts_pending_and_collect():
    idx = index()
    clash = fr.plan([("links.py", b"a", "100644"), ("core/links.py", b"b", "100644")], idx)
    assert fr.conflicts(clash)
    items = fr.plan([("backup_service.py", b"x", "100644")], idx)
    assert fr.pending(items) == 1
    items[0]["choice"] = ("main", "services/backup_service.py")
    assert fr.pending(items) == 0
    assert fr.collect(items) == {"main": {"services/backup_service.py": (b"x", "100644")}}


def test_diff_stats():
    assert fr.diff_stats(b"a\nb\n", b"a\nc\nd\n") == (2, 1)
    assert fr.diff_stats(b"\xff\xfe", b"x") is None
