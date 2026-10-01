"""COERLL Conversa Brasileira (UT Austin), CC BY.

35 short video scenes of real people talking. Each scene has its own page,
and each page links one PDF: notes, the Portuguese transcript, and an
English translation line under every Portuguese line.

Shape: an index page that links the 35 scene pages, and one PDF per scene
page. So this parser uses both halves of the interface: `follow` walks the
index to the scene pages, `parse` finds the PDF on each scene page.

One known error on the site: the Soccer 2 page links cob_32.pdf, which is
Jam Session 1's file. The real Soccer 2 PDF, cob_31.pdf, exists but is linked
from nowhere. Checked 2026-10-01: cob_31.pdf returns 200 and its cover reads
"Soccer 2: Ninguém tira o título da gente". LINK_FIXES corrects that one link.

The site answers on cob.coerll.utexas.edu. The old www.coerll.utexas.edu
path returns 403, so the start URL uses the cob host.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from ..models import Resource
from .base import CourseParser, register

SITE_HOST = "cob.coerll.utexas.edu"
SCENE_PAGE = re.compile(r"^/brazilpod/cob/([a-z-]+)-(\d+)/?$")
TRANSCRIPT_PDF = re.compile(r"cob_(\d+)\.pdf$", re.IGNORECASE)

# scene slug -> the PDF it should link, for pages the site links wrongly
LINK_FIXES = {"soccer-2": "cob_31.pdf"}


class CoerllCobParser(CourseParser):
    source = "coerll"
    provider = "coerll"
    course = "conversa-brasileira"
    title = "Conversa Brasileira"
    license = "CC BY"
    credit = ("Conversa Brasileira, COERLL, The University of Texas at Austin "
              "(CC BY)")
    page_url = "https://cob.coerll.utexas.edu/brazilpod/cob/"

    def follow(self, html: str, page_url: str = "") -> Iterable[str]:
        """Yield the scene pages (animals-1, food-2, ...) linked from the index."""
        soup = BeautifulSoup(html, "html.parser")
        found: dict[str, str] = {}
        for anchor in soup.find_all("a", href=True):
            url = urljoin(page_url or self.page_url, anchor["href"].strip())
            parsed = urlparse(url)
            if parsed.netloc == SITE_HOST and SCENE_PAGE.match(parsed.path):
                found.setdefault(parsed.path, f"https://{SITE_HOST}{parsed.path}")
        return [found[path] for path in sorted(found)]

    def parse(self, html: str, page_url: str = "") -> Iterator[Resource]:
        """Yield the transcript PDF linked from a scene page."""
        scene = SCENE_PAGE.match(urlparse(page_url).path) if page_url else None
        if scene is None:
            return  # the index page lists scenes, not files

        slug = f"{scene.group(1)}-{scene.group(2)}"
        topic = scene.group(1).replace("-", " ").title()
        scene_title = f"{topic} {scene.group(2)}"
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            url = urljoin(page_url, anchor["href"].strip())
            filename = unquote(urlparse(url).path).rsplit("/", 1)[-1]
            match = TRANSCRIPT_PDF.search(filename)
            if not match or url in seen:
                continue
            if slug in LINK_FIXES:
                filename = LINK_FIXES[slug]
                url = urljoin(url, filename)
                match = TRANSCRIPT_PDF.search(filename)
            seen.add(url)
            yield Resource(
                source=self.source,
                provider=self.provider,
                course=self.course,
                kind="pdf",
                url=url,
                filename=filename,
                title=scene_title,
                section=topic,
                ordinal=int(match.group(1)),
            )


register(CoerllCobParser())
