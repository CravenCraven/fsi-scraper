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


def _sha256_digest(path: Path) -> hashlib._Hash:
    """A running hash of the file so far, so a resumed download can continue it."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            digest.update(chunk)
    return digest


def sha256_of(path: Path) -> str:
    return _sha256_digest(path).hexdigest()


def download(fetcher: Fetcher, resource: Resource, root: Path) -> Fetched:
    dest = target_path(root, resource)
    if dest.exists():
        return Fetched(resource, dest, dest.stat().st_size, sha256_of(dest),
                       downloaded=False)

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    size = 0

    # Resume: if a partial file is on disk, hash what we have and ask the
    # server for the rest. The server may still send the whole file (200).
    headers = {}
    if part.exists():
        size = part.stat().st_size
        digest = _sha256_digest(part)
        headers["Range"] = f"bytes={size}-"

    with fetcher.stream(resource.url, headers=headers) as response:
        resumed = response.status_code == 206
        if not resumed:
            digest = hashlib.sha256()
            size = 0

        expected = None
        declared = response.headers.get("Content-Length")
        if declared is not None and not response.headers.get("Content-Encoding"):
            # With a Range, Content-Length covers only the piece being sent.
            expected = size + int(declared)

        with part.open("ab" if resumed else "wb") as out:
            for chunk in response.iter_content(CHUNK):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)

    if expected is not None and expected != size:
        raise OSError(f"incomplete download: got {size} of {expected} bytes; "
                      f"kept {part.name} to resume next run")

    part.replace(dest)
    return Fetched(resource, dest, size, digest.hexdigest(), downloaded=True)
