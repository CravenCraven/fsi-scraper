"""fetch tests. No network: a fake fetcher hands back bytes we made up."""

import hashlib

import pytest

from fsi_scraper.fetch import download
from fsi_scraper.models import Resource

BODY = b"not really a pdf, but 30 bytes"


class FakeResponse:
    def __init__(self, body: bytes, declared_length: int | None):
        self.body = body
        self.headers = {}
        if declared_length is not None:
            self.headers["Content-Length"] = str(declared_length)

    def iter_content(self, chunk_size):
        yield self.body[:10]
        yield self.body[10:]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeFetcher:
    def __init__(self, body: bytes, declared_length: int | None):
        self.body = body
        self.declared_length = declared_length
        self.calls = 0

    def stream(self, url: str) -> FakeResponse:
        self.calls += 1
        return FakeResponse(self.body, self.declared_length)


def make_resource() -> Resource:
    return Resource(
        source="test", provider="test", course="test-course", kind="pdf",
        url="https://example.com/Volume 1.pdf",
        filename="Volume 1.pdf", title="Volume 1",
    )


def test_download_writes_file_and_hash(tmp_path):
    fetcher = FakeFetcher(BODY, declared_length=len(BODY))

    result = download(fetcher, make_resource(), tmp_path)

    assert result.downloaded is True
    assert result.bytes == len(BODY)
    assert result.sha256 == hashlib.sha256(BODY).hexdigest()
    assert result.path.read_bytes() == BODY
    assert not list(tmp_path.rglob("*.part"))


def test_existing_file_is_not_downloaded_again(tmp_path):
    fetcher = FakeFetcher(BODY, declared_length=len(BODY))
    first = download(fetcher, make_resource(), tmp_path)

    second = download(fetcher, make_resource(), tmp_path)

    assert first.downloaded is True
    assert second.downloaded is False
    assert second.sha256 == first.sha256
    assert fetcher.calls == 1


def test_short_download_is_rejected_and_part_removed(tmp_path):
    fetcher = FakeFetcher(BODY, declared_length=len(BODY) + 5)

    with pytest.raises(OSError, match="incomplete download"):
        download(fetcher, make_resource(), tmp_path)

    assert not [p for p in tmp_path.rglob("*") if p.is_file()]
