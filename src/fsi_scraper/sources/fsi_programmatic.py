"""FSI Portuguese Programmatic (Brazilian).

48 units across two volumes: Volume 1 is units 1-25, Volume 2 is 26-48.
Drills and dialogs start at Unit 7. 1751 PDF pages, 27+ hours of audio.

Shape differs from FAST: the index page carries only the two complete-volume
PDFs. Each unit is a separate page on the site holding that unit's ZIP of
audio and its unit PDF. So this parser overrides `follow` to walk the 48 unit
pages found on the index.

The site advertises 299 audio files; those are the MP3s inside the 48 ZIPs.
`discover` reports what is downloadable -- 48 archives. Unpacking is a fetch
stage concern.

Unit page slugs are not derivable, so they are scraped, never constructed.
Asset classification keys off the CDN URL, which encodes volume and unit.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from ..models import Resource
from .base import CourseParser, register

CDN_HOST = "fsi-language-courses-media.nyc3.cdn.digitaloceanspaces.com"
SITE_HOST = "www.fsi-language-courses.org"
COURSE_PATH = "/fsi-portuguese-programmatic-course/"

VOLUME_IN_PATH = re.compile(r"/Programmatic/Volume\s+(\d+)/", re.IGNORECASE)
UNIT_FILE = re.compile(r"Unit\s+(\d{1,2})\.(zip|pdf)$", re.IGNORECASE)
VOLUME_PDF = re.compile(r"Course\s+-\s+Volume\s+(\d+)\.pdf$", re.IGNORECASE)
UNIT_PAGE = re.compile(rf"^{re.escape(COURSE_PATH)}(\d{{1,2}})-([a-z0-9-]+)/?$")


class FsiProgrammaticParser(CourseParser):
    source = "fsi-language-courses"
    provider = "fsi"
    course = "portuguese-programmatic"
    title = "FSI Portuguese Programmatic"
    license = "public domain"
    credit = "FSI Portuguese Programmatic, US Foreign Service Institute (public domain)"
    page_url = (
        "https://www.fsi-language-courses.org/fsi-portuguese-programmatic-course/"
    )

    def parse(self, html: str, page_url: str = "") -> Iterator[Resource]:
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            url = urljoin(page_url or self.page_url, anchor["href"].strip())
            if urlparse(url).netloc != CDN_HOST or url in seen:
                continue
            resource = self._classify(url)
            if resource is None:
                continue
            seen.add(url)
            yield resource

    def follow(self, html: str, page_url: str = "") -> Iterable[str]:
        """Yield the unit page URLs listed on the index."""
        soup = BeautifulSoup(html, "html.parser")
        found: dict[int, str] = {}

        for anchor in soup.find_all("a", href=True):
            url = urljoin(page_url or self.page_url, anchor["href"].strip())
            parsed = urlparse(url)
            if parsed.netloc != SITE_HOST:
                continue
            match = UNIT_PAGE.match(parsed.path)
            if not match:
                continue
            unit = int(match.group(1))
            found.setdefault(unit, url.split("#")[0])

        for unit in sorted(found):
            yield found[unit]

    def _classify(self, url: str) -> Resource | None:
        path = unquote(urlparse(url).path)
        filename = path.rsplit("/", 1)[-1]

        volume_match = VOLUME_IN_PATH.search(path)
        volume = int(volume_match.group(1)) if volume_match else None
        section = f"Volume {volume}" if volume else None

        unit_match = UNIT_FILE.search(filename)
        if unit_match:
            unit = int(unit_match.group(1))
            ext = unit_match.group(2).lower()
            kind = "zip" if ext == "zip" else "pdf"
            label = "Audio" if kind == "zip" else "Text"
            return Resource(
                source=self.source,
                provider=self.provider,
                course=self.course,
                kind=kind,
                url=url,
                filename=filename,
                title=f"Unit {unit:02d} {label}",
                section=section,
                ordinal=unit,
            )

        volume_pdf = VOLUME_PDF.search(filename)
        if volume_pdf:
            vol = int(volume_pdf.group(1))
            return Resource(
                source=self.source,
                provider=self.provider,
                course=self.course,
                kind="pdf",
                url=url,
                filename=filename,
                title=f"Complete Text, Volume {vol}",
                section=f"Volume {vol}",
                ordinal=None,
            )

        return None


register(FsiProgrammaticParser())
