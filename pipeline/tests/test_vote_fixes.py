#!/usr/bin/env python3
"""Regression tests for the vote-detection correctness fixes.

Every test here is built from an input that was observed to produce a wrong
answer, not from an invented one. The board fixture is the real Tesseract word
output for `board_05_16233.jpg` of clip 14821 (Sep 1 2026, the 5-1-0-1 board on
agenda item 9B), including the person glyphs Tesseract misreads as text, which
is what made the row grouping collapse names and values into one row.

Run with:

    .venv/bin/python -m unittest discover -s pipeline/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image

import detect_and_parse_votes as detect
import roster as roster_mod

ERA = roster_mod.era_for("2026-09-01")


def word(text: str, left: int, top: int, width: int, height: int, conf: float = 90.0) -> dict:
    return {
        "text": text, "left": left, "top": top,
        "width": width, "height": height, "conf": conf,
    }


# Real OCR output for board_05_16233.jpg, board crop 992x331 upscaled 3x to
# 2976x993. 'z', 'r', '7' and 'z£' are the coloured person glyphs; the value
# words for the second member row sit 35-50px below the names in the same
# visual band, which is what the old grouping tolerance swallowed.
BOARD_05_WORDS = [
    word("Voting", 105, 100, 150, 47, 96), word("Results", 267, 99, 171, 42, 97),
    word("5", 875, 398, 31, 42, 93), word("1", 1274, 399, 16, 40, 97),
    word("0", 1661, 398, 30, 42, 79), word("1", 2060, 396, 16, 39, 97),
    word("Yes", 863, 462, 58, 41, 96), word("No", 1259, 462, 46, 41, 96),
    word("Abstain", 1612, 462, 127, 40, 96), word("Recuse", 2013, 464, 114, 27, 71),
    # first member row: names
    word("z", 133, 665, 33, 39, 55),
    word("Councilmember", 215, 650, 246, 30, 82), word("Barnett", 470, 651, 114, 29, 96),
    word("r", 831, 665, 33, 40, 0),
    word("Councilmember", 914, 650, 245, 30, 92), word("Gerson", 1168, 651, 112, 29, 96),
    word("z", 1531, 666, 32, 38, 0),
    word("Councilmember", 1612, 650, 245, 31, 93), word("Kartsonis", 1868, 651, 145, 29, 92),
    word("7", 2228, 665, 34, 40, 0),
    word("Councilmember", 2311, 650, 245, 30, 93), word("Lewis", 2566, 652, 88, 29, 96),
    # first member row: values
    word("Yes", 212, 692, 50, 37, 97), word("Yoo", 911, 692, 50, 37, 77),
    word("Wecure", 1609, 692, 96, 37, 0), word("Yeo", 2312, 698, 41, 21, 71),
    # second member row: names and values, interleaved in reading order
    word("z\u00a3", 129, 765, 37, 59, 35),
    word("Mo", 211, 803, 39, 45, 78),
    word("Councilmember", 215, 768, 246, 29, 58), word("Lieu", 470, 768, 65, 29, 92),
    word("z", 831, 781, 33, 39, 21),
    word("Yes", 910, 803, 49, 45, 78),
    word("Councilmember", 914, 768, 246, 29, 95), word("Sheikh", 1169, 768, 107, 29, 96),
    word("z", 1530, 781, 34, 39, 39),
    word("Yes", 1613, 816, 41, 21, 84),
    word("Mayor", 1614, 768, 95, 34, 96), word("Kalani", 1719, 768, 96, 29, 96),
]

# Real glyph positions and hues for the same board, in board (un-upscaled)
# coordinates. Each sits 27-29px left of its name column.
BOARD_05_ICONS = [
    {"value": "YES", "hue": 117.2, "pixels": 102, "left": 43, "right": 55,
     "top": 223, "bottom": 234, "width": 12, "height": 12, "centre_y": 229.0},
    {"value": "YES", "hue": 117.5, "pixels": 106, "left": 277, "right": 288,
     "top": 222, "bottom": 233, "width": 12, "height": 12, "centre_y": 227.5},
    {"value": "RECUSE", "hue": 37.1, "pixels": 115, "left": 510, "right": 521,
     "top": 222, "bottom": 234, "width": 12, "height": 13, "centre_y": 228.0},
    {"value": "YES", "hue": 118.0, "pixels": 104, "left": 742, "right": 754,
     "top": 223, "bottom": 235, "width": 13, "height": 13, "centre_y": 229.0},
    {"value": "NO", "hue": 7.7, "pixels": 48, "left": 44, "right": 54,
     "top": 264, "bottom": 274, "width": 11, "height": 11, "centre_y": 269.0},
    {"value": "YES", "hue": 119.0, "pixels": 116, "left": 276, "right": 288,
     "top": 261, "bottom": 272, "width": 13, "height": 12, "centre_y": 266.5},
    {"value": "YES", "hue": 116.7, "pixels": 110, "left": 510, "right": 521,
     "top": 261, "bottom": 272, "width": 12, "height": 12, "centre_y": 266.5},
]

TRUE_BOARD_05_VOTES = {
    "Linda Barnett": "YES",
    "Jeremy Gerson": "YES",
    "David Kartsonis": "RECUSE",
    "Bridgett Lewis": "YES",
    "Betty Lieu": "NO",
    "Asam Sheikh": "YES",
    "Sharon Kalani": "YES",
}


def row_of(rows: list[list[dict]], text: str) -> list[dict]:
    for row in rows:
        if any(w["text"] == text for w in row):
            return row
    raise AssertionError(f"no row contains {text!r}")


def texts(row: list[dict]) -> list[str]:
    return [w["text"] for w in row]


# --------------------------------------------------------------------------
# C1: a failed motion must never read as passed
# --------------------------------------------------------------------------

class TestResultNormalisation(unittest.TestCase):
    """C1. `RESULT_WORDS["passed"]` held the bare token "pass" and was matched
    as a substring of an alpha-squashed string, with the dict iterating
    tie -> passed -> failed."""

    NEVER_PASSED = [
        "Result: Motion Failed to Pass",
        "Motion Failed, did not pass",
        "Not Passed",
        "Motion did not pass",
        "Motion Passed - Denied",
    ]

    def test_proven_failures_never_read_as_passed(self):
        for text in self.NEVER_PASSED:
            with self.subTest(text=text):
                self.assertNotEqual(roster_mod.normalize_result(text), "passed")
                self.assertNotEqual(roster_mod.normalize_result_fuzzy(text)[0], "passed")

    def test_explicit_failures_read_as_failed(self):
        for text in ["Result: Motion Failed to Pass", "Motion Failed, did not pass"]:
            with self.subTest(text=text):
                self.assertEqual(roster_mod.normalize_result(text), "failed")

    def test_negated_or_contradictory_lines_are_unreadable(self):
        for text in ["Not Passed", "Motion did not pass", "Motion Passed - Denied"]:
            with self.subTest(text=text):
                self.assertIsNone(roster_mod.normalize_result(text))
                self.assertIsNone(roster_mod.normalize_result_fuzzy(text)[0])

    # Raw payloads Tesseract actually returned for the result bar on frames
    # inside a board window on clip 14821. Each one reported an outcome that
    # contradicted the board it came from: a 3-4 character fragment landing on a
    # short vocabulary word ("ost" scores 0.857 against "lost", "ened" 0.800
    # against "denied", "tice" 0.857 against "tie").
    NOISE = [
        ("Motion ened", 16119.8),
        ("Rea te ost", 16233.8),
        ("Rant; ete ened", 16236.8),
        ("o- Pcie ened", 16237.8),
        ("Reauit; tite. se .eul", 7077.9),
        ("nina tie bE", 18824.6),
        ("eaita tice", 25962.8),
        ("Gita tice", 25962.8),
        ("tie Ot", 18825.6),
        ("dss tie", 25964.8),
    ]

    def test_short_word_noise_does_not_manufacture_an_outcome(self):
        for text, timestamp in self.NOISE:
            with self.subTest(text=text, t=timestamp):
                self.assertIsNone(roster_mod.normalize_result(text))
                self.assertIsNone(roster_mod.normalize_result_fuzzy(text)[0])

    # The counterpart to NOISE: every genuine read observed on the same clip,
    # including the ones the live output already carries. Tightening the
    # vocabulary must not cost any of these.
    GENUINE = (
        [(t, "passed") for t in (
            "Moton Pessed", "Motor Passed", "Movon Passed", "Motion Passed",
            "Moron Passed", "orion Passed", "Motono Pessed", "Motorn Passed",
            "Motion Possed", "Resutt: Motion Passed", "Vonen Passed",
            "soven Passed", "socien Passed", "Monon Passed", "Wenet Paseed",
            "seven Passed",
        )]
        + [(t, "failed") for t in (
            "Motion Failed", "Motion Faled", "Motion Falled", "Motion Denled",
        )]
        + [(t, "tie") for t in (
            "Motion Tied", "Result: Motion Tied", "Tie", "Tie Vote", "Motion Tie",
        )]
    )

    def test_real_reads_still_resolve(self):
        for text, expected in self.GENUINE:
            with self.subTest(text=text):
                self.assertEqual(roster_mod.normalize_result_fuzzy(text)[0], expected)

    def test_a_short_outcome_word_must_carry_the_line(self):
        """"tie" is three characters, so an exact hit on it inside a noisy line
        is not evidence. Framing words do not count as content."""
        self.assertEqual(roster_mod.normalize_result("Motion Tied"), "tie")
        self.assertEqual(roster_mod.normalize_result("Result: Motion Tie"), "tie")
        self.assertEqual(roster_mod.normalize_result("Tie Vote"), "tie")
        self.assertIsNone(roster_mod.normalize_result("nina tie bE"))
        self.assertIsNone(roster_mod.normalize_result("qq tie zz ww"))
        self.assertIsNone(roster_mod.normalize_result("tie Ot"))
        self.assertIsNone(roster_mod.normalize_result("dss tie"))

    def test_short_vocabulary_words_are_not_reachable_by_fuzzy_match(self):
        """A long garbage token must not match a short outcome word."""
        for text in ["tice", "ost", "tite", "fai1", "1ost"]:
            with self.subTest(text=text):
                self.assertIsNone(roster_mod.normalize_result_fuzzy(text)[0])

    def test_fuzzy_path_cannot_bypass_the_negation_guard(self):
        # "pass" scores 0.80 against "passed", over FUZZY_RESULT_CUTOFF, so the
        # guard has to exist on the fuzzy path too and not only on the exact one.
        self.assertIsNone(roster_mod.normalize_result_fuzzy("Motion did not pass")[0])

    def test_real_result_bars_still_read(self):
        # Every result_raw string the live run produced for clip 14821.
        for text in [
            "| Resutt: Motion Passed |", "Vonen Passed", "soven Passed",
            "| | Rosutt: socien Passed", "Monon Passed '", "| Reeull: Wenet Paseed",
            "seven Passed", "| Rewutt: Motion Passed",
        ]:
            with self.subTest(text=text):
                self.assertEqual(roster_mod.normalize_result_fuzzy(text)[0], "passed")

    def test_genuine_failures_and_ties_read(self):
        self.assertEqual(roster_mod.normalize_result("Motion Failed"), "failed")
        self.assertEqual(roster_mod.normalize_result("Motion Denied"), "failed")
        self.assertEqual(roster_mod.normalize_result("Result: Tie"), "tie")
        self.assertEqual(roster_mod.normalize_result("Motion Carried"), "passed")
        self.assertEqual(roster_mod.normalize_result_fuzzy("Motion Faled")[0], "failed")

    def test_bare_pass_is_not_in_the_vocabulary(self):
        self.assertNotIn("pass", roster_mod.RESULT_WORDS["passed"])


# --------------------------------------------------------------------------
# C2: a lost tally digit must be fatal
# --------------------------------------------------------------------------

def tally_rows(digits: list[str]) -> list[list[dict]]:
    """A board's digit row and label row with the real x positions."""
    lefts = [875, 1274, 1661, 2060]
    return detect.group_rows(
        [word(d, lefts[i], 398, 31, 42) for i, d in enumerate(digits)]
        + [
            word("Yes", 863, 462, 58, 41), word("No", 1259, 462, 46, 41),
            word("Abstain", 1612, 462, 127, 40), word("Recuse", 2013, 464, 114, 27),
        ]
    )


