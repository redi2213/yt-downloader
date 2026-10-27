import io
import zipfile

import pytest

from core import zip_tools as zt


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


def test_branch_folders_are_read():
    data = make_zip({"main/app.py": "x=1", "config/config.json": "{}", "main/__pycache__/a.pyc": "b"})
    assert zt.has_branch_folders(data)
    out = zt.read_update_zip(data)
    assert set(out) == {"main", "config"} and "app.py" in out["main"]
    assert not any("pyc" in p for p in out["main"])


def test_backup_folder_names_inside_a_wrapper_folder():
    data = make_zip({"wrapper/main-branch/a.py": "1", "wrapper/config-branch/config.json": "{}"})
    assert set(zt.read_update_zip(data)) == {"main", "config"}


def test_secrets_and_junk_are_never_sent():
    for path in ("android.keystore", "k.b64", "cookies.txt", ".env", "a/b/__pycache__/x.py",
                 "core/_branch.py", "x.apk", "../evil.py"):
        assert zt.is_skipped_path(path), path
    assert not zt.is_skipped_path("core/config.py")


def test_loose_files_zip():
    data = make_zip({"a.py": "1", "dir/b.py": "2", "secret.pem": "k"})
    assert not zt.has_branch_folders(data)
    assert sorted(n for n, _c, _m in zt.read_loose_files(data)) == ["a.py", "dir/b.py"]


def test_bad_zip():
    with pytest.raises(zt.ZipError):
        zt.read_update_zip(b"nope")
    assert zt.is_zip(make_zip({"a": "b"})) and not zt.is_zip(b"abcd")


def test_git_blob_sha_matches_git():
    assert zt.git_blob_sha(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert zt.git_blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
