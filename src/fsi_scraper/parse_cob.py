"""Turn the Conversa Brasileira PDFs into dialog lines with translations.

Unlike FSI, these PDFs are born digital: real text, clean accents, no OCR.
The hard parts are different:

* Every Portuguese line is followed by its English translation, and nothing
  in the file marks which is which. Same font, same position, and the color
  tracks the speaker, not the language. So the split is decided from the
  text itself (see `split_turn`).
* Note markers (#, $, %, &, ') sit inside the Portuguese. They are drawn in
  symbol fonts (ZapfDingbats, plus AppleGothic or HiraKaku in a few files), so they are
  dropped by font, not by guessing.
* Some notes are also referenced by a plain number after the phrase:
  "Ai, que amor! 1 Que coisa...". A number is only removed when note N at
  the back of the same PDF starts with the words right before it, because
  real numbers ("às 5 horas", "na 24") look exactly the same.
* Speakers are real people's names in capitals: "DENISE:". One file spells
  Denise as DESINE throughout; SPEAKER_FIXES maps it back.
* Lessons 34 and 35 ("Behind the Scenes") are the course creators talking
  about the course, mostly in English, quoting Portuguese as they go. There
  is no Portuguese-then-English pattern to split, so those turns are kept
  whole, with no translation.
* Each page repeats a header and footer (2013 COERLL, the university, the
  page number, the scene title) in bands at the top and bottom of the page,
  dropped by position. The notes at the back start with a
  numbered line ("1. Ai, que amor!"), which ends the dialog.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .parse_fast import DialogLine, Lesson

SYMBOL_FONTS = ("ZapfDingbats", "AppleGothic", "HiraKaku")
# Points. Small raised words sit ~5pt off their line; lines are 14+ apart.
SAME_LINE = 6.0
HEADER_Y, FOOTER_Y = 740.0, 85.0  # page chrome lives above / below these

SPEAKER = re.compile(r"^([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ .]{1,20}?):\s*(.*)$")
SPEAKER_FIXES = {"DESINE": "DENISE"}
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
COMMENTARY = re.compile(r"^Behind the Scenes", re.IGNORECASE)
NOTES_START = re.compile(r"^\d{1,2}\.\s+\S")
CHROME = re.compile(r"^(\d{4}\s+COERLL|The University of Texas at Austin|\d{1,3}|"
                    r"Conversa Brasileira)$")
TERMINAL = re.compile(r"[.!?…\"”]\s*$")

PT_WORDS = {
    "não", "né", "que", "é", "eu", "você", "uma", "um", "com", "pra", "para",
    "mas", "isso", "essa", "esse", "está", "tá", "aí", "ela", "ele", "muito",
    "bem", "sim", "cadê", "os", "de", "do", "da", "em", "na", "se",
    "ou", "também", "aqui", "lá", "então", "nossa", "gente", "tem", "tô",
    "vai", "ia", "foi", "era", "por", "pois", "meu", "minha", "seu", "sua",
    "como", "quando", "onde", "mais", "já", "só", "ai", "oi", "olha", "nada",
    "tava", "cê", "pô", "ali", "aquele", "aquela", "outra", "outro", "cara",
    "fazer", "ver", "ter", "dar", "eles", "elas", "nós", "lhe", "te", "vou",
}
EN_WORDS = {
    "the", "i", "you", "is", "it", "and", "she", "he", "how", "what", "this",
    "that", "was", "we", "with", "to", "of", "yeah", "oh", "but", "so", "my",
    "your", "her", "his", "are", "be", "do", "don't", "it's", "i'm", "have",
    "has", "there", "they", "for", "not", "just", "like", "well", "really",
    "know", "can", "would", "will", "were", "me", "him", "them", "our",
    "about", "if", "at", "on", "very", "good", "nice", "right", "okay", "or",
}
# "as" and "no" are left out of both lists: they are common words in both
# languages, and counting them pulled English lines into the Portuguese.
PT_LETTERS = re.compile(r"[ãõçáéíóúâêô]", re.IGNORECASE)
EN_SPELLING = re.compile(r"th|\w+ing\b|\w'(s|t|re|ll|ve|m|d)\b", re.IGNORECASE)
WORD = re.compile(r"[A-Za-zÀ-ÿ']+")


@dataclass(frozen=True)
class Item:
    y: float
    x: float
    font: str
    text: str


def pdf_items(path: Path) -> list[list[Item]]:
    """Every piece of text on every page, with its position and font."""
    from pypdf import PdfReader

    pages: list[list[Item]] = []
    for page in PdfReader(str(path)).pages:
        items: list[Item] = []

        def visit(text, cm, tm, font, size, items=items):
            if text.strip():
                x = tm[4] * cm[0] + cm[4]
                y = tm[5] * cm[3] + cm[5]
                name = (font or {}).get("/BaseFont", "")
                items.append(Item(y, x, str(name), text))

        page.extract_text(visitor_text=visit)
        pages.append(items)
    return pages


def page_lines(items: list[Item], chrome: bool = True) -> list[str]:
    """Rebuild a page's lines: drop symbols and page chrome, group by height."""
    kept = sorted(
        (i for i in items
         if not any(f in i.font for f in SYMBOL_FONTS)
         and (not chrome or FOOTER_Y < i.y < HEADER_Y)),
        key=lambda i: (-i.y, i.x))
    lines: list[list[Item]] = []
    for item in kept:
        if lines and abs(lines[-1][-1].y - item.y) <= SAME_LINE:
            lines[-1].append(item)
        else:
            lines.append([item])
    out = []
    for line in lines:
        text = " ".join(i.text.strip() for i in sorted(line, key=lambda i: i.x))
        # Lesson 30 has a NUL byte where a symbol was. Postgres refuses NUL in
        # text, and no control character belongs in dialog, so drop them all.
        text = CONTROL.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append(text)
    return out