class TestTallyDigits(unittest.TestCase):
    """C2. `parse_tally` ended with `tally.setdefault(key, 0)`, so a digit
    Tesseract turned into a letter silently became a zero."""

    def test_digit_misread_as_a_letter_rejects_the_board(self):
        # The proven case: Tesseract read the four digits as 5, l, 0, 1.
        tally, reason = detect.parse_tally_detail(tally_rows(["5", "l", "0", "1"]))
        self.assertIsNone(tally, "a lost digit must not produce a tally")
        self.assertIn("noes", reason)
        self.assertIn("zero", reason)

    def test_the_old_behaviour_would_have_erased_a_dissenter(self):
        # Documents exactly what used to happen: noes silently became 0, which
        # combined with a dropped member row to validate as unanimous.
        tally = detect.parse_tally(tally_rows(["5", "l", "0", "1"]))
        self.assertIsNone(tally)
        if tally is not None:  # pragma: no cover - guard against a regression
            self.assertNotEqual(tally["noes"], 0)

    def test_all_four_digits_present_parses(self):
        self.assertEqual(
            detect.parse_tally(tally_rows(["5", "1", "0", "1"])),
            {"ayes": 5, "noes": 1, "abstentions": 0, "recused": 1},
        )

    def test_three_column_board_without_recuse_defaults_recused_to_zero(self):
        """Clip 14798 prints Yes/No/Abstain only. Recused is 0, not missing."""
        lefts = [875, 1274, 1661]
        rows = detect.group_rows(
            [word(d, lefts[i], 398, 31, 42) for i, d in enumerate(["6", "0", "0"])]
            + [
                word("Yes", 863, 462, 58, 41),
                word("No", 1259, 462, 46, 41),
                word("Abstain", 1612, 462, 127, 40),
            ]
        )
        self.assertEqual(
            detect.parse_tally(rows),
            {"ayes": 6, "noes": 0, "abstentions": 0, "recused": 0},
        )

    def test_real_14798_ocr_words_parse_without_a_recuse_label(self):
        """Tesseract output from crops/14798/board_02_9437.jpg (no Recuse box)."""
        rows = detect.group_rows([
            word("6", 958, 399, 31, 42, 96),
            word("0", 1464, 399, 31, 42, 85),
            word("0", 1971, 396, 30, 41, 82),
            word("Yes", 943, 458, 62, 46, 96),
            word("No", 1455, 458, 47, 46, 96),
            word("Abstain", 1926, 464, 121, 27, 96),
        ])
        self.assertEqual(
            detect.parse_tally(rows),
            {"ayes": 6, "noes": 0, "abstentions": 0, "recused": 0},
        )

    def test_four_column_board_still_rejects_a_lost_recuse_digit(self):
        tally, reason = detect.parse_tally_detail(tally_rows(["6", "0", "0", "l"]))
        self.assertIsNone(tally)
        self.assertIn("recused", reason)

    def test_zero_is_read_as_zero_when_it_is_printed(self):
        self.assertEqual(
            detect.parse_tally(tally_rows(["7", "0", "0", "0"])),
            {"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0},
        )

    def test_real_board_tally_parses(self):
        rows = detect.group_rows(BOARD_05_WORDS)
        self.assertEqual(
            detect.parse_tally(rows),
            {"ayes": 5, "noes": 1, "abstentions": 0, "recused": 1},
        )


# --------------------------------------------------------------------------
# C4: the name line must not absorb the value line
# --------------------------------------------------------------------------

class TestRowGrouping(unittest.TestCase):
    """C4. `group_rows` scaled its tolerance by the row's *first* word, which on
    the second member row is a person glyph misread as text ("z£", h=59). That
    opened a window wide enough to swallow the value line 38px below."""

    def setUp(self):
        self.rows = detect.group_rows(BOARD_05_WORDS)

    def test_second_member_row_does_not_contain_its_values(self):
        names = row_of(self.rows, "Lieu")
        self.assertIn("Sheikh", texts(names))
        self.assertIn("Kalani", texts(names))
        # "Mo" is Lieu's value, the two "Yes" at t=803/816 are Sheikh's and
        # Kalani's. None of them belong on the name row.
        self.assertNotIn("Mo", texts(names))
        self.assertEqual(
            [w for w in names if w["top"] > 800], [],
            "no word from the value line may share the name row",
        )

    def test_value_line_forms_its_own_row(self):
        values = row_of(self.rows, "Mo")
        self.assertNotIn("Lieu", texts(values))
        self.assertNotIn("Councilmember", texts(values))

    def test_a_single_tall_glyph_cannot_widen_a_row(self):
        # Same three words at the same y, but with a 62px-high glyph leading.
        # The glyph must not pull in the word 40px below it.
        words = [
            word("ry", 100, 100, 30, 62),
            word("Councilmember", 150, 110, 240, 28),
            word("Barnett", 400, 110, 110, 28),
            word("Yes", 150, 150, 48, 28),
            word("Councilmember", 900, 110, 240, 28),
            word("Gerson", 1150, 110, 110, 28),
            word("Yes", 900, 150, 48, 28),
        ]
        rows = detect.group_rows(words)
        self.assertNotIn("Yes", texts(row_of(rows, "Barnett")))

    def test_all_seven_members_are_found(self):
        entries = detect.find_name_entries(self.rows, ERA)
        self.assertEqual(
            sorted(e["member"].name for e in entries),
            sorted(TRUE_BOARD_05_VOTES),
        )

    def test_column_is_anchored_on_the_title_not_the_surname(self):
        entries = {e["member"].name: e for e in detect.find_name_entries(self.rows, ERA)}
        for name in TRUE_BOARD_05_VOTES:
            with self.subTest(name=name):
                self.assertEqual(entries[name]["column_anchor"], "title")

    def test_column_grid_is_the_four_printed_columns(self):
        entries = detect.find_name_entries(self.rows, ERA)
        grid = entries[0]["column_grid"]
        self.assertEqual(len(grid), 4)
        for expected, actual in zip([215, 914, 1613, 2311], grid):
            self.assertLess(abs(expected - actual), 5)

    def test_value_in_the_same_row_as_the_name_is_still_found(self):
        # Sheikh's and Kalani's values are on the second member row. Before the
        # fix `parse_individual_votes` only scanned `rows[row_index + 1:]`, so a
        # value sharing the name's row was never looked at.
        entries = {e["member"].name: e for e in detect.find_name_entries(self.rows, ERA)}
        for name in ("Asam Sheikh", "Sharon Kalani"):
            with self.subTest(name=name):
                value, raw, score, box = detect.read_value_for_entry(
                    self.rows, entries[name]
                )
                self.assertEqual(value, "YES")
                self.assertEqual(raw, "Yes")
                self.assertIsNotNone(box, "the value box must be recorded")

    def test_barnett_value_on_the_following_row_is_found(self):
        entries = {e["member"].name: e for e in detect.find_name_entries(self.rows, ERA)}
        value, raw, _score, _box = detect.read_value_for_entry(
            self.rows, entries["Linda Barnett"]
        )
        self.assertEqual((value, raw), ("YES", "Yes"))


# --------------------------------------------------------------------------
# C3 / H1: the two channels must agree, per member
# --------------------------------------------------------------------------

def parsed_from_board(words: list[dict], icons: list[dict]) -> dict:
    rows = detect.group_rows(words)
    parsed = detect.parse_individual_votes(rows, ERA, None, icons)
    tally, tally_problem = detect.parse_tally_detail(rows)
    parsed["vote_tally"] = tally
    parsed["tally_problem"] = tally_problem
    parsed["result"] = "passed"
    parsed["vote_sources"] = {
        name: detail["source"] for name, detail in parsed["vote_details"].items()
    }
    return parsed


# The two value words to permute, identified by position so the tally labels
# ("Yes" at 863,462 and "No" at 1259,462) cannot be picked up by mistake.
LEWIS_VALUE_AT = (2312, 698)
LIEU_VALUE_AT = (211, 803)


def swap_value_words(words: list[dict], at_a: tuple[int, int], at_b: tuple[int, int]) -> list[dict]:
    """Swap the text of two value words, i.e. permute the text channel only."""
    out = [dict(w) for w in words]
    first = next(w for w in out if (w["left"], w["top"]) == at_a)
    second = next(w for w in out if (w["left"], w["top"]) == at_b)
    first["text"], second["text"] = second["text"], first["text"]
    return out


class TestChannelAgreement(unittest.TestCase):
    """C3 and H1. Every check in `validate` was a multiset count, so it could
    not see a permutation of values between members; and a disagreement between
    the glyph and the word was resolved by overwriting the word, silently."""

    def setUp(self):
        # Give Lewis and Lieu legible value words so the text channel has an
        # opinion to permute. Everything else is the real board.
        self.words = [dict(w) for w in BOARD_05_WORDS]
        for w in self.words:
            if w["text"] == "Yeo":       # Lewis's value
                w["text"] = "Yes"
            elif w["text"] == "Mo":      # Lieu's value
                w["text"] = "No"

    def test_correct_board_has_no_conflicts(self):
        parsed = parsed_from_board(self.words, BOARD_05_ICONS)
        self.assertEqual(parsed["icon_conflicts"], [])
        self.assertEqual(parsed["individual_votes"]["Bridgett Lewis"], "YES")
        self.assertEqual(parsed["individual_votes"]["Betty Lieu"], "NO")
        for name in ("Bridgett Lewis", "Betty Lieu", "Linda Barnett", "Asam Sheikh"):
            with self.subTest(name=name):
                self.assertEqual(
                    parsed["vote_details"][name]["source"], detect.VOTE_SOURCE_BOTH
                )
        problems, _absent = detect.validate(parsed, ERA, "absent", "agree")
        self.assertEqual(problems, [], f"clean board should validate: {problems}")

    def test_every_multiset_check_is_blind_to_a_permutation(self):
        # The review's proof: take the real 5-1-0-1 record and swap Lewis's YES
        # with Lieu's NO. Ayes, noes, abstentions and recused are all unchanged,
        # so every count-based check in validate() still agrees with the slide.
        permuted = dict(TRUE_BOARD_05_VOTES)
        permuted["Bridgett Lewis"], permuted["Betty Lieu"] = (
            permuted["Betty Lieu"], permuted["Bridgett Lewis"],
        )
        counted: dict[str, int] = {}
        for value in permuted.values():
            counted[detect.VOTE_TO_TALLY[value]] = (
                counted.get(detect.VOTE_TO_TALLY[value], 0) + 1
            )
        self.assertEqual(counted["ayes"], 5)
        self.assertEqual(counted["noes"], 1)
        self.assertEqual(counted["recused"], 1)

        # Fed to validate() with only count information, it passes -- which is
        # exactly the hole. Nothing about the tally can reveal a permutation.
        record = {
            "vote_tally": {"ayes": 5, "noes": 1, "abstentions": 0, "recused": 1},
            "result": "passed",
            "individual_votes": permuted,
            "vote_sources": {name: detect.VOTE_SOURCE_BOTH for name in permuted},
            "result_consensus": {"value": "passed", "count": 4, "reads": 4,
                                 "total": 4, "fraction": 1.0, "tied": False},
            "vote_consensus": {},
        }
        self.assertEqual(detect.validate(record, ERA, "absent", "both")[0], [])

    def test_permuted_text_channel_is_caught_by_the_icon_channel(self):
        # A permutation physically arises when the text channel assigns values
        # to the wrong columns. The glyphs are laid out independently, so they
        # do not permute with it, and the per-member cross-check sees it.
        permuted = swap_value_words(self.words, LEWIS_VALUE_AT, LIEU_VALUE_AT)
        parsed = parsed_from_board(permuted, BOARD_05_ICONS)

        conflicted = {c["member"] for c in parsed["icon_conflicts"]}
        self.assertEqual(conflicted, {"Bridgett Lewis", "Betty Lieu"})
        for name in ("Bridgett Lewis", "Betty Lieu"):
            with self.subTest(name=name):
                self.assertEqual(
                    parsed["vote_details"][name]["source"], detect.VOTE_SOURCE_CONFLICT
                )

        problems, _absent = detect.validate(parsed, ERA, "absent", "agree")
        self.assertTrue(problems, "a permutation of values must be blocking")
        self.assertTrue(any("icon/OCR disagreement" in p for p in problems), problems)

    def test_a_conflicting_read_is_blocking_under_every_policy_but_any(self):
        permuted = swap_value_words(self.words, LEWIS_VALUE_AT, LIEU_VALUE_AT)
        parsed = parsed_from_board(permuted, BOARD_05_ICONS)
        for policy in ("both", "agree"):
            with self.subTest(policy=policy):
                problems, _absent = detect.validate(parsed, ERA, "absent", policy)
                self.assertTrue(any("disagreement" in p for p in problems), problems)

    def test_value_bounding_box_is_persisted_for_audit(self):
        parsed = parsed_from_board(self.words, BOARD_05_ICONS)
        for name in TRUE_BOARD_05_VOTES:
            detail = parsed["vote_details"][name]
            if detail["ocr_value"]:
                with self.subTest(name=name):
                    box = detail["value_box"]
                    self.assertIsNotNone(box)
                    self.assertIn("left", box)
                    self.assertIn("top", box)

    def test_icon_only_read_is_marked_not_silently_corroborated(self):
        # Kartsonis reads "Wecure", Gerson "Yoo", and Lieu's box yields nothing
        # that normalizes, so on those three rows the glyph is the only channel
        # with an opinion. The original code recorded a conflict only when the
        # text read produced a value, so these were indistinguishable from a
        # corroborated read. They have to be visible in the record.
        parsed = parsed_from_board(BOARD_05_WORDS, BOARD_05_ICONS)
        icon_only = {
            name
            for name, detail in parsed["vote_details"].items()
            if detail["source"] == detect.VOTE_SOURCE_ICON
        }
        self.assertEqual(
            icon_only, {"Jeremy Gerson", "David Kartsonis", "Betty Lieu"}
        )
        for name in icon_only:
            self.assertIsNone(parsed["vote_details"][name]["ocr_value"])
        # The glyph still supplies the vote, and it is the correct one.
        self.assertEqual(parsed["individual_votes"]["David Kartsonis"], "RECUSE")
        self.assertEqual(parsed["individual_votes"]["Betty Lieu"], "NO")

        problems, _absent = detect.validate(parsed, ERA, "absent", "both")
        self.assertTrue(
            any("single channel" in p for p in problems),
            f"policy 'both' must block an icon-only read: {problems}",
        )
        for name in icon_only:
            self.assertTrue(
                any(name in p for p in problems),
                f"{name} must be named in the problem: {problems}",
            )

    def test_a_mangled_recuse_is_not_decoded_into_a_yes(self):
        """The closed-vocabulary decoder folds initial W onto Y, because "ves" is
        a real read of a YES. Applied to "Wecure" -- a real read of Kartsonis's
        RECUSE -- that inverts a recusal into an affirmative vote."""
        self.assertIsNone(roster_mod.normalize_vote("Wecure"))
        # The reads the decoder exists for must still work.
        for token in ("ves", "Yee", "Yeu"):
            with self.subTest(token=token):
                self.assertEqual(roster_mod.normalize_vote(token), "YES")
        # "Yor" and "Yoo" carry a Y initial but their nearest vocabulary word is
        # "no" (0.40, against 0.33 for "yes"), so the initial and the shape of
        # the word disagree and neither is trusted. Refusing them costs two
        # measured YES reads on this clip and buys immunity to the inverse case.
        for token in ("Yor", "Yoo"):
            with self.subTest(token=token):
                self.assertIsNone(roster_mod.normalize_vote(token))
        # And a fuzzy-reachable RECUSE is still recovered.
        self.assertEqual(roster_mod.normalize_vote("Recure"), "RECUSE")

    def test_agree_policy_allows_a_single_channel(self):
        parsed = parsed_from_board(BOARD_05_WORDS, BOARD_05_ICONS)
        problems, _absent = detect.validate(parsed, ERA, "absent", "agree")
        self.assertFalse(
            any("single channel" in p for p in problems),
            f"policy 'agree' should tolerate one channel: {problems}",
        )

    def test_no_vote_is_ever_inferred_from_the_tally(self):
        # Drop Kalani's glyph and her value word. She must come back
        # unreadable, never back-filled from the 5-1-0-1 tally.
        words = [w for w in self.words if not (w["text"] == "Yes" and w["top"] == 816)]
        icons = [i for i in BOARD_05_ICONS if not (i["left"] == 510 and i["centre_y"] > 250)]
        parsed = parsed_from_board(words, icons)
        self.assertNotIn("Sharon Kalani", parsed["individual_votes"])
        self.assertIn("Sharon Kalani", [u["member"] for u in parsed["unresolved"]])


# --------------------------------------------------------------------------
# H2: phantom icons
# --------------------------------------------------------------------------

class TestIconGeometry(unittest.TestCase):
    """H2. The panel's green edge glow came back as YES at hue 80.7 with 596
    pixels: four under the old size ceiling and 0.7 over the old YES floor."""

    def board_with(self, shapes: list[tuple[int, int, int, int, tuple[int, int, int]]]) -> Image.Image:
        arr = np.zeros((331, 992, 3), dtype=np.uint8)
        arr[:, :] = (12, 12, 14)
        for left, top, w, h, colour in shapes:
            arr[top : top + h, left : left + w] = colour
        return Image.fromarray(arr)

    def test_edge_glow_sliver_is_not_a_vote(self):
        # 4x150 sliver of the same panel green that scored hue ~80.
        board = self.board_with([(12, 190, 4, 150, (60, 200, 90))])
        self.assertEqual(detect.find_vote_icons(board), [])

    def test_real_person_glyph_is_found(self):
        board = self.board_with([(43, 223, 12, 12, (40, 190, 70))])
        icons = detect.find_vote_icons(board)
        self.assertEqual(len(icons), 1)
        self.assertEqual(icons[0]["value"], "YES")

    def test_sliver_and_glyph_together_yield_only_the_glyph(self):
        board = self.board_with(
            [
                (12, 190, 4, 150, (60, 200, 90)),
                (970, 190, 4, 130, (60, 200, 90)),
                (43, 223, 12, 12, (40, 190, 70)),
            ]
        )
        icons = detect.find_vote_icons(board)
        self.assertEqual(len(icons), 1)
        self.assertEqual(icons[0]["left"], 43)

    def test_hue_between_bands_is_unknown_rather_than_no(self):
        # The old table ran NO from 0-25 and RECUSE from 25-55, so a recuse
        # glyph measured at 36.5 sat 11 degrees from being read as a NO. The
        # bands now have dead zones; a hue in one classifies as nothing.
        for lo, hi, _value in detect.ICON_HUE_CLASSES:
            self.assertTrue(0.0 <= lo < hi <= 360.0)
        bands = sorted((lo, hi) for lo, hi, _ in detect.ICON_HUE_CLASSES)
        gaps = [bands[i + 1][0] - bands[i][1] for i in range(len(bands) - 1)]
        self.assertTrue(
            all(gap >= 8.0 for gap in gaps),
            f"every hue boundary needs a guard band, got gaps {gaps}",
        )

    def test_recuse_hue_is_comfortably_inside_its_band(self):
        recuse = next(
            (lo, hi) for lo, hi, value in detect.ICON_HUE_CLASSES if value == "RECUSE"
        )
        for observed in (36.5, 37.1):
            self.assertGreater(observed - recuse[0], 5.0)
            self.assertGreater(recuse[1] - observed, 5.0)

    def test_glyph_must_sit_at_its_column(self):
        entry = {
            "column_x": 215, "column_left": 215, "top": 651, "height": 29,
            "column_grid": [215.0, 914.0, 1613.0, 2311.0],
        }
        phantom = {"value": "YES", "hue": 80.7, "left": 12, "right": 15,
                   "centre_y": 229.0}
        real = {"value": "YES", "hue": 117.2, "left": 43, "right": 55,
                "centre_y": 229.0}
        self.assertIsNone(detect.icon_for_entry([phantom], entry))
        self.assertIs(detect.icon_for_entry([phantom, real], entry), real)


# --------------------------------------------------------------------------
# H3: minority reads and insertion-order ties
# --------------------------------------------------------------------------

class TestConsensusSupport(unittest.TestCase):
    """H3. `results.most_common(1)[0][0]` had no minimum and broke ties on
    insertion order. Agreement is measured against frames that produced a
    result, not against frames whose result bar did not read at all."""

    def test_tie_resolves_to_nothing_not_to_insertion_order(self):
        counts = detect.Counter({"passed": 2, "failed": 2})
        pick = detect.consensus_pick(counts, 4)
        self.assertIsNone(pick["value"])
        self.assertTrue(pick["tied"])
        self.assertEqual(pick["candidates"], ["failed", "passed"])

    def test_insertion_order_does_not_decide(self):
        first = detect.consensus_pick(detect.Counter({"passed": 2, "failed": 2}), 4)
        second = detect.consensus_pick(detect.Counter({"failed": 2, "passed": 2}), 4)
        self.assertEqual(first["value"], second["value"])

    def test_unread_frames_do_not_block_a_unanimous_result_read(self):
        """A faint result bar often reads on 1 of 7 frames. That is absence,
        not disagreement — vote 4 on 14821 was 1/3 of frames that produced a
        result and is a hand-verified correct `passed`."""
        parsed = {
            "result": "passed",
            "result_consensus": {"value": "passed", "count": 1, "reads": 1,
                                 "total": 7, "fraction": 1 / 7, "tied": False},
            "vote_consensus": {},
        }
        self.assertEqual(detect._agreement_problems(parsed), [])

    def test_result_disagreement_among_reads_is_blocking(self):
        parsed = {
            "result": "passed",
            "result_consensus": {"value": "passed", "count": 1, "reads": 2,
                                 "total": 7, "fraction": 1 / 7, "tied": False},
            "vote_consensus": {},
        }
        problems = detect._agreement_problems(parsed)
        self.assertTrue(any("1/2" in p for p in problems), problems)

    def test_majority_result_is_accepted(self):
        parsed = {
            "result": "passed",
            "result_consensus": {"value": "passed", "count": 3, "reads": 3,
                                 "total": 5, "fraction": 0.6, "tied": False},
            "vote_consensus": {},
        }
        self.assertEqual(detect._agreement_problems(parsed), [])

    def test_per_member_tie_is_blocking(self):
        parsed = {
            "result": "passed",
            "result_consensus": {"value": "passed", "count": 4, "reads": 4,
                                 "total": 4, "fraction": 1.0, "tied": False},
            "vote_consensus": {
                "Betty Lieu": {"value": None, "count": 2, "reads": 4, "total": 4,
                               "fraction": 0.5, "tied": True,
                               "candidates": ["NO", "YES"]},
            },
        }
        problems = detect._agreement_problems(parsed)
        self.assertTrue(any("Betty Lieu" in p and "split" in p for p in problems), problems)

    def test_agreement_is_actually_read_by_validate(self):
        # The old validate() never looked at vote_agreement or result_agreement.
        parsed = {
            "vote_tally": {"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0},
            "result": "passed",
            "individual_votes": {m.name: "YES" for m in ERA.members},
            "vote_sources": {m.name: detect.VOTE_SOURCE_BOTH for m in ERA.members},
            "result_consensus": {"value": "passed", "count": 1, "reads": 2,
                                 "total": 7, "fraction": 1 / 7, "tied": False},
            "vote_consensus": {},
        }
        problems, _absent = detect.validate(parsed, ERA, "absent", "both")
        self.assertTrue(any("1/2" in p for p in problems), problems)


# --------------------------------------------------------------------------
# H4: OCR noise as a confident vote
# --------------------------------------------------------------------------

class TestVoteNormalisation(unittest.TestCase):
    """H4. `VOTE_SYNONYMS` held single letters and the difflib cutoff was 0.72,
    so 'es', 'eS', 'ye', 'y' read YES and 'n', 'Nes', 'Nol', 'NERS' read NO."""

    def test_proven_noise_is_rejected(self):
        for token in ["es", "eS", "ye", "y", "n", "Nes", "Nol", "NERS"]:
            with self.subTest(token=token):
                self.assertIsNone(roster_mod.normalize_vote(token))

    def test_single_letters_are_gone_from_the_vocabulary(self):
        self.assertNotIn("y", roster_mod.VOTE_SYNONYMS)
        self.assertNotIn("n", roster_mod.VOTE_SYNONYMS)

    def test_real_vote_words_still_read(self):
        for token, expected in [
            ("Yes", "YES"), ("No", "NO"), ("Abstain", "ABSTAIN"),
            ("Recuse", "RECUSE"), ("Absent", "ABSENT"), ("Ayes", "YES"),
            ("Noes", "NO"),
        ]:
            with self.subTest(token=token):
                self.assertEqual(roster_mod.normalize_vote(token), expected)

    def test_long_tokens_still_recover_from_one_bad_character(self):
        self.assertEqual(roster_mod.normalize_vote("recusod"), "RECUSE")
        self.assertEqual(roster_mod.normalize_vote("Abstalned"), "ABSTAIN")

    def test_highest_scoring_candidate_wins_not_the_leftmost(self):
        # A stray fragment sitting left of the real word must not take the vote.
        # 'Yes' scores 1.0; anything that reaches the window scores lower.
        entry = {
            "column_x": 215, "column_left": 215, "top": 651, "bottom": 680,
            "height": 29, "row_index": 0,
            "column_grid": [215.0, 914.0, 1613.0, 2311.0],
        }
        rows = [
            [word("Councilmember", 215, 651, 246, 29), word("Barnett", 470, 651, 114, 29)],
            [word("recusod", 216, 692, 90, 37), word("Yes", 250, 692, 50, 37)],
        ]
        value, raw, score, _box = detect.read_value_for_entry(rows, entry)
        self.assertEqual((value, raw), ("YES", "Yes"))
        self.assertEqual(score, 1.0)


# --------------------------------------------------------------------------
# H5: cluster splitting
# --------------------------------------------------------------------------

GOOD = (7, 0, 0, 0)
BAD = (-1, -1, -1, -1)
OTHER = (5, 1, 0, 1)


def presence_frames(keys: list[tuple[int, ...]], present: list[bool] | None = None,
                    start: float = 100.0, step: float = 1.0) -> list[dict]:
    present = present if present is not None else [True] * len(keys)
    return [
        {
            "frame": f"f{i}", "video_timestamp": start + i * step,
            "_tally_key": key, "_present": flag, "_detected": True,
        }
        for i, (key, flag) in enumerate(zip(keys, present))
    ]


class TestClusterSplitting(unittest.TestCase):
    """H5. Grouping by runs of *equal* tally split one vote in two when a frame
    misread, and merged two votes into one when their tallies matched."""

    def test_one_bad_frame_does_not_bisect_a_vote(self):
        groups = detect.group_by_presence(
            presence_frames([GOOD, GOOD, BAD, GOOD, GOOD])
        )
        self.assertEqual(len(groups), 1, "a misread frame is not a new vote")
        self.assertEqual(len(groups[0]), 5, "every frame stays in the one vote")

    def test_no_frame_is_assigned_to_two_votes(self):
        groups = detect.group_by_presence(
            presence_frames([GOOD, GOOD, BAD, GOOD, GOOD])
        )
        names = [f["frame"] for g in groups for f in g]
        self.assertEqual(len(names), len(set(names)))

    def test_two_identical_votes_separated_by_a_gap_stay_separate(self):
        # Two 7-0-0-0 votes with the board off screen between them: the consent
        # calendar case where the second vote used to disappear entirely.
        keys = [GOOD] * 4 + [BAD] * 3 + [GOOD] * 4
        present = [True] * 4 + [False] * 3 + [True] * 4
        groups = detect.group_by_presence(presence_frames(keys, present))
        self.assertEqual(len(groups), 2)
        self.assertEqual([len(g) for g in groups], [4, 4])

    def test_a_lasting_tally_change_with_no_gap_still_splits(self):
        groups = detect.group_by_presence(
            presence_frames([GOOD, GOOD, GOOD, OTHER, OTHER, OTHER])
        )
        self.assertEqual(len(groups), 2)

    def test_same_tally_either_side_of_another_is_merged(self):
        groups = detect.group_by_presence(
            presence_frames([GOOD, GOOD, OTHER, OTHER, GOOD, GOOD])
        )
        keys = {tuple(sorted(f["frame"] for f in g)) for g in groups}
        self.assertEqual(len(groups), 2)
        self.assertIn(("f0", "f1", "f4", "f5"), keys)

    def test_non_contiguous_group_is_flagged(self):
        frames = presence_frames([GOOD, GOOD, OTHER, OTHER, GOOD, GOOD])
        groups = detect.group_by_presence(frames)
        merged = next(g for g in groups if len(g) == 4)
        self.assertTrue(
            any(f.get("_non_contiguous") for f in merged),
            "a group whose frames are not contiguous in time must be flagged",
        )

    def test_stabilize_absorbs_a_single_frame_anomaly(self):
        self.assertEqual(
            detect.stabilize_tally_keys([GOOD, GOOD, BAD, GOOD, GOOD]),
            [GOOD] * 5,
        )

    def test_stabilize_keeps_a_lasting_change(self):
        self.assertEqual(
            detect.stabilize_tally_keys([GOOD, GOOD, OTHER, OTHER]),
            [GOOD, GOOD, OTHER, OTHER],
        )


# --------------------------------------------------------------------------
# H6: roster era safety
# --------------------------------------------------------------------------

class TestRosterEra(unittest.TestCase):
    """H6 and L5. An undated clip fell back to Jan 1, which resolves to the
    pre-turnover era holding a completely different council."""

    def test_undated_clip_would_have_picked_the_wrong_council(self):
        era = roster_mod.era_for("2026-01-01")
        self.assertEqual(era.key, "2024-pre-turnover")
        self.assertTrue(era.verified)
        names = {m.name for m in era.members}
        self.assertIn("George Chen", names)
        self.assertNotIn("Linda Barnett", names)

    def test_unverified_era_is_detectable(self):
        # archive-pre-2024 remains unverified; modern eras are verified.
        self.assertFalse(roster_mod.era_for("2010-06-01").verified)
        self.assertTrue(roster_mod.era_for("2026-01-01").verified)
        self.assertTrue(roster_mod.era_for("2026-09-01").verified)

    def test_researched_eras_cover_2018_through_2024(self):
        self.assertEqual(
            roster_mod.era_for("2018-07-09").key, "2016-furey-herring"
        )
        self.assertEqual(
            roster_mod.era_for("2018-07-10").key, "2018-furey-chen-mattucci"
        )
        self.assertEqual(
            roster_mod.era_for("2019-07-01").key, "2019-furey-herring-vacant"
        )
        self.assertEqual(
            roster_mod.era_for("2020-05-12").key, "2020-furey-district"
        )
        self.assertEqual(
            roster_mod.era_for("2021-06-01").key, "2021-furey-goodrich-vacant"
        )
        self.assertEqual(
            roster_mod.era_for("2021-07-13").key, "2021-furey-walser"
        )
        self.assertEqual(
            roster_mod.era_for("2022-08-09").key, "2022-chen-lewis"
        )
        self.assertEqual(
            roster_mod.era_for("2024-04-08").key, "2022-chen-lewis"
        )
        self.assertEqual(
            roster_mod.era_for("2024-04-09").key, "2024-pre-turnover"
        )
        # archive placeholder no longer covers 2019+
        self.assertNotEqual(
            roster_mod.era_for("2019-05-01").key, "archive-pre-2024"
        )

    def test_pre_furey_date_raises_when_outside_researched_eras(self):
        # 2005 still hits archive-pre-2024; a gap with no era should raise.
        # Use a date after archive end and before Furey if we ever punch a hole;
        # today archive ends 2014-12-31 and Furey starts 2015-01-01 with no gap.
        self.assertEqual(
            roster_mod.era_for("2010-06-01").key, "archive-pre-2024"
        )

    def test_effective_dating_still_resolves_the_transition(self):
        self.assertEqual(roster_mod.era_for("2026-08-24").key, "2026-d4-vacant")
        self.assertEqual(roster_mod.era_for("2026-08-25").key, "2026-barnett-appointment")
        self.assertEqual(roster_mod.era_for("2026-08-26").key, "2026-full")
        self.assertEqual(roster_mod.era_for("2026-09-01").key, "2026-full")


# --------------------------------------------------------------------------
# H7: agenda binding
# --------------------------------------------------------------------------

AGENDA_14821 = [
    {"meta_id": "451683", "time": 6761, "title": "8. CONSENT CALENDAR Matters listed"},
    {"meta_id": "451690", "time": 6910, "title": "11. AGENCY AGENDAS - None Scheduled"},
    {"meta_id": "451684", "time": 6925, "title": "8A. Community Development - Adopt"},
]

AGENDA_14798_BOUNDARY = [
    {
        "meta_id": "446102",
        "time": 5583,
        "title": "4. MOTION TO WAIVE FURTHER READING OF RESOLUTIONS AND ORDINANCES",
    },
    {
        "meta_id": "446105",
        "time": 5610,
        "title": "5. COUNCIL COMMITTEE MEETINGS AND ANNOUNCEMENTS",
    },
]

AGENDA_14821_SEQ6 = [
    {"meta_id": "451735", "time": 18000, "title": "9. prior item"},
    {"meta_id": "451763", "time": 18814, "title": "10A. City Manager — Accept and File Economic Development Update"},
    {"meta_id": "451771", "time": 18821, "title": "11. AGENCY AGENDAS - None Scheduled"},
]


class TestAgendaBinding(unittest.TestCase):
    """H7. The board was visible 6908..6930 with a cuepoint at 6910 titled
    "None Scheduled", so bind(6908) gave the right item and bind(6915) gave a
    heading for nothing. Nothing used the recorded `board_last_seen`."""

    def test_cuepoint_advancing_mid_board_is_flagged(self):
        detail = detect.bind_agenda_detail(AGENDA_14821, 6908, 6930)
        self.assertEqual(detail["item"]["meta_id"], "451683")
        self.assertTrue(
            any("still on screen" in p for p in detail["problems"]),
            detail["problems"],
        )

    def test_both_candidates_are_recorded(self):
        detail = detect.bind_agenda_detail(AGENDA_14821, 6908, 6930)
        self.assertEqual(detail["before"]["meta_id"], "451683")
        self.assertEqual(
            [a["meta_id"] for a in detail["during"]], ["451690", "451684"]
        )

    def test_non_item_cuepoint_alone_is_not_h7_ambiguity(self):
        """A non-item cuepoint during the board is not H7 substantive ambiguity."""
        agenda = [a for a in AGENDA_14821 if a["meta_id"] != "451684"]
        detail = detect.bind_agenda_detail(agenda, 6908, 6930)
        self.assertEqual(detail["item"]["meta_id"], "451683")
        self.assertFalse(
            any("still on screen" in p for p in detail["problems"]),
            detail["problems"],
        )
        self.assertEqual([a["meta_id"] for a in detail["during"]], ["451690"])
        # The non-item cuepoint at 6910 is still within the boundary band (+2 s)
        # and must be flagged even though H7 does not treat it as substantive.
        self.assertTrue(
            any("cannot resolve which side of the boundary" in p for p in detail["problems"]),
            detail["problems"],
        )

    def test_binding_onto_a_non_item_is_flagged(self):
        detail = detect.bind_agenda_detail(AGENDA_14821, 6915, 6930)
        self.assertEqual(detail["item"]["meta_id"], "451690")
        self.assertTrue(
            any("non-substantive" in p for p in detail["problems"]), detail["problems"]
        )

    def test_unambiguous_binding_has_no_problems(self):
        detail = detect.bind_agenda_detail(AGENDA_14821, 7000, 7005)
        self.assertEqual(detail["item"]["meta_id"], "451684")
        self.assertEqual(detail["problems"], [])

    def test_boundary_near_cuepoint_flags_wrong_binding(self):
        """14798 seq 0: onset 5610.1 binds to the wrong item with no H7 signal."""
        detail = detect.bind_agenda_detail(AGENDA_14798_BOUNDARY, 5610.1, 5612.0)
        self.assertEqual(detail["item"]["meta_id"], "446105")
        self.assertTrue(
            any("cannot resolve which side of the boundary" in p for p in detail["problems"]),
            detail["problems"],
        )
        self.assertEqual([a["meta_id"] for a in detail["boundary"]], ["446105"])

    def test_published_vote_outside_boundary_band_is_not_flagged(self):
        """14821 seq 6 at 18817.605 clears the nearest cuepoint by 3.40 s."""
        detail = detect.bind_agenda_detail(AGENDA_14821_SEQ6, 18817.605, 18820.0)
        self.assertEqual(detail["item"]["meta_id"], "451763")
        self.assertFalse(
            any("cannot resolve which side of the boundary" in p for p in detail["problems"]),
            detail["problems"],
        )

    def test_guarded_titles(self):
        for title in [
            "11. AGENCY AGENDAS - None Scheduled", "RECESS", "RECONVENE",
            "5. CLOSED SESSION",
        ]:
            with self.subTest(title=title):
                self.assertTrue(detect.is_non_item(title))
        self.assertFalse(detect.is_non_item("8A. Community Development - Adopt"))


# --------------------------------------------------------------------------
# M1: majority rule
# --------------------------------------------------------------------------

def tally_parsed(ayes: int, noes: int, abstentions: int, recused: int,
                 result: str = "passed") -> dict:
    values = ["YES"] * ayes + ["NO"] * noes + ["ABSTAIN"] * abstentions + ["RECUSE"] * recused
    members = [m.name for m in ERA.members][: len(values)]
    return {
        "vote_tally": {"ayes": ayes, "noes": noes,
                       "abstentions": abstentions, "recused": recused},
        "result": result,
        "individual_votes": dict(zip(members, values)),
        "vote_sources": {name: detect.VOTE_SOURCE_BOTH for name in members},
        "result_consensus": {"value": result, "count": 4, "reads": 4, "total": 4,
                             "fraction": 1.0, "tied": False},
        "vote_consensus": {},
    }


class TestMajorityRule(unittest.TestCase):
    """M1. `cast` summed all four tally columns, so abstentions and recusals
    counted as votes against."""

    def test_passing_votes_with_recusals_are_not_rejected(self):
        for ayes, noes, abstentions, recused in [(3, 2, 0, 2), (3, 0, 4, 0), (2, 1, 0, 4)]:
            with self.subTest(tally=(ayes, noes, abstentions, recused)):
                problems, _absent = detect.validate(
                    tally_parsed(ayes, noes, abstentions, recused), ERA, "absent", "both"
                )
                self.assertFalse(
                    any("majority" in p for p in problems),
                    f"{ayes}-{noes}-{abstentions}-{recused} genuinely passes: {problems}",
                )

    def test_a_genuine_minority_still_fails_the_check(self):
        problems, _absent = detect.validate(
            tally_parsed(2, 3, 0, 0), ERA, "absent", "both"
        )
        self.assertTrue(any("majority" in p for p in problems), problems)

    def test_a_tie_reported_as_passed_still_fails_the_check(self):
        problems, _absent = detect.validate(
            tally_parsed(3, 3, 0, 0), ERA, "absent", "both"
        )
        self.assertTrue(any("majority" in p for p in problems), problems)

    def test_failed_with_aye_majority_is_rejected(self):
        """Agenda-banner OCR once labeled a 6-0 consent vote as failed."""
        problems, _absent = detect.validate(
            tally_parsed(6, 0, 0, 0, result="failed"), ERA, "absent", "both"
        )
        self.assertTrue(any("result says failed" in p for p in problems), problems)


# --------------------------------------------------------------------------
# M2 / M6 / L2 / L3
# --------------------------------------------------------------------------

class TestResultBarCrop(unittest.TestCase):
    """M2. RESULT_BAR_WIDTH=0.60 handed Tesseract a 595px strip for text that
    occupies ~65px, and the percentile stretch was computed over that mostly
    blank strip."""

    def test_text_columns_are_isolated_from_a_wide_blank_band(self):
        band = np.full((40, 595), 60.0, dtype=np.float32)
        band[12:28, 100:165] = 110.0  # the "Motion Passed" glyphs
        cropped = detect._crop_to_text_columns(band)
        self.assertLess(cropped.shape[1], 100, "the blank majority must be dropped")
        self.assertGreater(cropped.shape[1], 60, "the glyphs must be kept whole")

    def test_a_flat_band_is_returned_unchanged(self):
        band = np.full((40, 595), 60.0, dtype=np.float32)
        self.assertEqual(detect._crop_to_text_columns(band).shape, band.shape)

    def test_extra_page_segmentation_modes_are_swept(self):
        source = Path(detect.__file__).read_text()
        self.assertIn("for psm in (7, 6, 11, 13)", source)

    def test_more_than_one_black_point_is_tried(self):
        """Cropping to the text columns changes the histogram the stretch is
        computed over, and how much of the crop is still bar rather than glyph
        varies with the length of the phrase."""
        self.assertGreaterEqual(len(detect.RESULT_BAR_BLACK_POINTS), 2)

    def test_alternate_geometries_are_swept(self):
        """The faint 14821 5-1-0-1 bar needs a higher/wider crop than the
        historical 0.17/0.60 span; both must remain in the sweep."""
        self.assertGreaterEqual(len(detect.RESULT_BAR_GEOMETRIES), 2)
        self.assertIn((detect.RESULT_BAR_SPAN, detect.RESULT_BAR_WIDTH),
                      detect.RESULT_BAR_GEOMETRIES)

    def test_faint_14821_result_bar_reads_passed(self):
        path = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/crops/14821/board_05_16233.jpg"
        )
        if not path.exists():
            self.skipTest("14821 board_05_16233 crop is not on this machine")
        with Image.open(path) as board:
            result, raw = detect.read_result_bar(board)
        self.assertEqual(result, "passed", raw)
        self.assertIsNotNone(raw)


class TestTesseractTimeout(unittest.TestCase):
    """M6. `subprocess.run` had no timeout, and a non-zero exit returned [],
    so a systematic failure looked like "no words found"."""

    def test_timeout_is_reported_not_silently_empty(self):
        image = Image.new("L", (900, 300), color=255)
        words, status = detect.run_tesseract(image, timeout=0.001)
        self.assertEqual(words, [])
        self.assertEqual(status, detect.TESS_TIMEOUT)

    def test_timeout_is_counted(self):
        before = detect.TESS_STATS["timeouts"]
        detect.run_tesseract(Image.new("L", (900, 300), color=255), timeout=0.001)
        self.assertEqual(detect.TESS_STATS["timeouts"], before + 1)

    def test_success_is_distinguishable_from_failure(self):
        image = Image.new("L", (400, 120), color=255)
        words, status = detect.run_tesseract(image)
        self.assertEqual(status, detect.TESS_OK)
        self.assertEqual(words, [], "a blank image has no words but did not fail")

    def test_default_timeout_is_set(self):
        self.assertGreater(detect.TESSERACT_TIMEOUT, 0)


class TestTallyLabelMatching(unittest.TestCase):
    """L2. `token.startswith(label[:4])` for "no" is `startswith("no")`, so
    "None", "Notice" and "Nominations" all matched the No column."""

    def test_words_beginning_no_are_not_the_no_column(self):
        for token in ["none", "notice", "nominations", "notes", "nothing"]:
            with self.subTest(token=token):
                self.assertIsNone(detect.tally_label_for(token))

    def test_no_and_noes_match_exactly(self):
        self.assertEqual(detect.tally_label_for("no"), "no")
        self.assertEqual(detect.tally_label_for("noes"), "no")

    def test_format_a_yea_label_matches_yes_column(self):
        self.assertEqual(detect.tally_label_for("yea"), "yes")

    def test_yes_does_not_match_yesterday(self):
        self.assertEqual(detect.tally_label_for("yes"), "yes")
        self.assertIsNone(detect.tally_label_for("yesterday"))

    def test_long_labels_keep_their_prefix_tolerance(self):
        for token in ["abstain", "abstaln", "abstentions"]:
            with self.subTest(token=token):
                self.assertEqual(detect.tally_label_for(token), "abstain")
        for token in ["recuse", "recusod", "recusals"]:
            with self.subTest(token=token):
                self.assertEqual(detect.tally_label_for(token), "recuse")

    def test_label_hits_no_longer_gets_a_free_hit(self):
        words = [word(t, 0, 0, 10, 10) for t in ["None", "Scheduled", "Notice"]]
        flat = detect.squash(detect.words_text(words))
        self.assertEqual(detect.count_label_hits(words, flat), 0)

    def test_a_real_board_scores_four(self):
        words = [word(t, 0, 0, 10, 10) for t in ["Yes", "No", "Abstain", "Recuse"]]
        flat = detect.squash(detect.words_text(words))
        self.assertEqual(detect.count_label_hits(words, flat), 4)


class TestFormatAGate(unittest.TestCase):
    def test_bright_low_saturation_slide_routes_to_format_a(self):
        image = Image.new("RGB", (480, 360), color=(230, 230, 230))
        stats = detect.frame_stats_image(image)
        self.assertTrue(detect.passes_bright_gate(stats))
        self.assertFalse(detect.passes_dark_gate(stats))
        self.assertEqual(detect.frame_format(stats), detect.FORMAT_A)
        self.assertTrue(detect.passes_gate(stats))

    def test_dark_board_keeps_format_b_route(self):
        image = Image.new("RGB", (1280, 720), color=(12, 12, 14))
        stats = detect.frame_stats_image(image)
        self.assertTrue(detect.passes_dark_gate(stats))
        self.assertFalse(detect.passes_bright_gate(stats))
        self.assertEqual(detect.frame_format(stats), detect.FORMAT_B)

    def test_bright_format_b_resolution_does_not_expand_gate_set(self):
        image = Image.new("RGB", (1280, 720), color=(230, 230, 230))
        stats = detect.frame_stats_image(image)
        self.assertFalse(detect.passes_bright_gate(stats))
        self.assertIsNone(detect.frame_format(stats))

    def test_incomplete_stats_fail_closed(self):
        dark_only = {
            "board_dark_fraction": 0.1,
            "board_saturation": 20.0,
            "inner_dark_fraction": 0.1,
            "inner_saturation": 20.0,
        }
        self.assertFalse(detect.passes_bright_gate(dark_only))
        self.assertIsNone(detect.frame_format(dark_only))
        self.assertFalse(detect.passes_gate(dark_only))
        self.assertFalse(detect.passes_gate_relaxed(dark_only, 0.05, 4.0))

    def test_native_parser_reads_14610_unanimous_board(self):
        path = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/"
            "frames.noindex/14610/w003/f_00524.jpg"
        )
        if not path.exists():
            self.skipTest("14610 Format A frame is not on this machine")
        era = roster_mod.era_for("2026-01-13")
        with Image.open(path) as image:
            parsed = detect.ocr_parse_format_a(image, era)
        self.assertEqual(parsed["parser"], "tesseract_format_a_marks")
        self.assertNotIn("format_problem", parsed)
        self.assertEqual(parsed["result"], "passed")
        self.assertEqual(
            parsed["vote_tally"],
            {"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0},
        )
        self.assertEqual(len(parsed["individual_votes"]), 7)
        self.assertTrue(all(v == "YES" for v in parsed["individual_votes"].values()))
        problems, absent = detect.validate(parsed, era)
        self.assertEqual(problems, [])
        self.assertEqual(absent, [])

    def test_native_parser_reads_a_format_a_no_vote(self):
        path = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/"
            "frames.noindex/14610/w005/f_00716.jpg"
        )
        if not path.exists():
            self.skipTest("14610 Format A Nay frame is not on this machine")
        era = roster_mod.era_for("2026-01-13")
        with Image.open(path) as image:
            parsed = detect.ocr_parse_format_a(image, era)
        self.assertEqual(parsed["vote_tally"]["noes"], 1)
        self.assertEqual(parsed["vote_tally"]["ayes"], 6)
        noes = [n for n, v in parsed["individual_votes"].items() if v == "NO"]
        self.assertEqual(len(noes), 1)
        problems, _ = detect.validate(parsed, era)
        self.assertEqual(problems, [])


