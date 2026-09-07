"""Effective-dated Torrance City Council rosters.

The council turned over on Jul 14 2026, so a 2026 vote must never be validated
against Chen / Kaji / Mattucci. District 4 sat vacant from Jul 14 until Linda
Barnett was appointed and sworn in part-way through the Aug 25 2026 meeting,
which is why that date accepts either a 6- or 7-member board.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Member:
    name: str
    district: str
    role: str = "Councilmember"


@dataclass(frozen=True)
class Era:
    key: str
    start: str
    end: str | None
    members: tuple[Member, ...]
    expected_sizes: tuple[int, ...] = ()
    verified: bool = True
    note: str = ""
    aliases: dict[str, str] = field(default_factory=dict)

    @property
    def sizes(self) -> tuple[int, ...]:
        return self.expected_sizes or (len(self.members),)

    def by_surname(self) -> dict[str, Member]:
        return {m.name.rsplit(" ", 1)[-1].lower(): m for m in self.members}


# Chen mayor / Lewis / Gerson council from Gerson's Apr 9 2024 swearing-in
# through the Jul 2026 mayoral turnover. Verified after Format A crop spot-check.
HISTORICAL = Era(
    key="2024-pre-turnover",
    start="2024-04-09",
    end="2026-07-13",
    verified=True,
    note=(
        "Mayor Chen / Kaji / Lewis / Sheikh / Kalani / Mattucci / Gerson; "
        "Gerson seated Apr 9 2024 succeeding Griffiths. Verified 2026-09-07 "
        "against Format A crops (e.g. 14286, 14350, 14427, 14536, 14688)."
    ),
    members=(
        Member("George Chen", "Mayor", "Mayor"),
        Member("Jon Kaji", "District 1"),
        Member("Bridgett Lewis", "District 2"),
        Member("Asam Sheikh", "District 3"),
        Member("Sharon Kalani", "District 4"),
        Member("Aurelio Mattucci", "District 5"),
        Member("Jeremy Gerson", "District 6"),
    ),
    aliases={
        "bridget lewis": "Bridgett Lewis",
        "mike gerson": "Jeremy Gerson",
    },
)

# Pre-2015 archive sampling only. Member names are NOT historically researched —
# detect/OCR can still surface board crops and tallies, but individual attributions
# must not be published until a real era is filled in. Accept 5–7 seat boards.
ARCHIVE_PRE_2024 = Era(
    key="archive-pre-2024",
    start="2005-01-01",
    end="2014-12-31",
    verified=False,
    expected_sizes=(5, 6, 7),
    note=(
        "Granicus archive before researched Furey eras; placeholder roster for "
        "format sampling only. Do not publish member-level votes from this era."
    ),
    members=HISTORICAL.members,
)

# Mayor Furey council with Gene Barnett still seated (Format C boards, e.g. clip
# 12849 on 2016-01-12). Narrower than ARCHIVE_PRE_2024 so era_for prefers this.
# Milton Herring replaced Barnett mid-2016 — end before that transition.
FUREY_BARNETT_2015 = Era(
    key="2015-2016-furey-barnett",
    start="2015-01-01",
    end="2016-06-30",
    verified=True,
    note=(
        "Mayor Furey / Ashcraft / Barnett / Goodrich / Griffiths / Rizzo / Weideman; "
        "researched from 2015 city site archive and Jan 2016 board OCR. "
        "Verified 2026-09-06 against Format C crops (e.g. clip 12849)."
    ),
    members=(
        Member("Patrick Furey", "Mayor", "Mayor"),
        Member("Heidi Ashcraft", "Council"),
        Member("Gene Barnett", "Council"),
        Member("Tim Goodrich", "Council"),
        Member("Mike Griffiths", "Council"),
        Member("Geoff Rizzo", "Council"),
        Member("Kurt Weideman", "Council"),
    ),
    aliases={
        "furey": "Patrick Furey",
        "mayor furey": "Patrick Furey",
        "ashcraft": "Heidi Ashcraft",
        "barnett": "Gene Barnett",
        "goodrich": "Tim Goodrich",
        "griffiths": "Mike Griffiths",
        "rizzo": "Geoff Rizzo",
        "weideman": "Kurt Weideman",
    },
)

# Milton Herring elected June 2016 (Barnett termed out). Same Format C slide
# family; OCR on 2017–early 2018 crops confirms this surname set through the
# Jul 10 2018 install (Ashcraft out / Weideman lost; Chen + Mattucci in).
FUREY_HERRING_2016 = Era(
    key="2016-furey-herring",
    start="2016-07-01",
    end="2018-07-09",
    verified=True,
    note=(
        "Mayor Furey / Ashcraft / Goodrich / Griffiths / Herring / Rizzo / Weideman; "
        "OCR-confirmed on 2017–2018 Format C boards. Ends day before Jul 10 2018 install."
    ),
    members=(
        Member("Patrick Furey", "Mayor", "Mayor"),
        Member("Heidi Ashcraft", "Council"),
        Member("Tim Goodrich", "Council"),
        Member("Mike Griffiths", "Council"),
        Member("Milton Herring", "Council"),
        Member("Geoff Rizzo", "Council"),
        Member("Kurt Weideman", "Council"),
    ),
    aliases={
        "furey": "Patrick Furey",
        "mayor furey": "Patrick Furey",
        "ashcraft": "Heidi Ashcraft",
        "goodrich": "Tim Goodrich",
        "griffiths": "Mike Griffiths",
        "herring": "Milton Herring",
        "rizzo": "Geoff Rizzo",
        "weideman": "Kurt Weideman",
    },
)

_FUREY_ALIASES_CHEN = {
    "furey": "Patrick Furey",
    "mayor furey": "Patrick Furey",
    "goodrich": "Tim Goodrich",
    "chen": "George Chen",
    "george chen": "George Chen",
    "mattucci": "Aurelio Mattucci",
    "herring": "Milton Herring",
    "griffiths": "Mike Griffiths",
    "rizzo": "Geoff Rizzo",
}

# Jul 10 2018 install: Chen + Mattucci in; Ashcraft / Weideman out.
FUREY_CHEN_MATTUCCI_2018 = Era(
    key="2018-furey-chen-mattucci",
    start="2018-07-10",
    end="2019-06-30",
    verified=True,
    note=(
        "Mayor Furey / Goodrich / Chen / Mattucci / Herring / Griffiths / Rizzo; "
        "post–Jun 5 2018 election install (RES 2018-68 Jul 10)."
    ),
    members=(
        Member("Patrick Furey", "Mayor", "Mayor"),
        Member("Tim Goodrich", "Council"),
        Member("George Chen", "Council"),
        Member("Aurelio Mattucci", "Council"),
        Member("Milton Herring", "Council"),
        Member("Mike Griffiths", "Council"),
        Member("Geoff Rizzo", "Council"),
    ),
    aliases=_FUREY_ALIASES_CHEN,
)

# Herring resigned effective Jun 30 2019; seat vacant until Mar 2020 district election.
FUREY_HERRING_VACANT_2019 = Era(
    key="2019-furey-herring-vacant",
    start="2019-07-01",
    end="2020-04-13",
    verified=True,
    expected_sizes=(6,),
    note=(
        "Herring resigned effective Jun 30 2019; six voting members until "
        "Apr 2020 district-election install."
    ),
    members=(
        Member("Patrick Furey", "Mayor", "Mayor"),
        Member("Tim Goodrich", "Council"),
        Member("George Chen", "Council"),
        Member("Aurelio Mattucci", "Council"),
        Member("Mike Griffiths", "Council"),
        Member("Geoff Rizzo", "Council"),
    ),
    aliases={
        k: v for k, v in _FUREY_ALIASES_CHEN.items() if k not in ("herring",)
    },
)

# First by-district results certified Apr 14 2020; Chen→D2 leaves at-large vacant
# until Ashcraft appointment May 12.
FUREY_DISTRICT_PRE_ASHCRAFT_2020 = Era(
    key="2020-furey-district-pre-ashcraft",
    start="2020-04-14",
    end="2020-05-11",
    verified=True,
    expected_sizes=(6,),
    note=(
        "Post–Mar 3 2020 district install: Chen D2, Kalani D4, Griffiths D6; "
        "Rizzo out; Chen's at-large seat vacant until Ashcraft May 12."
    ),
    members=(
        Member("Patrick Furey", "Mayor", "Mayor"),
        Member("George Chen", "District 2"),
        Member("Sharon Kalani", "District 4"),
        Member("Mike Griffiths", "District 6"),
        Member("Tim Goodrich", "Council"),
        Member("Aurelio Mattucci", "Council"),
    ),
    aliases={
        "furey": "Patrick Furey",
        "chen": "George Chen",
        "kalani": "Sharon Kalani",
        "griffiths": "Mike Griffiths",
        "goodrich": "Tim Goodrich",
        "mattucci": "Aurelio Mattucci",
    },
)

FUREY_DISTRICT_2020 = Era(
    key="2020-furey-district",
    start="2020-05-12",
    end="2021-05-31",
    verified=True,
    note=(
        "Ashcraft appointed May 12 2020 to Chen's unexpired at-large seat; "
        "full seven through Goodrich resignation."
    ),
    members=(
        Member("Patrick Furey", "Mayor", "Mayor"),
        Member("George Chen", "District 2"),
        Member("Sharon Kalani", "District 4"),
        Member("Mike Griffiths", "District 6"),
        Member("Tim Goodrich", "Council"),
        Member("Aurelio Mattucci", "Council"),
        Member("Heidi Ashcraft", "Council"),
    ),
    aliases={
        "furey": "Patrick Furey",
        "chen": "George Chen",
        "kalani": "Sharon Kalani",
        "griffiths": "Mike Griffiths",
        "goodrich": "Tim Goodrich",
        "mattucci": "Aurelio Mattucci",
        "ashcraft": "Heidi Ashcraft",
    },
)

FUREY_GOODRICH_VACANT_2021 = Era(
    key="2021-furey-goodrich-vacant",
    start="2021-06-01",
    end="2021-07-12",
    verified=True,
    expected_sizes=(6,),
    note="Goodrich resigned effective Jun 1 2021; vacant until Walser Jul 13.",
    members=(
        Member("Patrick Furey", "Mayor", "Mayor"),
        Member("George Chen", "District 2"),
        Member("Sharon Kalani", "District 4"),
        Member("Mike Griffiths", "District 6"),
        Member("Aurelio Mattucci", "Council"),
        Member("Heidi Ashcraft", "Council"),
    ),
    aliases={
        "furey": "Patrick Furey",
        "chen": "George Chen",
        "kalani": "Sharon Kalani",
        "griffiths": "Mike Griffiths",
        "mattucci": "Aurelio Mattucci",
        "ashcraft": "Heidi Ashcraft",
    },
)

FUREY_WALSER_2021 = Era(
    key="2021-furey-walser",
    start="2021-07-13",
    end="2022-07-11",
    verified=True,
    note="Jack Walser appointed Jul 13 2021 to Goodrich's unexpired at-large term.",
    members=(
        Member("Patrick Furey", "Mayor", "Mayor"),
        Member("George Chen", "District 2"),
        Member("Sharon Kalani", "District 4"),
        Member("Mike Griffiths", "District 6"),
        Member("Aurelio Mattucci", "Council"),
        Member("Heidi Ashcraft", "Council"),
        Member("Jack Walser", "Council"),
    ),
    aliases={
        "furey": "Patrick Furey",
        "chen": "George Chen",
        "kalani": "Sharon Kalani",
        "griffiths": "Mike Griffiths",
        "mattucci": "Aurelio Mattucci",
        "ashcraft": "Heidi Ashcraft",
        "walser": "Jack Walser",
        "jack walser": "Jack Walser",
        "john jack walser": "Jack Walser",
        "john walser": "Jack Walser",
    },
)

# Jun 7 2022: Chen elected mayor; Kaji D1, Sheikh D3, Mattucci D5. D2 vacant
# until Lewis appointment (August 2022).
CHEN_MAYOR_2022 = Era(
    key="2022-chen-mayor",
    start="2022-07-12",
    end="2022-08-08",
    verified=True,
    expected_sizes=(6,),
    note=(
        "Mayor Chen after Jun 7 2022 install; D2 vacant until Bridgett Lewis "
        "appointment (Aug 2022)."
    ),
    members=(
        Member("George Chen", "Mayor", "Mayor"),
        Member("Jon Kaji", "District 1"),
        Member("Asam Sheikh", "District 3"),
        Member("Sharon Kalani", "District 4"),
        Member("Aurelio Mattucci", "District 5"),
        Member("Mike Griffiths", "District 6"),
    ),
    aliases={
        "chen": "George Chen",
        "mayor chen": "George Chen",
        "kaji": "Jon Kaji",
        "sheikh": "Asam Sheikh",
        "kalani": "Sharon Kalani",
        "mattucci": "Aurelio Mattucci",
        "griffiths": "Mike Griffiths",
    },
)

CHEN_LEWIS_2022 = Era(
    key="2022-chen-lewis",
    start="2022-08-09",
    end="2024-04-08",
    verified=True,
    note=(
        "Lewis appointed Aug 2022 to Chen's former D2 seat; Griffiths still D6 "
        "until Gerson swearing-in Apr 9 2024."
    ),
    members=(
        Member("George Chen", "Mayor", "Mayor"),
        Member("Jon Kaji", "District 1"),
        Member("Bridgett Lewis", "District 2"),
        Member("Asam Sheikh", "District 3"),
        Member("Sharon Kalani", "District 4"),
        Member("Aurelio Mattucci", "District 5"),
        Member("Mike Griffiths", "District 6"),
    ),
    aliases={
        "chen": "George Chen",
        "mayor chen": "George Chen",
        "kaji": "Jon Kaji",
        "lewis": "Bridgett Lewis",
        "bridget lewis": "Bridgett Lewis",
        "bridgett lewis": "Bridgett Lewis",
        "sheikh": "Asam Sheikh",
        "kalani": "Sharon Kalani",
        "mattucci": "Aurelio Mattucci",
        "griffiths": "Mike Griffiths",
    },
)

D4_VACANT = Era(
    key="2026-d4-vacant",
    start="2026-07-14",
    end="2026-08-24",
    note="District 4 vacant; 6 voting members",
    members=(
        Member("Sharon Kalani", "Mayor", "Mayor"),
        Member("David Kartsonis", "District 1"),
        Member("Bridgett Lewis", "District 2"),
        Member("Asam Sheikh", "District 3"),
        Member("Betty Lieu", "District 5"),
        Member("Jeremy Gerson", "District 6"),
    ),
)

FULL_2026 = Era(
    key="2026-full",
    start="2026-08-26",
    end=None,
    note="Barnett seated in District 4; 7 voting members",
    members=(
        Member("Sharon Kalani", "Mayor", "Mayor"),
        Member("David Kartsonis", "District 1"),
        Member("Bridgett Lewis", "District 2"),
        Member("Asam Sheikh", "District 3"),
        Member("Linda Barnett", "District 4"),
        Member("Betty Lieu", "District 5"),
        Member("Jeremy Gerson", "District 6"),
    ),
)

# Aug 25 2026 seats Barnett mid-meeting, so both board sizes are legitimate.
TRANSITION_2026_08_25 = Era(
    key="2026-barnett-appointment",
    start="2026-08-25",
    end="2026-08-25",
    expected_sizes=(6, 7),
    note="Barnett appointed then sworn in mid-meeting; 6 or 7 voting members",
    members=FULL_2026.members,
)

ERAS: tuple[Era, ...] = (
    ARCHIVE_PRE_2024,
    FUREY_BARNETT_2015,
    FUREY_HERRING_2016,
    FUREY_CHEN_MATTUCCI_2018,
    FUREY_HERRING_VACANT_2019,
    FUREY_DISTRICT_PRE_ASHCRAFT_2020,
    FUREY_DISTRICT_2020,
    FUREY_GOODRICH_VACANT_2021,
    FUREY_WALSER_2021,
    CHEN_MAYOR_2022,
    CHEN_LEWIS_2022,
    HISTORICAL,
    D4_VACANT,
    TRANSITION_2026_08_25,
    FULL_2026,
)

VOTE_VALUES = ("YES", "NO", "ABSTAIN", "RECUSE", "ABSENT")
# Single letters are deliberately absent. The value printed under a name is a
# handful of grey pixels, so Tesseract routinely emits one- and two-character
# fragments ("es", "ye", "n") off a row it could not really read. Accepting
# those as a confident vote is how a stray glyph beat the real word.
VOTE_SYNONYMS = {
    "yes": "YES",
    "yea": "YES",
    "aye": "YES",
    "ayes": "YES",
    "no": "NO",
    "nay": "NO",
    "noes": "NO",
    "abstain": "ABSTAIN",
    "abstains": "ABSTAIN",
    "abstained": "ABSTAIN",
    "abstention": "ABSTAIN",
    "recuse": "RECUSE",
    "recused": "RECUSE",
    "recusal": "RECUSE",
    "absent": "ABSENT",
    "excused": "ABSENT",
}

# Below this length a token must match the vocabulary exactly. Every vote word
# short enough to fall here ("yes", "no", "nay", "aye", "noes") is also short
# enough that a single wrong character scores ~0.67 against the right answer
# and ~0.86 against the wrong one -- "nes" is closer to "noes" than "yos" is to
# "yes" -- so fuzzy matching in that range reliably inverts the vote.
VOTE_FUZZY_MIN_LEN = 5
VOTE_FUZZY_CUTOFF = 0.82
# A token has to look clearly more like one value than any other.
VOTE_FUZZY_MARGIN = 0.06

# Closed-vocabulary decoder, applied only after an exact and then a fuzzy match
# have both failed. The value column holds one of five words and nothing else,
# so an initial letter can carry the whole decision -- but only for an initial
# that no *other* outcome word can garble into.
#
# Y is the only such initial. Nothing but "Yes"/"Yea" begins with it, and none
# of "no", "abstain", "recuse" or "absent" can lose its own initial and gain a
# Y. The measured misses on clip 14821 are exactly this shape: "Yee" on four
# rows, plus "Yeu", "Yor" and "ves", every one of them a YES.
#
# The other initials are deliberately excluded, and the asymmetry is the point:
#   n  "Yes" misread as "Nes" would decode to NO. That is a vote inversion, the
#      single worst output this pipeline can produce, and it is the exact case
#      VOTE_FUZZY_MIN_LEN was raised to block. Correct "No" is two characters
#      and already matches exactly, so there is nothing to gain here either.
#   a  ambiguous at the value level: aye -> YES, abstain -> ABSTAIN,
#      absent -> ABSENT.
#   r  "Recuse" is six characters and the fuzzy path already recovers it
#      ("Recure" scores 0.83); decoding it would add risk for no measured gain.
#   e  "excused" shares its initial with the "es" tail of "Yes", which is the
#      fragment this guard exists to reject.
VOTE_DECODE_VALUES = {"y": "YES"}
# V is the measured glyph collision for Y on these boards: "ves" is a real read
# of Kalani's YES on two separate frames. W is deliberately NOT here. "Wecure"
# is a real read of Kartsonis's RECUSE, so folding W onto Y decodes a recusal
# into an aye -- the confidently-wrong vote this whole guard exists to prevent.
VOTE_DECODE_INITIAL_ALIASES = {"v": "y"}
# The decode band. The floor: below three characters a token is a fragment, not
# a word, so "eS", "ye", "N0" and "y" all stay rejected. The ceiling: at
# VOTE_FUZZY_MIN_LEN and above the fuzzy path is allowed to run, and similarity
# over a whole word is better evidence than one letter of it. A long token that
# fuzzy already refused is a badly mangled word whose initial deserves no more
# trust than the rest of it -- "Wecure" is six characters and must stay rejected
# on that ground alone, whatever its initial.
VOTE_DECODE_MIN_LEN = 3
# Well under VOTE_FUZZY_CUTOFF, so a decoded token never outranks a real read of
# the same value box. Callers pick the best-scoring candidate in the window.
VOTE_DECODE_SCORE = 0.45


def decode_vote_token(token: str) -> str | None:
    """Last-resort decode of a short mangled value word against the vocabulary.

    Three guards, each load-bearing. Minimum length: without it "eS" is a Y-word
    tail. Initial letter: without it "eS" is a YES. Maximum length: without it a
    six-character "Wecure" reaches the initial test at all.

    The last guard is that the nearest word in the vocabulary must not disagree
    with the decode. The initial alone is a single letter of evidence, so a
    token that looks more like some other outcome word than like a Y-word is
    rejected rather than decoded.
    """
    if not (VOTE_DECODE_MIN_LEN <= len(token) < VOTE_FUZZY_MIN_LEN):
        return None
    initial = VOTE_DECODE_INITIAL_ALIASES.get(token[0], token[0])
    decoded = VOTE_DECODE_VALUES.get(initial)
    if decoded is None:
        return None

    nearest, best = None, 0.0
    for word, value in VOTE_SYNONYMS.items():
        score = difflib.SequenceMatcher(None, token, word).ratio()
        if score > best:
            nearest, best = value, score
    return decoded if nearest == decoded else None


class UnknownRosterEra(ValueError):
    """Raised when no effective-dated roster covers the requested date."""


def era_for(date: str) -> Era:
    """Pick the roster era covering an ISO date, preferring the narrowest match."""
    matches = [
        era
        for era in ERAS
        if era.start <= date and (era.end is None or date <= era.end)
    ]
    if not matches:
        covered = ", ".join(f"{e.key} ({e.start}..{e.end or 'open'})" for e in ERAS)
        raise UnknownRosterEra(
            f"no roster era covers {date!r}; this pipeline only has rosters for "
            f"{covered}. Add an Era to pipeline/roster.py before parsing votes "
            f"from that meeting -- validating against the wrong council would "
            f"attribute votes to members who were not seated."
        )
    return min(matches, key=lambda e: (e.end or "9999-12-31"))


def normalize_vote_scored(raw: str) -> tuple[str | None, float]:
    """Resolve an OCR'd vote word, reporting how confident the match is.

    Returns (value, score) where an exact vocabulary hit scores 1.0. Callers
    that read several words out of one value box use the score to take the
    best candidate rather than the first, so a stray glyph sitting left of the
    real word can no longer win by position.

    Three tiers, tried in order and scored so that a weaker tier can never
    outrank a stronger one on the same value box: exact vocabulary, then fuzzy
    match for tokens long enough to make similarity meaningful, then the
    initial-letter decoder for the short mangled ones fuzzy must not touch.
    """
    token = re.sub(r"[^a-z]", "", (raw or "").lower())
    if not token:
        return None, 0.0
    if token in VOTE_SYNONYMS:
        return VOTE_SYNONYMS[token], 1.0
    if len(token) < VOTE_FUZZY_MIN_LEN:
        # Too short to fuzzy match without inverting votes, but not necessarily
        # too short to decode: "Yee" is three characters and unambiguous.
        decoded = decode_vote_token(token)
        return (decoded, VOTE_DECODE_SCORE) if decoded else (None, 0.0)

    best: dict[str, float] = {}
    for word, value in VOTE_SYNONYMS.items():
        score = difflib.SequenceMatcher(None, token, word).ratio()
        if score > best.get(value, 0.0):
            best[value] = score
    ranked = sorted(best.items(), key=lambda item: -item[1])
    winner, score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if score >= VOTE_FUZZY_CUTOFF and score - runner_up >= VOTE_FUZZY_MARGIN:
        return winner, score

    # A token long enough to reach the fuzzy path has already been compared
    # against the whole vocabulary, and that comparison is better evidence than
    # an initial letter. So the decoder only confirms the fuzzy winner here, it
    # never overrides it: "Wecure" is a real read of Kartsonis's RECUSE on clip
    # 14821, and because W folds onto Y, decoding it on its own turned a recusal
    # into a YES -- the vote inversion this decoder is supposed to avoid. Fuzzy
    # ranks it RECUSE at 0.67, short of the cutoff, so the honest answer is that
    # the text channel cannot read the box.
    decoded = decode_vote_token(token)
    if decoded and decoded == winner:
        return decoded, VOTE_DECODE_SCORE
    return None, score


def normalize_vote(raw: str) -> str | None:
    return normalize_vote_scored(raw)[0]


# Surnames are 4-8 characters, so a 3-character token is closer to noise than
# to a name ("lie" scores 0.86 against "lieu").
MEMBER_FUZZY_MIN_LEN = 4
MEMBER_FUZZY_CUTOFF = 0.78
MEMBER_FUZZY_MARGIN = 0.10


def match_member(raw_name: str, era: Era) -> Member | None:
    """Resolve an OCR'd name like 'Counciimember Kartsonis' to a roster member."""
    text = re.sub(r"[^A-Za-z \-']", " ", raw_name or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered in era.aliases:
        text = era.aliases[lowered]
        lowered = text.lower()

    # Strip the title, which OCR mangles often ("Counciimember", "Councllmember").
    tokens = text.split()
    if tokens and difflib.get_close_matches(
        tokens[0].lower(), ["councilmember", "council", "mayor", "member"], n=1, cutoff=0.7
    ):
        tokens = tokens[1:]
    if not tokens:
        return None

    surnames = era.by_surname()
    candidate = tokens[-1].lower()
    if candidate in surnames:
        return surnames[candidate]

    full = " ".join(tokens).lower()
    for member in era.members:
        if member.name.lower() == full:
            return member

    if len(candidate) >= MEMBER_FUZZY_MIN_LEN:
        scored = sorted(
            (
                (difflib.SequenceMatcher(None, candidate, surname).ratio(), surname)
                for surname in surnames
            ),
            reverse=True,
        )
        score, surname = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        if score >= MEMBER_FUZZY_CUTOFF and score - runner_up >= MEMBER_FUZZY_MARGIN:
            return surnames[surname]

    # Last resort: a roster surname appearing inside the OCR string. This only
    # decides anything when exactly one surname is in there. Returning the
    # first hit in roster declaration order made "xx lewis yy lieu zz" resolve
    # to Lewis whichever name came first in the text, which is a coin flip
    # dressed up as a match.
    inside = [member for surname, member in surnames.items() if surname in lowered]
    return inside[0] if len(inside) == 1 else None


# Matched as whole words, never as substrings, and "failed" is tested before
# "passed". The bare token "pass" is deliberately absent: with substring
# matching against an alpha-squashed string it made every one of
# "Motion Failed to Pass", "Motion did not pass" and "Not Passed" read as a
# carried motion.
RESULT_WORDS: dict[str, tuple[str, ...]] = {
    "tie": ("tie", "tied"),
    "failed": (
        "failed", "fails", "fail", "failure",
        "denied", "denies", "denial",
        "defeated", "defeat", "lost", "rejected",
    ),
    "passed": ("passed", "passes", "carried", "approved", "adopted"),
}

# Words that invert whatever outcome word shares the line with them. A result
# bar carrying both a negation and a positive outcome ("Not Passed", "Motion
# Passed - Denied") is unreadable, not carried: the safe failure is to reject
# the vote, because publishing a failed motion as passed is unrecoverable.
NEGATION_WORDS = frozenset(
    {
        "not", "never", "cannot", "cant", "didnt", "doesnt", "isnt", "wasnt",
        "without", "nor", "unless",
        "failed", "fails", "fail", "failure",
        "denied", "denies", "denial",
        "defeated", "defeat", "lost", "rejected", "withdrawn",
    }
)

# Words that frame an outcome on a real result bar ("Result: Motion Passed").
# They are not evidence of an outcome themselves, but they are also not content,
# so they do not count against the short-outcome guard below.
RESULT_ANCHOR_WORDS = ("result", "results", "motion", "motions", "vote", "votes", "moved")

# A garbled word has to look clearly more like one outcome than the other before
# it is trusted, so a smudged "Failed" can never be read as "passed".
FUZZY_RESULT_CUTOFF = 0.78
FUZZY_RESULT_MARGIN = 0.08

# Fuzzy matching needs both sides to be long enough for a match to mean
# something. Measured against the real bars on clip 14821: every genuine read is
# a 6-character token scoring 0.83+ against "passed"/"failed", while every false
# read came from a 3-4 character fragment landing on a short vocabulary word --
# "ost" scores 0.857 against "lost", "ened" 0.800 against "denied" and "tice"
# 0.857 against "tie". Requiring 5 characters on both sides removes all of them
# and keeps all of the real ones.
FUZZY_RESULT_MIN_LEN = 5
FUZZY_RESULT_MIN_WORD_LEN = 5

# An outcome word shorter than this, matched exactly, has to be the whole line
# apart from framing words. "tie" is three characters, so noise like
# "nina tie bE", "tie Ot" and "dss tie" otherwise reports a tied vote with full
# confidence -- all three came off real frames on boards that passed. A genuine
# bar reads "Motion Tied" or "Tie Vote", which are framing words only.
SHORT_OUTCOME_LEN = 5
SHORT_OUTCOME_MAX_CONTENT = 0


def result_tokens(raw: str) -> list[str]:
    return re.findall(r"[a-z]+", (raw or "").lower())


def _is_anchor(token: str) -> bool:
    """True when a token is the framing of a result line rather than content."""
    if token in RESULT_ANCHOR_WORDS:
        return True
    return any(
        difflib.SequenceMatcher(None, token, word).ratio() >= 0.75
        for word in RESULT_ANCHOR_WORDS
        if len(token) >= 4
    )


def _short_outcome_is_isolated(tokens: list[str], matched_words: set[str]) -> bool:
    """True when a short outcome word carries the line rather than riding on noise.

    "tie" is three characters, so it turns up inside garbage often enough that an
    exact hit on it is not evidence on its own. A real bar reads "Motion Tied" or
    just "Tie", so everything other than the outcome and the framing words has to
    be absent.
    """
    content = [
        token
        for token in tokens
        if token not in matched_words and not _is_anchor(token)
    ]
    return len(content) <= SHORT_OUTCOME_MAX_CONTENT


def _negates(tokens: set[str], outcome: str | None) -> bool:
    """True when the line carries a negation that makes `outcome` unsafe.

    Only a positive outcome can be negated: "Motion Failed" contains a
    negation word and still means exactly what it says.
    """
    return outcome == "passed" and bool(tokens & NEGATION_WORDS)


def normalize_result(raw: str) -> str | None:
    tokens = result_tokens(raw)
    tokenset = set(tokens)
    if not tokenset:
        return None
    matched = [
        outcome
        for outcome, words in RESULT_WORDS.items()
        if tokenset.intersection(words)
    ]
    # Two different outcomes on one line means the read is wrong, not that the
    # motion both passed and failed.
    if len(matched) != 1:
        return None
    outcome = matched[0]
    hits = tokenset.intersection(RESULT_WORDS[outcome])
    if all(len(word) < SHORT_OUTCOME_LEN for word in hits):
        if not _short_outcome_is_isolated(tokens, hits):
            return None
    if _negates(tokenset, outcome):
        return None
    return outcome


def normalize_result_fuzzy(raw: str) -> tuple[str | None, float]:
    """Match a badly OCR'd result line against the VoteCast outcome vocabulary.

    The result bar is faint grey prose that Tesseract mangles into things like
    "Wenet Paseed". Scoring each word against the known outcome words recovers
    those, but only when one outcome wins clearly; an ambiguous smudge returns
    nothing so the vote is rejected rather than guessed.
    """
    exact = normalize_result(raw)
    if exact:
        return exact, 1.0

    tokens = result_tokens(raw)
    tokenset = set(tokens)
    best: dict[str, float] = {}
    for token in tokens:
        if len(token) < FUZZY_RESULT_MIN_LEN:
            continue
        for outcome, words in RESULT_WORDS.items():
            for word in words:
                # A short vocabulary word is reachable by too much noise to be
                # matched approximately; it only counts on the exact path above.
                if len(word) < FUZZY_RESULT_MIN_WORD_LEN:
                    continue
                score = difflib.SequenceMatcher(None, token, word).ratio()
                if score > best.get(outcome, 0.0):
                    best[outcome] = score

    if not best:
        return None, 0.0
    ranked = sorted(best.items(), key=lambda item: -item[1])
    winner, score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if score < FUZZY_RESULT_CUTOFF or score - runner_up < FUZZY_RESULT_MARGIN:
        return None, score
    # The same negation guard as the exact path. Without it "Motion did not
    # pass" comes back through here as passed=0.80 on the token "pass", which
    # is precisely the read that dropping the bare "pass" token was meant to
    # stop.
    if _negates(tokenset, winner):
        return None, score
    return winner, score
