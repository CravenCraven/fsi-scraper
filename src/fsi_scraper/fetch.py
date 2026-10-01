"""Download the files `discover` finds.

Two rules keep a rerun safe:

* A file already on disk is never downloaded again.
* A download is written to `<name>.part` and renamed only once it is
  complete, so an interrupted run cannot leave a cut-off file that looks
  finished.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .models import Resource

if TYPE_CHECKING:
    from .cli import Fetcher

CHUNK = 1 << 16  # read and write 64 KB at a time


@dataclass(frozen=True)
class Fetched:
    resource: Resource
    path: Path
    bytes: int
    sha256: str
    downloaded: bool  # False when the file was already on disk


def target_path(root: Path, resource: Resource) -> Path:
    """data/raw/<course>/<kind>/<filename>"""
    return root / resource.course / resource.kind / resource.filename


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(fetcher: Fetcher, resource: Resource, root: Path) -> Fetched:
    dest = target_path(root, resource)
    if dest.exists():
        return Fetched(resource, dest, dest.stat().st_size, sha256_of(dest),
                       downloaded=False)

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    size = 0

    with fetcher.stream(resource.url) as response:
        expected = response.headers.get("Content-Length")
        if response.headers.get("Content-Encoding"):
            expected = None  # compressed on the wire; length won't match
        with part.open("wb") as out:
            for chunk in response.iter_content(CHUNK):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)

    if expected is not None and int(expected) != size:
        part.unlink()
        raise OSError(f"incomplete download: got {size} of {expected} bytes")

    part.replace(dest)
    return Fetched(resource, dest, size, digest.hexdigest(), downloaded=True)
