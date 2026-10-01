"""Conversa Brasileira parser tests, built from real lines in the PDFs.

The hard cases are the ones that broke while building the parser: a
Portuguese line that wraps, a translation that keeps a Portuguese word, a
second Portuguese sentence after a finished one, note numbers next to real
numbers, and symbol-font markers.
"""

from fsi_scraper.parse_cob import (
    Item,
    page_lines,
    parse_pdf,
    split_turn,
    strip_note_numbers,
)


def test_simple_turn_splits_into_portuguese_and_english():
    assert split_turn(["Provavelmente...", "Probably..."]) == (
        "Provavelmente...", "Probably...")


def test_wrapped_portuguese_stays_portuguese():
    pt, en = split_turn([
        "Pois é, eu tenho duas meninas em casa, aí elas que escolheram o nome,",
        "né?",
        "Well, I have two girls at home, so they chose her name...",
    ])
    assert pt.endswith("o nome, né?")
    assert en.startswith("Well, I have two girls")


def test_second_portuguese_sentence_after_a_finished_one():
    pt, en = split_turn([
        "Eh, eu acho que tem que levar em consideração, eh, a criança, não?",
        "Em primeiro lugar... Então, se ela tem uma vida estável, trabalhando,",
        "tem um emprego fixo, então seria interessante ela levar a criança...",
        "First and foremost, I think that she has to take into account",
    ])
    assert "Em primeiro lugar" in pt and "emprego fixo" in pt
    assert en.startswith("First and foremost")


def test_translation_that_keeps_a_portuguese_name():
    pt, en = split_turn(["Ou então, pão de queijo...", "Or pão de queijo ..."])
    assert (pt, en) == ("Ou então, pão de queijo...", "Or pão de queijo ...")


def test_words_used_in_both_languages_do_not_count():
    assert split_turn(["... tão grande como o Rio...", "... as big as Rio..."])[1] \
        == "... as big as Rio..."


def test_note_number_after_its_phrase_is_removed():
    notes = {1: "Ai, que amor!"}
    assert strip_note_numbers(
        "Ai, que amor! 1 Que coisa mais linda!", notes
    ) == "Ai, que amor! Que coisa mais linda!"


def test_real_numbers_are_kept():
    notes = {5: "Pois é , mas..."}
    text = "fechava às 5 horas da tarde"
    assert strip_note_numbers(text, notes) == text


def test_page_lines_drop_symbols_and_page_chrome():
    items = [
        Item(752.0, 47.0, "/X+GillSans", "Animals 1: Dog lovers 1"),  # header band
        Item(706.7, 90.0, "/X+GillSansMT", "MICHELLE:"),
        Item(704.8, 157.6, "/X+GillSansMT", "E cadê"),  # label sits ~2pt off
        Item(704.8, 192.5, "/X+ZapfDingbatsITC", "#"),  # note marker
        Item(704.8, 209.0, "/X+GillSansMT", "o Júnior?"),
        Item(690.9, 157.6, "/X+GillSansMT", "Where is Junior?"),
        Item(62.0, 40.0, "/X+GillSans", "9"),  # footer band
    ]
    assert page_lines(items) == [
        "MICHELLE: E cadê o Júnior?",
        "Where is Junior?",
    ]


def test_misspelled_speaker_is_fixed():
    def line(y, text):
        return Item(y, 90.0, "/X+GillSansMT", text)

    pages = [
        [line(700, "Travel 2: Hanging out at Breakfast 2")],
        [line(700, "DESINE: Oi!"), line(686, "Hi!")],
    ]
    lesson = parse_pdf(pages, 4)
    assert (lesson.location, lesson.title) == ("Travel 2", "Hanging out at Breakfast 2")
    assert [(x.speaker, x.text, x.translation) for x in lesson.lines] == [
        ("Denise", "Oi!", "Hi!")]


def test_behind_the_scenes_turns_are_not_split():
    def line(y, text):
        return Item(y, 90.0, "/X+GillSansMT", text)

    pages = [
        [line(700, "Studio 1: Behind the Scenes, Ói, que safado!")],
        [line(700, "ORLANDO: It’d be nice to have different words, one for"),
         line(686, "‘safado’ and one for ‘desgraçado’...")],
    ]
    lesson = parse_pdf(pages, 34)
    assert [(x.text, x.translation) for x in lesson.lines] == [(
        "It’d be nice to have different words, one for "
        "‘safado’ and one for ‘desgraçado’...", None)]
