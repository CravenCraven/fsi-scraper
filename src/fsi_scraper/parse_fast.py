"""Turn the FSI FAST student texts (two PDFs) into dialog lines.

The PDFs are scans with an OCR text layer, so the text is close to right but
not exact. Everything here is written against what the OCR actually
produces, not what the printed book says:

* Page header "BRAZILIAN PORTUGUESE FAST" also comes out as BRAZILlAN or
  BRAZIUAN.
* "LESSON 3" sometimes loses its space: "LESSON3".
* Roman numerals become digits: "III. Seeing It" is "111. Seeing It".
* Lesson 13 has two Brazilian speakers, B1 and B2. OCR reads B as 8, so
  they show up as "81." / "82." and sometimes "B 1.".
* Lesson 30's dialog has no "Sample Dialog" heading, so the dialog is found
  by its section ("Seeing It"), not by that heading.

Lesson titles and locations go through TITLE_FIXES. There are 30 of them,
from a book that will never change, so a hand-checked table is exact where
pattern-based fixes could break correct words. Dialog text is not touched.

Each lesson's dialog sits on one page. It runs from the "Seeing It" heading
to the page footer (e.g. "2.2", OCR'd as "5.t" once) or the next section.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

LESSON = re.compile(r"\bLESSON\s*(\d{1,2})\b")
HEADER = re.compile(r"^BRAZI\w*\s+PORTUGUESE\s+FAST$")
SEEING_IT = re.compile(r"Seeing\s+It\b")
NEXT_SECTION = re.compile(r"^[IVX1l]+\s*\.\s+[A-Z][a-z]")  # "IV. Taking It Apart"
FOOTER = re.compile(r"^\d{1,2}\s*[.\-]\s*\S{1,3}$")  # "2.2", "5.t", "13 -4"
SPEAKER = re.compile(r"^(A|B|[B8]\s?[12])\s?\.\s+(.*)$")
DIRECTION = re.compile(r"^\(.*\)$")  # "(A few minutes later)"
SKIP = re.compile(r"^(Sample\s+Dialog|Looking at the dialog|clues, see how much|"
                  r"contextual clues, see how much)")


# lesson number -> (location, title) as printed in the book. Only lessons
# where the OCR got it wrong are listed.
TITLE_FIXES: dict[int, tuple[str, str]] = {
    1: ("AT THE HOTEL", "Checking In"),
    2: ("AT THE HOTEL", "Ordering Breakfast"),
    5: ("AT THE HOTEL", "Checking for Messages"),
    7: ("ON THE STREET", "Asking for Directions (Inside of a building)"),
    9: ("AT THE OFFICE", "Answering the Telephone"),
    10: ("AT THE OFFICE", "Leaving a Message"),
    12: ('IN A "LANCHONETE"', "Ordering Lunch"),
    13: ("AT A PARTY", "Being Introduced to Someone"),
    14: ("TELEPHONE EXCHANGES", "Answering a Wrong Number"),
    19: ("AT AN OPEN-AIR MARKET", "Buying Fresh Food"),
    20: ("AT THE BUTCHER SHOP", "Buying Meat"),
    26: ("HOUSEHOLD HELP", "Giving Instructions (On the Way Out)"),
    29: ("HANDLING EMERGENCIES", "Reporting an Assault to the Police"),
    30: ("AT THE GAS STATION", "Filling up with Gas"),
}


@dataclass(frozen=True)
class DialogLine:
    lesson: int
    seq: int  # order within the lesson's dialog, starting at 1
    speaker: str | None  # "A", "B", "B1", "B2", or None for a stage direction
    text: str
    page: int  # 1-based page in the PDF


@dataclass(frozen=True)
class Lesson:
    number: int
    location: str  # "AT THE HOTEL"
    title: str  # "Checking In"
    lines: tuple[DialogLine, ...]


def pdf_pages(path: Path) -> list[str]:
    """Text of every page. Kept separate so the parser itself needs no PDF."""
    from pypdf import PdfReader

    return [page.extract_text() or "" for page in PdfReader(str(path)).pages]


def _clean_lines(page: str) -> list[str]:
    return [line.strip() for line in page.splitlines()
            if line.strip() and not HEADER.match(line.strip())]


def _speaker(raw: str) -> str:
    return raw.replace(" ", "").replace("8", "B")


def lesson_starts(pages: list[str]) -> dict[int, int]:
    """Lesson number -> index of its first page ("Setting the Scene")."""
    starts: dict[int, int] = {}
    for i, page in enumerate(pages):
        if "Scene" not in page:
            continue
        match = LESSON.search(page)
        if match:
            starts.setdefault(int(match.group(1)), i)
    return starts


def parse_dialog(page: str, lesson: int, page_no: int) -> list[DialogLine]:
    """Dialog lines from the one page that holds a lesson's dialog."""
    lines = _clean_lines(page)
    start = next((i for i, line in enumerate(lines) if SEEING_IT.search(line)), None)
    if start is None:
        return []

    out: list[DialogLine] = []
    for line in lines[start + 1:]:
        if FOOTER.match(line) or NEXT_SECTION.match(line):
            break
        if SKIP.match(line):
            continue
        speaker = SPEAKER.match(line)
        if speaker:
            out.append(DialogLine(lesson, len(out) + 1,
                                  _speaker(speaker.group(1)),
                                  speaker.group(2).strip(), page_no))
        elif DIRECTION.match(line):
            out.append(DialogLine(lesson, len(out) + 1, None, line, page_no))
        elif out and out[-1].speaker is not None:
            # A wrapped line: glue it onto the line before.
            prev = out[-1]
            out[-1] = DialogLine(prev.lesson, prev.seq, prev.speaker,
                                 f"{prev.text} {line}", prev.page)
    return out


def _title(page: str) -> tuple[str, str]:
    lines = _clean_lines(page)
    for i, line in enumerate(lines):
        if LESSON.search(line):
            location = lines[i + 1] if i + 1 < len(lines) else ""
            title = lines[i + 2] if i + 2 < len(lines) else ""
            return location, title
    return "", ""


def parse_lessons(pages: list[str]) -> Iterator[Lesson]:
    starts = lesson_starts(pages)
    numbers = sorted(starts)
    for n, number in enumerate(numbers):
        first = starts[number]
        last = starts[numbers[n + 1]] if n + 1 < len(numbers) else len(pages)
        dialog_page = next((i for i in range(first, last)
                            if SEEING_IT.search(pages[i])), None)
        lines = (parse_dialog(pages[dialog_page], number, dialog_page + 1)
                 if dialog_page is not None else [])
        location, title = TITLE_FIXES.get(number) or _title(pages[first])
        yield Lesson(number, location, title, tuple(lines))


def parse_books(paths: Iterable[Path]) -> list[Lesson]:
    lessons: list[Lesson] = []
    for path in paths:
        lessons.extend(parse_lessons(pdf_pages(path)))
    return sorted(lessons, key=lambda lesson: lesson.number)
