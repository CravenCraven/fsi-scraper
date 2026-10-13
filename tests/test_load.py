"""load tests, against the local Docker Postgres (`docker compose up -d`).

They use their own database, corpus_test, so the real corpus is never touched.
Skipped when Postgres is not reachable, so the other tests still run anywhere.
"""

import hashlib
import os
from pathlib import Path

import psycopg
import pytest

from fsi_scraper.fetch import target_path
from fsi_scraper.load import load
from fsi_scraper.models import Resource
from fsi_scraper.parse_fast import DialogLine, Lesson

ADMIN_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/corpus"
)
TEST_DB = "corpus_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/" + TEST_DB
SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


class FakeSource:
    course = "test-course"
    title = "Test Course"
    provider = "test"
    page_url = "https://example.com/course/"
    license = "public domain"
    credit = "Test Course (public domain)"


@pytest.fixture
def db():
    try:
        admin = psycopg.connect(ADMIN_URL, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("local Postgres not running: docker compose up -d")
    with admin:
        exists = admin.execute(
            "select 1 from pg_database where datname = %s", (TEST_DB,)
        ).fetchone()
        if not exists:
            admin.execute(f"create database {TEST_DB}")
    with psycopg.connect(TEST_URL) as conn:
        conn.execute(SCHEMA.read_text())
        conn.execute("truncate dialog_line, lesson, resource, course")
    return TEST_URL


def test_load_twice_leaves_database_unchanged(db, tmp_path):
    resource = Resource(
        source="test", provider="test", course="test-course", kind="pdf",
        url="https://example.com/Volume 1.pdf",
        filename="Volume 1.pdf", title="Volume 1",
    )
    lesson = Lesson(number=1, location="AT THE HOTEL", title="Checking In", lines=(
        DialogLine(lesson=1, seq=1, speaker="B", text="Bom dia!", page=20),
        DialogLine(lesson=1, seq=2, speaker="A", text="Bom dia.", page=20),
    ))
    on_disk = target_path(tmp_path, resource)
    on_disk.parent.mkdir(parents=True)
    on_disk.write_bytes(b"pretend pdf")

    with psycopg.connect(db) as conn:
        first = load(conn, FakeSource(), [resource], [lesson], tmp_path)
    with psycopg.connect(db) as conn:
        second = load(conn, FakeSource(), [resource], [lesson], tmp_path)

    assert first == second == (1, 1, 2)

    with psycopg.connect(db) as conn:
        counts = conn.execute(
            "select (select count(*) from resource),"
            "       (select count(*) from lesson),"
            "       (select count(*) from dialog_line)"
        ).fetchone()
        sha256, fetched_bytes = conn.execute(
            "select sha256, fetched_bytes from resource"
        ).fetchone()

    assert counts == (1, 1, 2)
    assert sha256 == hashlib.sha256(b"pretend pdf").hexdigest()
    assert fetched_bytes == len(b"pretend pdf")
