"""Core data types shared by every source."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Kind = Literal["pdf", "audio", "zip"]


@dataclass(frozen=True)
class Resource:
    """One downloadable asset discovered on a course page.

    `url` is the natural unique key: it is scraped from the page, never
    constructed, and the CDN paths are stable across site rebuilds.
    """

    source: str
    provider: str
    course: str
    kind: Kind
    url: str
    filename: str
    title: str
    section: str | None = None
    ordinal: int | None = None
    part: str | None = None
    declared_bytes: int | None = None
    discovered_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def key(self) -> str:
        return self.url
