"""Core data types shared by every source."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

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
    section: Optional[str] = None
    ordinal: Optional[int] = None
    part: Optional[str] = None
    declared_bytes: Optional[int] = None
    discovered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def key(self) -> str:
        return self.url
