from pathlib import Path

import pytest

from backend.services.storage_service import StorageService


def make_local_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "objects"))
    return StorageService()


def test_local_storage_round_trip_and_listing(tmp_path, monkeypatch):
    service = make_local_storage(tmp_path, monkeypatch)
    result = service.put_bytes("docs/hello.txt", b"hello", "text/plain")
    assert result["key"] == "docs/hello.txt"
    assert service.get_bytes("docs/hello.txt") == b"hello"
    items = service.list("docs")
    assert len(items) == 1
    assert items[0]["name"] == "hello.txt"
    assert items[0]["size"] == 5


def test_local_storage_delete_folder(tmp_path, monkeypatch):
    service = make_local_storage(tmp_path, monkeypatch)
    service.put_bytes("docs/a.txt", b"a")
    service.put_bytes("docs/nested/b.txt", b"b")
    service.delete("docs/")
    assert service.list("docs") == []


@pytest.mark.parametrize("key", ["../escape.txt", "docs/../escape.txt", ""])
def test_storage_rejects_unsafe_keys(tmp_path, monkeypatch, key):
    service = make_local_storage(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        service.put_bytes(key, b"no")
