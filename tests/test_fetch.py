"""fetch tests. No network: a fake fetcher hands back bytes we made up."""

import hashlib

import pytest

from fsi_scraper.fetch import download, target_path
from fsi_scraper.models import Resource

BODY = b"not really a pdf, but 30 bytes"


class FakeResponse:
    def __init__(self, body: bytes, declared_length: int | None,
                 status_code: int = 200):
        self.body = body
        self.status_code = status_code
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
        self.status_code = 200
        self.last_headers: dict | None = None

    def stream(self, url: str, headers: dict | None = None) -> FakeResponse:
        self.calls += 1
        self.last_headers = headers
        return FakeResponse(self.body, self.declared_length, self.status_code)


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


def test_short_download_is_rejected_and_part_kept(tmp_path):
    fetcher = FakeFetcher(BODY, declared_length=len(BODY) + 5)

    with pytest.raises(OSError, match="incomplete download"):
        download(fetcher, make_resource(), tmp_path)

    leftovers = [p.name for p in tmp_path.rglob("*") if p.is_file()]
    assert leftovers == ["Volume 1.pdf.part"]


def test_resume_continues_partial_download(tmp_path):
    resource = make_resource()
    part = target_path(tmp_path, resource).with_name("Volume 1.pdf.part")
    part.parent.mkdir(parents=True)
    part.write_bytes(BODY[:10])

    fetcher = FakeFetcher(BODY[10:], declared_length=len(BODY) - 10)
    fetcher.status_code = 206

    result = download(fetcher, resource, tmp_path)

    assert fetcher.last_headers == {"Range": "bytes=10-"}
    assert result.bytes == len(BODY)
    assert result.sha256 == hashlib.sha256(BODY).hexdigest()
    assert result.path.read_bytes() == BODY
    assert not part.exists()


def test_server_ignoring_range_restarts_from_scratch(tmp_path):
    resource = make_resource()
    part = target_path(tmp_path, resource).with_name("Volume 1.pdf.part")
    part.parent.mkdir(parents=True)
    part.write_bytes(b"stale junk")

    fetcher = FakeFetcher(BODY, declared_length=len(BODY))

    result = download(fetcher, resource, tmp_path)

    assert fetcher.last_headers == {"Range": "bytes=10-"}
    assert result.path.read_bytes() == BODY
    assert result.sha256 == hashlib.sha256(BODY).hexdigest()
