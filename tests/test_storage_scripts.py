import storage_core as sc
import storage_publish as sp


class FakeClient:
    def __init__(self, used):
        self.used = used
        self.uploaded = []

    def get_paginator(self, name):
        outer = self

        class Pages:
            def paginate(self, **kwargs):
                return [{"Contents": [{"Key": "k", "Size": outer.used}]}]

        return Pages()

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self.uploaded.append((bucket, key))


def test_buckets_are_found_and_ordered():
    secrets = {"ARVAN_ACCESS_KEY": "a", "ARVAN_SECRET_KEY": "b", "ARVAN_2_ACCESS_KEY": "c",
               "ARVAN_2_SECRET_KEY": "d", "ARVAN_2_BUCKET": "bk2", "ARVAN_2_QUOTA_GB": "10"}
    buckets = sc.discover_buckets(secrets)
    assert [b.id for b in buckets] == ["main", "2"]
    assert buckets[1].quota_bytes == 10 * sc.GIB and buckets[0].bucket == sc.DEFAULT_MAIN_BUCKET
    assert [b.id for b in sc.order_buckets(buckets, "2")] == ["2", "main"]


def test_secrets_from_environment():
    data = sc.load_secrets({"ALL_SECRETS": '{"ARVAN_ACCESS_KEY":"x","EMPTY":""}', "ARVAN_BUCKET": "b"})
    assert data["ARVAN_ACCESS_KEY"] == "x" and data["ARVAN_BUCKET"] == "b" and "EMPTY" not in data


def test_public_url_encodes_spaces():
    b = sc.Bucket("main", "a", "b", "bk", "https://s3.example.com", 1)
    assert sc.public_url(b, "ytbridge/run-1/my file.mp4") == "https://s3.example.com/bk/ytbridge/run-1/my%20file.mp4"


def test_upload_moves_on_when_the_first_bucket_is_full(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * 100)
    b1 = sc.Bucket("main", "a", "b", "one", "https://e", 1000)
    b2 = sc.Bucket("2", "a", "b", "two", "https://e", 1000)
    clients = {"main": FakeClient(950), "2": FakeClient(0)}
    info, warnings = sc.upload_to_arvan(str(f), [b1, b2], "", "run-1", client_factory=lambda b: clients[b.id], now=0)
    assert info["bucket"] == "two" and clients["2"].uploaded
    assert any("full" in w for w in warnings)


def test_upload_without_any_bucket(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    info, warnings = sc.upload_to_arvan(str(f), [], "", "run-1")
    assert info is None and warnings


def test_publish_in_github_mode_makes_a_release(tmp_path, monkeypatch):
    (tmp_path / "a.zip").write_bytes(b"1")
    calls = []
    monkeypatch.setattr(sp, "gh", lambda *a, **k: calls.append(a))
    monkeypatch.setenv("STORAGE", "github")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("QUALITY_META", raising=False)
    assert sp.main(["publish", "--dir", str(tmp_path), "--tag", "run-5", "--title", "T"]) == 0
    args = calls[0]
    assert args[:3] == ("release", "create", "run-5") and str(tmp_path / "a.zip") in args and "--prerelease" in args


def test_publish_with_no_file_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, "gh", lambda *a, **k: None)
    assert sp.main(["publish", "--dir", str(tmp_path), "--tag", "t"]) == 1


def test_unknown_storage_mode_means_github(monkeypatch):
    monkeypatch.setenv("STORAGE", "weird")
    assert sp.get_mode() == "github"
