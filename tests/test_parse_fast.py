"""Parser tests, built from text the OCR really produced.

No PDFs and no network: each test hands the parser a few pages of text
copied from the FAST student texts, mistakes included.
"""

from fsi_scraper.parse_fast import lesson_starts, parse_dialog, parse_lessons

SCENE_L1 = """I. Setting the Scene
BRAZILlAN PORTUGUESE FAST
LESSON 1
AT THE HOTEL
Checking In
As you arrive at the hotel, the bell captain rushes to open the car door.
11. Hearing It
Listen to the tape once."""

DIALOG_L1 = """BRAZILlAN PORTUGUESE FAST
111. Seeing It
Sample Dialog
Looking at the dialog, listen to the tape again. Looking for cognates and contextual
clues, see how much you can understand.
B. Bom dia, às suas ordens!
A. Bom dia, o senhor tem uma reserva no nome de Anne Covington?
B. Um momento, vou ver ... Covington ... Ah, aqui está. A senhora é do
Consulado Americano?
A. Sou, sim.
1.5"""

EXERCISE_L1 = """BRAZILlAN PORTUGUESE FAST
Filling in the 81anks - 1
Listen to the tape again, this time trying to write missing words.
Bom I às ordens! -------------- ----------"""

SCENE_L3 = """I. Setting the Scene
BRAZIUAN PORTUGUESE FAST
LESSON3
AT THE HOTEL
Making a Long-Distance Call"""


def test_dialog_lines_have_speaker_text_and_order():
    lines = parse_dialog(DIALOG_L1, lesson=1, page_no=22)
    assert [line.speaker for line in lines] == ["B", "A", "B", "A"]
    assert lines[0].text == "Bom dia, às suas ordens!"
    assert [line.seq for line in lines] == [1, 2, 3, 4]


def test_accents_survive():
    lines = parse_dialog(DIALOG_L1, lesson=1, page_no=22)
    assert "às" in lines[0].text
    assert "está" in lines[2].text


def test_wrapped_line_is_joined_to_the_line_before():
    lines = parse_dialog(DIALOG_L1, lesson=1, page_no=22)
    assert lines[2].text.endswith("A senhora é do Consulado Americano?")


def test_footer_ends_the_dialog():
    lines = parse_dialog(DIALOG_L1 + "\nB. not dialog", lesson=1, page_no=22)
    assert lines[-1].text == "Sou, sim."


def test_instructions_are_not_dialog():
    texts = " ".join(line.text for line in parse_dialog(DIALOG_L1, 1, 22))
    assert "Looking at the dialog" not in texts


def test_lesson_number_without_a_space():
    assert lesson_starts([SCENE_L3]) == {3: 0}


def test_ocr_8_for_b_gives_b1_and_b2():
    page = """111. Seeing It
Sample Dialog
B 1. Oi Paul, como vai?
A. Eu acabei de chegar.
81. Ela é prima do Carlinhos.
82. Tudo ótimo, Fernando, e você?
13 -4"""
    lines = parse_dialog(page, lesson=13, page_no=9)
    assert [line.speaker for line in lines] == ["B1", "A", "B1", "B2"]


def test_dialog_found_without_sample_dialog_heading():
    page = """111. Seeing It
A. Encha o tanque, e verifique o óleo, por favor.
(A few minutes later)
B. O óleo está baixo.
IV. Taking It Apart"""
    lines = parse_dialog(page, lesson=30, page_no=345)
    assert [line.speaker for line in lines] == ["A", None, "B"]
    assert lines[1].text == "(A few minutes later)"


def test_whole_lesson_from_pages():
    lessons = list(parse_lessons([SCENE_L1, DIALOG_L1, EXERCISE_L1]))
    assert len(lessons) == 1
    lesson = lessons[0]
    assert (lesson.number, lesson.location, lesson.title) == (
        1, "AT THE HOTEL", "Checking In")
    assert len(lesson.lines) == 4
    assert lesson.lines[0].page == 2