class TestFormatAResultConsensus(unittest.TestCase):
    """Format A used to parse only the sharpest frame, so a cluster whose
    sharpest frame lost the result line rejected even when neighbours read
    Motion Passes clearly."""

    def test_majority_result_overrides_empty_sharpest_result(self):
        era = roster_mod.era_for("2026-01-13")
        sharp = {
            "frame": "sharp.jpg",
            "video_timestamp": 100.0,
            "_sharpness": 100.0,
            "format": detect.FORMAT_A,
            "_probe_a": {
                "parser": "tesseract_format_a_marks",
                "vote_tally": {"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0},
                "result": None,
                "result_raw": None,
                "individual_votes": {m.name: "YES" for m in era.members},
                "vote_details": {},
                "vote_sources": {},
                "unresolved": [],
                "icon_conflicts": [],
                "ocr_text": "",
            },
        }
        neighbour = {
            "frame": "neighbour.jpg",
            "video_timestamp": 101.0,
            "_sharpness": 50.0,
            "format": detect.FORMAT_A,
            "_probe_a": {
                "parser": "tesseract_format_a_marks",
                "vote_tally": {"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0},
                "result": "passed",
                "result_raw": "Motion Passes",
                "individual_votes": {m.name: "YES" for m in era.members},
                "vote_details": {},
                "vote_sources": {},
                "unresolved": [],
                "icon_conflicts": [],
                "ocr_text": "Motion Passes",
            },
        }
        neighbour2 = dict(neighbour)
        neighbour2["frame"] = "neighbour2.jpg"
        neighbour2["video_timestamp"] = 102.0
        # Avoid re-opening images: probes are pre-seeded.
        parsed = detect.consensus_parse_format_a(
            [sharp, neighbour, neighbour2], era
        )
        self.assertEqual(parsed["result"], "passed")
        self.assertEqual(parsed["result_raw"], "Motion Passes")
        self.assertEqual(parsed["parser"], "tesseract_format_a_marks_consensus")
        self.assertEqual(
            parsed["vote_tally"],
            {"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0},
        )
        self.assertEqual(parsed["frames_merged"], 3)

    def test_tied_results_do_not_invent_an_outcome(self):
        era = roster_mod.era_for("2026-01-13")
        votes = {m.name: "YES" for m in era.members}
        a = {
            "frame": "a.jpg",
            "video_timestamp": 1.0,
            "_sharpness": 90.0,
            "format": detect.FORMAT_A,
            "_probe_a": {
                "parser": "tesseract_format_a_marks",
                "vote_tally": {"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0},
                "result": "passed",
                "result_raw": "Motion Passes",
                "individual_votes": votes,
                "vote_details": {},
                "vote_sources": {},
                "unresolved": [],
                "icon_conflicts": [],
                "ocr_text": "",
            },
        }
        b = {
            "frame": "b.jpg",
            "video_timestamp": 2.0,
            "_sharpness": 80.0,
            "format": detect.FORMAT_A,
            "_probe_a": {
                "parser": "tesseract_format_a_marks",
                "vote_tally": {"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0},
                "result": "failed",
                "result_raw": "Motion Failed",
                "individual_votes": votes,
                "vote_details": {},
                "vote_sources": {},
                "unresolved": [],
                "icon_conflicts": [],
                "ocr_text": "",
            },
        }
        parsed = detect.consensus_parse_format_a([a, b], era)
        self.assertIsNone(parsed["result"])
        self.assertTrue(parsed["result_consensus"]["tied"])

    def test_all_missed_result_infers_from_mark_tally(self):
        era = roster_mod.era_for("2025-04-08")
        votes = {m.name: "YES" for m in list(era.members)[:5]}
        tally = {"ayes": 5, "noes": 0, "abstentions": 0, "recused": 0}
        group = []
        for i in range(3):
            group.append(
                {
                    "frame": f"f{i}.jpg",
                    "video_timestamp": float(i),
                    "_sharpness": 100 - i,
                    "format": detect.FORMAT_A,
                    "_probe_a": {
                        "parser": "tesseract_format_a_marks",
                        "vote_tally": tally,
                        "result": None,
                        "result_raw": None,
                        "individual_votes": votes,
                        "vote_details": {},
                        "vote_sources": {},
                        "unresolved": [],
                        "icon_conflicts": [],
                        "ocr_text": "",
                    },
                }
            )
        parsed = detect.consensus_parse_format_a(group, era)
        self.assertEqual(parsed["result"], "passed")
        self.assertTrue(parsed.get("result_inferred_from_tally"))

    def test_real_14610_cluster_keeps_marks_from_sharpest(self):
        path = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/"
            "frames.noindex/14610/w003/f_00524.jpg"
        )
        if not path.exists():
            self.skipTest("14610 Format A frame is not on this machine")
        era = roster_mod.era_for("2026-01-13")
        # Single-frame group still works through the consensus entry point.
        group = [{
            "frame": str(path),
            "video_timestamp": 524.0,
            "_sharpness": 10.0,
            "format": detect.FORMAT_A,
        }]
        parsed = detect.consensus_parse_format_a(group, era)
        self.assertEqual(parsed["result"], "passed")
        self.assertEqual(parsed["vote_tally"]["ayes"], 7)

    def test_format_a_bottom_strip_recovers_motion_passes(self):
        path = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/crops/14536/board_01_6761.jpg"
        )
        if not path.exists():
            self.skipTest("14536 Format A crop is not on this machine")
        with Image.open(path) as image:
            result, raw = detect.read_format_a_result(image)
        self.assertEqual(result, "passed", raw)


class TestFormatC(unittest.TestCase):
    """Mid-2010s white Voting Results slide (clip 12849 / 2016-01-12)."""

    BOARD = Path(
        "/Volumes/Black Passport/torrance-vote-viewer/crops/12849/board_06_17268.jpg"
    )

    def test_furey_era_covers_january_2016(self):
        era = roster_mod.era_for("2016-01-12")
        self.assertEqual(era.key, "2015-2016-furey-barnett")
        surnames = {m.name.rsplit(" ", 1)[-1] for m in era.members}
        self.assertEqual(
            surnames,
            {"Furey", "Ashcraft", "Barnett", "Goodrich", "Griffiths", "Rizzo", "Weideman"},
        )

    def test_herring_era_covers_2017(self):
        era = roster_mod.era_for("2017-01-12")
        self.assertEqual(era.key, "2016-furey-herring")
        surnames = {m.name.rsplit(" ", 1)[-1] for m in era.members}
        self.assertEqual(
            surnames,
            {"Furey", "Ashcraft", "Goodrich", "Griffiths", "Herring", "Rizzo", "Weideman"},
        )
        self.assertNotIn("Barnett", surnames)
        # Narrower than archive-pre-2024
        self.assertEqual(roster_mod.era_for("2016-07-01").key, "2016-furey-herring")
        self.assertEqual(roster_mod.era_for("2018-04-24").key, "2016-furey-herring")

    def test_native_parser_reads_13382_with_herring_roster(self):
        path = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/crops/13382/board_00_5703.jpg"
        )
        if not path.exists():
            self.skipTest("13382 Format C crop is not on this machine")
        era = roster_mod.era_for("2018-01-09")
        self.assertEqual(era.key, "2016-furey-herring")
        with Image.open(path) as image:
            self.assertEqual(detect.classify_bright_format(image), detect.FORMAT_C)
            parsed = detect.ocr_parse_format_c(image, era)
        self.assertEqual(parsed["format"], detect.FORMAT_C)
        self.assertIsNotNone(parsed.get("vote_tally"))
        self.assertGreaterEqual(len(parsed.get("individual_votes") or {}), 5)
        self.assertIn("Herring", " ".join(parsed["individual_votes"]))
        # Wrong archive roster must fail to read marks on this board
        archive = roster_mod.ARCHIVE_PRE_2024
        with Image.open(path) as image:
            bad = detect.ocr_parse_format_c(image, archive)
        self.assertFalse(bad.get("individual_votes"))

    def test_classifies_12849_board_as_format_c(self):
        if not self.BOARD.exists():
            self.skipTest("12849 Format C crop is not on this machine")
        with Image.open(self.BOARD) as image:
            self.assertEqual(detect.classify_bright_format(image), detect.FORMAT_C)
            self.assertEqual(len(detect.find_format_c_marks(image)), 7)

    def test_native_parser_reads_7_0_unanimous(self):
        if not self.BOARD.exists():
            self.skipTest("12849 Format C crop is not on this machine")
        era = roster_mod.era_for("2016-01-12")
        with Image.open(self.BOARD) as image:
            parsed = detect.ocr_parse_format_c(image, era)
        self.assertEqual(parsed["format"], detect.FORMAT_C)
        self.assertEqual(parsed["parser"], "tesseract_format_c_marks")
        self.assertEqual(parsed["result"], "passed")
        self.assertEqual(
            parsed["vote_tally"],
            {"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0},
        )
        self.assertEqual(len(parsed["individual_votes"]), 7)
        self.assertTrue(all(v == "YES" for v in parsed["individual_votes"].values()))
        self.assertIn("Moratorium", parsed.get("agenda_banner") or "")
        problems, absent = detect.validate(parsed, era)
        self.assertEqual(problems, [])
        self.assertEqual(absent, [])

    def test_format_c_midband_reads_motion_passes(self):
        """Format C Motion Passes sits ~0.60–0.75; lower-only strips miss it."""
        path = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/crops/13176/board_00_12086.jpg"
        )
        if not path.exists():
            self.skipTest("13176 Format C crop is not on this machine")
        with Image.open(path) as image:
            result, raw = detect.read_format_a_result(image)
        self.assertEqual(result, "passed")
        self.assertIn("Motion", raw or "")

    def test_format_c_infers_result_from_tally_when_banner_missing(self):
        path = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/crops/13386/board_00_6574.jpg"
        )
        if not path.exists():
            self.skipTest("13386 Format C crop is not on this machine")
        era = roster_mod.era_for("2018-01-23")
        with Image.open(path) as image:
            parsed = detect.ocr_parse_format_c(image, era)
        self.assertEqual(parsed["result"], "passed")
        self.assertTrue(parsed.get("result_inferred_from_tally"))
        self.assertGreaterEqual(len(parsed.get("individual_votes") or {}), 5)
        problems, _absent = detect.validate(parsed, era)
        self.assertEqual(problems, [])

    def test_result_from_format_c_tally(self):
        self.assertEqual(
            detect.result_from_format_c_tally({"ayes": 7, "noes": 0, "abstentions": 0, "recused": 0}),
            "passed",
        )
        self.assertEqual(
            detect.result_from_format_c_tally({"ayes": 2, "noes": 5, "abstentions": 0, "recused": 0}),
            "failed",
        )
        self.assertEqual(
            detect.result_from_format_c_tally({"ayes": 3, "noes": 3, "abstentions": 1, "recused": 0}),
            "tie",
        )
        self.assertIsNone(detect.result_from_format_c_tally(None))

    def test_format_a_board_does_not_route_to_c(self):
        path = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/crops/14273/board_00_6216.jpg"
        )
        if not path.exists():
            self.skipTest("14273 Format A crop is not on this machine")
        with Image.open(path) as image:
            self.assertEqual(detect.classify_bright_format(image), detect.FORMAT_A)

    def test_transcript_confirms_result_and_urgency_motion(self):
        if not self.BOARD.exists():
            self.skipTest("12849 Format C crop is not on this machine")
        catalog = Path(
            "/Volumes/Black Passport/torrance-vote-viewer/metadata/clips_2016.json"
        )
        if not catalog.exists():
            self.skipTest("2016 catalog is not on this machine")
        import json

        data = json.loads(catalog.read_text())
        clip = next(c for c in data["clips"] if str(c["clip_id"]) == "12849")
        era = roster_mod.era_for(clip["date"])
        with Image.open(self.BOARD) as image:
            parsed = detect.ocr_parse_format_c(image, era)
        binding = detect.bind_agenda_detail(clip["agenda"], 17268.0, 17300.0)
        check = detect.transcript_double_check(
            clip, 17268.0, parsed, binding["item"]
        )
        self.assertEqual(check["result_match"], "confirmed")
        self.assertEqual(check["agenda_match"], "confirmed")
        self.assertEqual(check["status"], "confirmed")
        self.assertEqual(check["problems"], [])


