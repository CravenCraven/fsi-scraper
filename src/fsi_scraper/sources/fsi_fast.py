"""FSI Brazilian Portuguese FAST.

Two volumes: Volume 1 is lessons 01-12, Volume 2 is lessons 13-30.
One Student Text PDF per volume, plus 34 MP3s (lessons 01, 06, 15 and 19
are split into A/B tapes). 36 assets total.

Parsing keys off the CDN URL, not the page markup: the volume and lesson
numbers are encoded in the CDN path, and object keys survive site rebuilds
that would break table-row parsing.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from ..models import Resource
from .base import CourseParser, register

CDN_HOST = "fsi-language-courses-media.nyc3.cdn.digitaloceanspaces.com"

VOLUME_IN_PATH = re.compile(r"/FAST/Volume\s+(\d+)/", re.IGNORECASE)
AUDIO_FILE = re.compile(r"Lesson\s+(\d{1,2})\s*([AB])?\.mp3$", re.IGNORECASE)
PDF_FILE = re.compile(r"Volume\s+(\d+)\.pdf$", re.IGNORECASE)


class FsiFastParser(CourseParser):
    source = "fsi-language-courses"
    provider = "fsi"
    course = "brazilian-portuguese-fast"
    title = "FSI Brazilian Portuguese FAST"
    license = "public domain"
    credit = ("FSI Brazilian Portuguese FAST, US Foreign Service Institute "
              "(public domain)")
    page_url = (
        "https://www.fsi-language-courses.org/fsi-brazilian-portuguese-fast-course/"
    )

    def parse(self, html: str, page_url: str = "") -> Iterator[Resource]:
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            url = anchor["href"].strip()
            if urlparse(url).netloc != CDN_HOST:
                continue
            if url in seen:
                continue

            resource = self._classify(url)
            if resource is None:
                continue

            seen.add(url)
            yield resource

    def _classify(self, url: str) -> Resource | None:
        path = unquote(urlparse(url).path)
        filename = path.rsplit("/", 1)[-1]

        volume_match = VOLUME_IN_PATH.search(path)
        volume = int(volume_match.group(1)) if volume_match else None
        section = f"Volume {volume}" if volume else None

        audio_match = AUDIO_FILE.search(filename)
        if audio_match:
            lesson = int(audio_match.group(1))
            part = (audio_match.group(2) or "").upper() or None
            title = f"Lesson {lesson:02d}" + (f" (Tape {part})" if part else "")
            return Resource(
                source=self.source,
                provider=self.provider,
                course=self.course,
                kind="audio",
                url=url,
                filename=filename,
                title=title,
                section=section,
                ordinal=lesson,
                part=part,
            )

        pdf_match = PDF_FILE.search(filename)
        if pdf_match:
            pdf_volume = int(pdf_match.group(1))
            return Resource(
                source=self.source,
                provider=self.provider,
                course=self.course,
                kind="pdf",
                url=url,
                filename=filename,
                title=f"Student Text, Volume {pdf_volume}",
                section=f"Volume {pdf_volume}",
                ordinal=None,
            )

        return None


register(FsiFastParser())
