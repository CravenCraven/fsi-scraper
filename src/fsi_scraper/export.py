"""Export a small, public sample of the corpus as JSON.

The output is read from the database, not the parsers, so it proves the
whole path worked: fetch -> parse -> load -> query.

Every course in the database is exported with its credit line, and every
sample lesson names its course. COERLL is CC BY, so wherever one of its
lessons is shown, the page needs that course's credit next to it.

It is deterministic on purpose: no timestamps, fixed ordering. Exporting
twice from the same data gives a byte-identical file, so `git diff` on the
committed sample shows only real data changes.
"""

from __future__ import annotations

import psycopg

COURSES = """
SELECT c.slug, c.title, c.license, c.credit,
       (SELECT count(*) FROM resource r WHERE r.course = c.slug),
       (SELECT count(*) FROM lesson l WHERE l.course = c.slug),
       (SELECT count(*) FROM dialog_line d JOIN lesson l ON l.id = d.lesson_id
         WHERE l.course = c.slug)
FROM course c
ORDER BY c.slug
"""

LESSONS = """
SELECT id, number, location, title
FROM lesson
WHERE course = %s
ORDER BY number
LIMIT %s
"""

LINES = """
SELECT speaker, text, translation
FROM dialog_line
WHERE lesson_id = %s
ORDER BY seq
"""


def export(conn: psycopg.Connection, limit: int) -> dict:
    """`limit` lessons per course."""
    courses, sample = [], []
    totals = {"files": 0, "lessons": 0, "dialog_lines": 0}
    with conn.cursor() as cur:
        cur.execute(COURSES)
        rows = cur.fetchall()
        for slug, title, license_, credit, files, lessons, lines in rows:
            courses.append({
                "slug": slug, "title": title, "license": license_,
                "credit": credit, "files": files, "lessons": lessons,
                "dialog_lines": lines,
            })
            totals["files"] += files
            totals["lessons"] += lessons
            totals["dialog_lines"] += lines

            cur.execute(LESSONS, (slug, limit))
            for lesson_id, number, location, lesson_title in cur.fetchall():
                cur.execute(LINES, (lesson_id,))
                sample.append({
                    "course": slug,
                    "number": number,
                    "location": location,
                    "title": lesson_title,
                    "lines": [{"speaker": s, "text": t, "translation": tr}
                              for s, t, tr in cur.fetchall()],
                })

    return {"courses": courses, "totals": totals, "lessons": sample}
