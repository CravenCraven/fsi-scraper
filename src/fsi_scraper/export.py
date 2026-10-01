"""Export a small, public sample of the corpus as JSON.

The output is read from the database, not the parser, so it proves the whole
path worked: fetch -> parse -> load -> query.

It is deterministic on purpose: no timestamps, fixed ordering. Exporting
twice from the same data gives a byte-identical file, so `git diff` on the
committed sample shows only real data changes.
"""

from __future__ import annotations

import psycopg

COURSE = "brazilian-portuguese-fast"

TOTALS = """
SELECT (SELECT count(*) FROM resource WHERE course = %(course)s),
       (SELECT count(*) FROM lesson WHERE course = %(course)s),
       (SELECT count(*) FROM dialog_line d JOIN lesson l ON l.id = d.lesson_id
         WHERE l.course = %(course)s)
"""

LESSONS = """
SELECT id, number, location, title
FROM lesson
WHERE course = %(course)s
ORDER BY number
LIMIT %(limit)s
"""

LINES = """
SELECT speaker, text
FROM dialog_line
WHERE lesson_id = %s
ORDER BY seq
"""


def export(conn: psycopg.Connection, limit: int) -> dict:
    params = {"course": COURSE, "limit": limit}
    with conn.cursor() as cur:
        cur.execute(TOTALS, params)
        files, lessons, lines = cur.fetchone()

        cur.execute(LESSONS, params)
        sample = []
        for lesson_id, number, location, title in cur.fetchall():
            cur.execute(LINES, (lesson_id,))
            sample.append({
                "number": number,
                "location": location,
                "title": title,
                "lines": [{"speaker": s, "text": t} for s, t in cur.fetchall()],
            })

    return {
        "source": "FSI Brazilian Portuguese FAST (public domain)",
        "course": COURSE,
        "totals": {"files": files, "lessons": lessons, "dialog_lines": lines},
        "lessons": sample,
    }
