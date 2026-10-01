"""The interface every course parser implements.

  parse(html, page_url)   -> Resources found on this page
  follow(html, page_url)  -> further page URLs worth visiting

Single-page courses implement only `parse`; `follow` defaults to empty and
the crawl terminates after one fetch. Multi-page courses override `follow`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator

from ..models import Resource


class CourseParser(ABC):
    """Parses one course's pages into Resources."""

    source: str
    provider: str
    course: str
    page_url: str

    @abstractmethod
    def parse(self, html: str, page_url: str) -> Iterator[Resource]:
        """Yield one Resource per downloadable asset found in `html`."""
        raise NotImplementedError

    def follow(self, html: str, page_url: str) -> Iterable[str]:
        """Yield further page URLs to crawl. Default: single-page course."""
        return ()


_REGISTRY: dict[str, CourseParser] = {}


def register(parser: CourseParser) -> CourseParser:
    _REGISTRY[parser.course] = parser
    return parser


def get(course: str) -> CourseParser:
    try:
        return _REGISTRY[course]
    except KeyError:
        raise KeyError(
            f"no parser registered for course {course!r}; "
            f"known: {sorted(_REGISTRY)}"
        ) from None


def registered() -> list[str]:
    return sorted(_REGISTRY)