def evidence(line: str) -> tuple[int, int]:
    """(Portuguese clues, English clues) found in a line."""
    words = [w.lower() for w in WORD.findall(line)]
    pt = sum(w in PT_WORDS for w in words) + len(PT_LETTERS.findall(line))
    en = sum(w in EN_WORDS for w in words) + len(EN_SPELLING.findall(line))
    return pt, en


def score(line: str) -> int:
    """> 0 looks Portuguese, < 0 looks English, 0 can't tell."""
    pt, en = evidence(line)
    return pt - en


def split_turn(lines: list[str]) -> tuple[str, str | None]:
    """One speaker's turn -> (portuguese, english).

    The first line is always Portuguese: it is the text after the name.
    Each later line is judged on two clues:

    * its words: clearly Portuguese (score >= 2), or some Portuguese and no
      English at all, stays Portuguese; anything that leans English
      (score < 0) starts the translation. English clues include spelling
      Portuguese never uses: "th", "-ing", "it's" and "don't";
    * if the words can't decide (score 0 or 1), the line before breaks the
      tie: cut off mid-sentence means this line continues it, a finished
      sentence means this is the translation starting.

    From the first English line on, everything is English.
    """
    # Names and words that need no translation are printed twice:
    # "Sílvia!" then "Sílvia!". The second copy is the "translation".
    if len(lines) == 2 and WORD.findall(lines[0]) == WORD.findall(lines[1]):
        return lines[0].strip(), lines[1].strip()

    pt = [lines[0]] if lines else []
    en: list[str] = []
    for line in lines[1:]:
        if en:
            en.append(line)
            continue
        pt_clues, en_clues = evidence(line)
        s = pt_clues - en_clues
        unfinished = not pt[-1] or not TERMINAL.search(pt[-1])
        if s >= 2 or (pt_clues and not en_clues) or (s >= 0 and unfinished):
            pt.append(line)
        else:
            en.append(line)
    portuguese = " ".join(x for x in pt if x).strip()
    english = " ".join(en).strip() or None
    return portuguese, english


def strip_note_numbers(text: str, notes: dict[int, str]) -> str:
    """Remove "1" in "Ai, que amor! 1 Que..." when note 1 is "Ai, que amor!"."""
    for n, phrase in notes.items():
        words = WORD.findall(phrase.split("/")[0])
        if not words:
            continue
        # the number sits after the end of the phrase, or after its first word
        for anchor in (words[-2:], words[:1]):
            pattern = r"\W+".join(re.escape(w) for w in anchor)
            text = re.sub(rf"(\b{pattern}\W{{0,4}})\s*\b{n}\b\s*", r"\1 ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_pdf(pages: list[list[Item]], number: int) -> Lesson:
    first = page_lines(pages[0], chrome=False) if pages else []
    title_line = first[0] if first else ""
    location, _, title = title_line.partition(":")
    title = title.strip()

    def chrome(line: str) -> bool:
        # Position already drops the header and footer bands. Matching on the
        # scene title as well dropped real dialog: lesson 18 is titled "They
        # are getting...", which is also how one of its translations starts.
        return bool(CHROME.match(line))

    turns: list[tuple[str, int, list[str]]] = []  # speaker, page, lines
    notes: dict[int, str] = {}
    in_notes = False
    for page_no, items in enumerate(pages[1:], start=2):
        for line in page_lines(items):
            if chrome(line):
                continue
            note = NOTES_START.match(line)
            if turns and note:
                in_notes = True
            if in_notes:
                numbered = re.match(r"^(\d{1,2})\.\s+(.+)$", line)
                if numbered:
                    notes.setdefault(int(numbered.group(1)), numbered.group(2))
                continue
            speaker = SPEAKER.match(line)
            if speaker:
                name = speaker.group(1).strip()
                name = SPEAKER_FIXES.get(name, name).title()
                turns.append((name, page_no, [speaker.group(2).strip()]))
            elif turns:
                turns[-1][2].append(line)
            # lines before the first speaker are the scenario paragraph

    commentary = bool(COMMENTARY.match(title))
    lines = []
    for seq, (speaker, page_no, body) in enumerate(turns, start=1):
        if commentary:
            portuguese, english = " ".join(x for x in body if x).strip(), None
        else:
            portuguese, english = split_turn(body)
        portuguese = strip_note_numbers(portuguese, notes)
        lines.append(DialogLine(number, seq, speaker, portuguese, page_no, english))
    return Lesson(number, location.strip(), title, tuple(lines))


def parse_books(paths: Iterable[Path]) -> list[Lesson]:
    lessons = []
    for path in paths:
        match = re.search(r"cob_(\d+)\.pdf$", path.name)
        if match:
            lessons.append(parse_pdf(pdf_items(path), int(match.group(1))))
    return sorted(lessons, key=lambda lesson: lesson.number)
