"""Write discovered files and parsed lessons into Postgres.

Every write is an upsert, so running `load` twice leaves the database
exactly as running it once.

The connection string comes from DATABASE_URL. Locally that is the Docker
Compose Postgres; on the cluster the same code points at CloudNativePG by
changing only that variable.
"""

from __future__ import annotations

import dataclasses
import os

import psycopg

from .models import Resource
from .parse_fast import Lesson

DEFAULT_URL = "postgresql://postgres:postgres@localhost:5432/corpus"

UPSERT_RESOURCE = """
INSERT INTO resource (source, provider, course, kind, url, filename, title,
                      section, ordinal, part, declared_bytes, discovered_at)
VALUES (%(source)s, %(provider)s, %(course)s, %(kind)s, %(url)s, %(filename)s,
        %(title)s, %(section)s, %(ordinal)s, %(part)s, %(declared_bytes)s,
        %(discovered_at)s)
ON CONFLICT (url) DO UPDATE SET
    source = EXCLUDED.source,
    provider = EXCLUDED.provider,
    course = EXCLUDED.course,
    kind = EXCLUDED.kind,
    filename = EXCLUDED.filename,
    title = EXCLUDED.title,
    section = EXCLUDED.section,
    ordinal = EXCLUDED.ordinal,
    part = EXCLUDED.part,
    declared_bytes = EXCLUDED.declared_bytes
"""
# discovered_at is left out of the update on purpose: it keeps the date the
# file was FIRST seen, which is the useful one.

UPSERT_LESSON = """
INSERT INTO lesson (course, number, location, title)
VALUES (%s, %s, %s, %s)
ON CONFLICT (course, number) DO UPDATE SET
    location = EXCLUDED.location,
    title = EXCLUDED.title
RETURNING id
"""

INSERT_LINE = """
INSERT INTO dialog_line (lesson_id, seq, speaker, text, page)
VALUES (%s, %s, %s, %s, %s)
"""


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def load(
    conn: psycopg.Connection,
    course: str,
    resources: list[Resource],
    lessons: list[Lesson],
) -> tuple[int, int, int]:
    """Upsert everything. Returns (resources, lessons, dialog lines) written.

    The caller's `with psycopg.connect(...)` block is the transaction: if
    anything here fails, none of it is saved.
    """
    lines_written = 0
    with conn.cursor() as cur:
        for resource in resources:
            cur.execute(UPSERT_RESOURCE, dataclasses.asdict(resource))

        for lesson in lessons:
            cur.execute(UPSERT_LESSON,
                        (course, lesson.number, lesson.location, lesson.title))
            (lesson_id,) = cur.fetchone()

            # The line count can change when the parser improves, so replace
            # this lesson's lines wholesale rather than matching them up.
            cur.execute("DELETE FROM dialog_line WHERE lesson_id = %s",
                        (lesson_id,))
            cur.executemany(INSERT_LINE, [
                (lesson_id, line.seq, line.speaker, line.text, line.page)
                for line in lesson.lines
            ])
            lines_written += len(lesson.lines)

    return len(resources), len(lessons), lines_written