class TestCropClearing(unittest.TestCase):
    """L3. The timestamp is part of the crop filename, so re-runs leave
    board_00_6907.jpg next to board_00_6909.jpg from a previous pass."""

    def test_clearing_is_opt_in_and_defaults_off(self):
        source = Path(detect.__file__).read_text()
        self.assertIn('"--clear-crops"', source)
        self.assertIn('"--crops-dir"', source)
        # argparse store_true defaults to False; assert there is no default=True.
        self.assertNotIn("'--clear-crops', action='store_true', default=True", source)


# --------------------------------------------------------------------------
# L6: surname matching
# --------------------------------------------------------------------------

class TestMemberMatching(unittest.TestCase):
    """L6. The substring fallback returned the first roster surname in
    declaration order, so 'xx lewis yy lieu zz' resolved to Lewis whichever
    name came first in the text."""

    def test_ambiguous_substring_resolves_to_nothing(self):
        self.assertIsNone(roster_mod.match_member("xx lewis yy lieu zz", ERA))
        self.assertIsNone(roster_mod.match_member("xx lieu yy lewis zz", ERA))

    def test_declaration_order_no_longer_decides(self):
        first = roster_mod.match_member("xx lewis yy lieu zz", ERA)
        second = roster_mod.match_member("xx lieu yy lewis zz", ERA)
        self.assertEqual(first, second)

    def test_a_single_surname_inside_a_string_still_resolves(self):
        member = roster_mod.match_member("zz lewis yy", ERA)
        self.assertIsNotNone(member)
        self.assertEqual(member.name, "Bridgett Lewis")

    def test_real_ocr_names_still_resolve(self):
        for raw, expected in [
            ("Councilmember Kartsonis", "David Kartsonis"),
            ("Counciimember Sheikh", "Asam Sheikh"),
            ("Mayor Kalani", "Sharon Kalani"),
            ("Councilmember Barnett", "Linda Barnett"),
            ("Councilmember Lieu", "Betty Lieu"),
            ("Councilmember Gerson", "Jeremy Gerson"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(roster_mod.match_member(raw, ERA).name, expected)

    def test_short_tokens_do_not_fuzzy_match_a_surname(self):
        for token in ["lie", "ger", "lew", "kal"]:
            with self.subTest(token=token):
                self.assertIsNone(roster_mod.match_member(token, ERA))


class TestPublishSkipGuards(unittest.TestCase):
    """Non-votable binds and invented unreadable members must not publish."""

    def setUp(self):
        import publish_votes as publish_mod

        self.publish = publish_mod

    def test_close_public_hearing_is_non_votable(self):
        self.assertTrue(
            self.publish.is_non_votable_title("CLOSE PUBLIC HEARING")
        )
        self.assertTrue(self.publish.is_non_votable_title("RECESS"))
        self.assertFalse(
            self.publish.is_non_votable_title("8. CONSENT CALENDAR")
        )

    def test_skip_non_votable_bind(self):
        reason = self.publish.should_skip_publish(
            {
                "agenda_item": "CLOSE PUBLIC HEARING",
                "individual_votes": {"Sharon Kalani": "YES"},
                "problems": [],
                "parser": "tesseract_format_a_marks_consensus",
            }
        )
        self.assertEqual(reason, "non_votable_agenda_bind")

    def test_skip_empty_individuals(self):
        reason = self.publish.should_skip_publish(
            {
                "agenda_item": "9A. Something",
                "individual_votes": {},
                "problems": ["no individual votes read"],
                "parser": "tesseract_format_a_marks_consensus",
                "verification": "needs_review",
            }
        )
        self.assertEqual(reason, "empty_individual_votes")

    def test_skip_unreadable_invented_member(self):
        reason = self.publish.should_skip_publish(
            {
                "agenda_item": "9A. Something",
                "individual_votes": {"Milton Herring": "YES", "Tim Goodrich": "YES"},
                "problems": ["vote value unreadable for: Milton Herring"],
                "parser": "tesseract_format_c",
            }
        )
        self.assertTrue(reason.startswith("unreadable_member_invented"))
        self.assertIn("Milton Herring", reason)

    def test_oral_empty_individuals_not_skipped(self):
        reason = self.publish.should_skip_publish(
            {
                "agenda_item": "8. Consent",
                "individual_votes": {},
                "problems": ["oral attribution from clerk speech; not board OCR"],
                "parser": "oral_asr_unanimous",
            }
        )
        self.assertIsNone(reason)


class TestOralAsrAttribution(unittest.TestCase):
    """Oral convert must attribute clerk formulas and map ASR names."""

    def setUp(self):
        import oral_votes_from_hunt as oral_mod

        self.oral = oral_mod
        self.era = roster_mod.era_for("2019-06-01")

    def test_unanimous_carried_is_passed(self):
        self.assertEqual(
            self.oral.classify_outcome("Your Honor, that motion carried unanimously."),
            "passed",
        )

    def test_named_no_is_passed_with_exceptions(self):
        text = "Your Honor, that motion carries with Council Member Mattucci voting no."
        self.assertEqual(self.oral.classify_outcome(text), "passed")
        exc, unresolved = self.oral.parse_named_exceptions(text, self.era)
        self.assertEqual(exc, {"Aurelio Mattucci": "NO"})
        self.assertEqual(unresolved, [])

    def test_named_abstain_parsed(self):
        text = "Your Honor, that motion carries with Council Member Goodrich abstaining."
        exc, unresolved = self.oral.parse_named_exceptions(text, self.era)
        self.assertEqual(exc, {"Tim Goodrich": "ABSTAIN"})
        self.assertEqual(unresolved, [])

    def test_two_named_noes(self):
        text = (
            "Your Honor, that motion carries with Council Members Griffiths "
            "and Mattucci voting no."
        )
        exc, unresolved = self.oral.parse_named_exceptions(text, self.era)
        self.assertEqual(exc.get("Mike Griffiths"), "NO")
        self.assertEqual(exc.get("Aurelio Mattucci"), "NO")
        self.assertEqual(unresolved, [])

    def test_numeric_tally_refused(self):
        self.assertIsNone(
            self.oral.classify_outcome("that motion carries 5 to 2")
        )

    def test_matucci_one_t_maps_to_mattucci(self):
        self.assertEqual(
            self.oral.match_absent_names(
                "Your Honor, that motion carries with Council Member Matucci absent.",
                self.era,
            ),
            ["Aurelio Mattucci"],
        )

    def test_hearing_maps_to_herring(self):
        self.assertEqual(
            self.oral.match_absent_names(
                "Your Honor, that motion carries with Councilmember hearing absent.",
                self.era,
            ),
            ["Milton Herring"],
        )

    def test_possessive_griffiths_absent(self):
        era = roster_mod.era_for("2019-07-23")
        self.assertEqual(
            self.oral.match_absent_names(
                "that motion carries with council member griffith's absent",
                era,
            ),
            ["Mike Griffiths"],
        )

    def test_mayor_currie_maps_to_furey(self):
        era = roster_mod.era_for("2019-09-24")
        self.assertEqual(
            self.oral.match_absent_names(
                "Your Honor, that motion carries with Mayor Currie absent.",
                era,
            ),
            ["Patrick Furey"],
        )

    def test_build_candidate_named_no(self):
        event = {
            "start": 1000.0,
            "end": 1010.0,
            "text": (
                "Start voting, please. | Your Honor, that motion carries "
                "with Council Members Griffiths and Mattucci voting no."
            ),
            "result": "passed",
            "has_start": True,
        }
        cand = self.oral.build_candidate(
            clip_id="13461",
            seq=0,
            event=event,
            era=self.era,
            agenda=[],
        )
        self.assertIsNotNone(cand)
        votes = cand["parsed"]["individual_votes"]
        self.assertEqual(votes["Mike Griffiths"], "NO")
        self.assertEqual(votes["Aurelio Mattucci"], "NO")
        self.assertEqual(votes["George Chen"], "YES")
        self.assertEqual(cand["parsed"]["vote_tally"]["noes"], 2)
        self.assertEqual(cand["parsed"]["parser"], "oral_asr_clerk")

    def test_attendance_only_empty_reason(self):
        hunt = {
            "vote_hits": 1,
            "hits": [
                {
                    "start": 30.0,
                    "end": 32.0,
                    "text": "City Clerk, may I have a roll call, please?",
                }
            ],
        }
        reason = self.oral.empty_reason_for(hunt, [], hunt["hits"])
        self.assertEqual(reason, "attendance_roll_call_only")

    def test_cluster_attributes_dissent_in_followup_hit(self):
        hits = [
            {"start": 100.0, "end": 105.0, "text": "Start voting, please."},
            {
                "start": 110.0,
                "end": 120.0,
                "text": "Your Honor, that motion carries with council members",
            },
            {
                "start": 121.0,
                "end": 130.0,
                "text": "Griffiths and Mattucci voting no.",
            },
        ]
        events = self.oral.cluster_events(hits, era=self.era)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["result"], "passed")
        exc, _ = self.oral.parse_named_exceptions(events[0]["text"], self.era)
        self.assertEqual(exc.get("Mike Griffiths"), "NO")
        self.assertEqual(exc.get("Aurelio Mattucci"), "NO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
