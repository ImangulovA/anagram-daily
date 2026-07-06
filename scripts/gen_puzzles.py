#!/usr/bin/env python3
"""
Anagram Daily -- anagram engine + daily puzzle generator (Agent 2).

Consumes  data/words_defs.json  (Agent 1: word -> {def, freq})
Emits     data/puzzles.json  and  data/puzzles.js  (window.PUZZLES = [...])

Core invariant for every puzzle:  sorted(A.word + B.word) == sorted(C.word)
Length rules: len(C) >= 8, len(A) >= 2, len(B) >= 2  (=> len(A)+len(B)==len(C))

Algorithm (efficient, NOT O(n^2) over pairs):
  * signature(word) = "".join(sorted(word))  -- multiset key.
  * anagram groups: signature -> [words]; plus a set of all signatures.
  * For each final word C (len>=8): enumerate sub-multisets of C's letters that
    are a known word signature (candidate A). Remainder = C minus A; if remainder
    is also a known signature and both halves have len >= 2, we have a valid split.
  * Sub-multiset enumeration is bounded by product(count_i + 1) over distinct
    letters, which stays tractable for ordinary words.

Bootstrap: if data/words_defs.json is missing, a curated starter dictionary is
embedded so the whole pipeline runs end-to-end. Re-running once the full
words_defs.json exists regenerates better puzzles with NO code changes.

Reproducible: any randomness is seeded deterministically.
"""

import itertools
import json
import os
import sys
from collections import Counter
from datetime import date, timedelta

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(ROOT, "data")
WORDS_DEFS_PATH = os.path.join(DATA_DIR, "words_defs.json")
PUZZLES_JSON_PATH = os.path.join(DATA_DIR, "puzzles.json")
PUZZLES_JS_PATH = os.path.join(DATA_DIR, "puzzles.js")
# SvelteKit data module consumed by the app (app/src/lib/game/data/days.js).
DAYS_JS_PATH = os.path.join(
    ROOT, "app", "src", "lib", "game", "data", "days.js")

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
ANCHOR_DATE = date(2026, 7, 5)   # day 0 (public launch anchor)
# First (earliest) day index in the buffer. Negative days are "historical"
# playtest days BEFORE launch. date(day) = ANCHOR_DATE + day. So:
#   day -34 -> 2026-06-01, day -1 -> 2026-07-04, day 0 -> 2026-07-05.
FIRST_DAY = -34
LAST_DAY = 129                    # inclusive; buffer covers FIRST_DAY..LAST_DAY
NUM_DAYS = LAST_DAY - FIRST_DAY + 1  # contiguous day count
MIN_C_LEN = 8
MIN_PART_LEN = 2
# Prefer final words in this sweet-spot length range for daily play.
PREFERRED_C_LEN = (8, 11)
# Minimum freq we accept for a word to APPEAR in a puzzle (keeps clues solvable).
MIN_WORD_FREQ = 0.12
# Minimum freq for the FINAL word C (it should be recognizable).
MIN_C_FREQ = 0.20
SEED = 20260705

# --- Curation-quality knobs (coordinator upgrades) --------------------------
# Soft penalty multiplier applied to a triple's quality for EACH len-2 source
# word. 2-letter function words (IN, ON, OF, ...) make weak, repetitive clues,
# so we deprioritize them; they only surface when nothing better fills a day.
LEN2_PENALTY = 0.55
# Prefer source words of length >= 3 with decent freq.
PREFERRED_MIN_SRC_LEN = 3
# Max number of days any single source word may appear across the whole buffer.
MAX_SOURCE_WORD_USES = 3
# A source word may not repeat within this many days of a prior use.
SOURCE_WORD_MIN_GAP = 7

# --- Weekday difficulty ramp (by final-word length) -------------------------
# The day of week decides how long the anagram (word C) is. weekday(): Mon=0 ..
# Sun=6.  Sun/Mon/Tue -> 8 letters | Wed/Thu -> 9 | Fri/Sat -> 10..12.
WEEKDAY_C_LENS = {
    6: (8,),            # Sunday
    0: (8,),            # Monday
    1: (8,),            # Tuesday
    2: (9,),            # Wednesday
    3: (9,),            # Thursday
    4: (10, 11, 12),    # Friday
    5: (10, 11, 12),    # Saturday
}


def len_target_for_weekday(weekday):
    """Allowed C lengths for a given weekday index (Mon=0..Sun=6)."""
    return set(WEEKDAY_C_LENS.get(weekday, (8, 9, 10, 11, 12)))

# ----------------------------------------------------------------------------
# Bootstrap starter dictionary (used ONLY if words_defs.json is absent).
# Curated so that many valid A+B==C splits exist with clean definitions.
# freq is a rough commonness in [0,1].
# ----------------------------------------------------------------------------
STARTER_WORDS = {
    # short common source words (2-6 letters) ------------------------------
    "MOON": ("Earth's natural satellite", 0.91),
    "SUN": ("The star at the center of our solar system", 0.97),
    "STAR": ("A luminous ball of gas in the night sky", 0.93),
    "STARE": ("To gaze fixedly", 0.72),
    "STARER": ("One who gazes fixedly", 0.30),
    "RATE": ("A measure or speed of something", 0.86),
    "TEAR": ("A drop of liquid from the eye", 0.83),
    "RACE": ("A contest of speed", 0.88),
    "CARE": ("To feel concern or interest", 0.90),
    "ACRE": ("A unit of land area", 0.66),
    "EARN": ("To gain by work", 0.82),
    "NEAR": ("Close in distance", 0.90),
    "LATE": ("After the expected time", 0.88),
    "TALE": ("A story", 0.80),
    "MEAL": ("Food eaten at one time", 0.86),
    "LAME": ("Unable to walk properly", 0.62),
    "MALE": ("Of the sex that fathers young", 0.86),
    "LEAN": ("Thin; to incline", 0.78),
    "LANE": ("A narrow road or path", 0.79),
    "MEAN": ("To intend; unkind", 0.87),
    "NAME": ("A word by which someone is known", 0.94),
    "AMEN": ("Said at the end of a prayer", 0.60),
    "TIME": ("The ongoing sequence of events", 0.96),
    "ITEM": ("A single article or unit", 0.85),
    "MITE": ("A tiny arachnid; a small amount", 0.45),
    "EMIT": ("To give off or send out", 0.55),
    "TILE": ("A flat slab for covering surfaces", 0.70),
    "LITE": ("Low in calories; light", 0.40),
    "LIME": ("A green citrus fruit", 0.68),
    "MILE": ("A unit of distance", 0.80),
    "RIME": ("Frost; hoarfrost", 0.28),
    "MIRE": ("Soft muddy ground", 0.35),
    "RISE": ("To move upward", 0.87),
    "SIRE": ("A male parent of an animal", 0.44),
    "IRES": ("Feelings of anger (plural)", 0.20),
    "REIN": ("A strap to guide a horse", 0.50),
    "NINE": ("The number after eight", 0.85),
    "LINE": ("A long narrow mark", 0.92),
    "NILE": ("A great river of Africa", 0.55),
    "LIEN": ("A legal claim on property", 0.30),
    "SALE": ("The exchange of goods for money", 0.88),
    "SEAL": ("A marine mammal; to close tightly", 0.74),
    "ALES": ("Types of beer (plural)", 0.30),
    "TALES": ("Stories (plural)", 0.62),
    "STEAL": ("To take without permission", 0.80),
    "SLATE": ("A fine-grained gray rock", 0.55),
    "STALE": ("No longer fresh", 0.66),
    "LEAST": ("Smallest in amount", 0.84),
    "TESLA": ("A unit of magnetic flux density", 0.40),
    "REAL": ("Actually existing", 0.93),
    "EARL": ("A British nobleman", 0.45),
    "LEAR": ("A king in a Shakespeare play", 0.30),
    "PALE": ("Light in color", 0.75),
    "LEAP": ("To jump", 0.72),
    "PEAL": ("A loud ringing of bells", 0.35),
    "PLEA": ("An earnest request", 0.58),
    "PLATE": ("A flat dish", 0.82),
    "PETAL": ("A part of a flower", 0.62),
    "LEPT": ("Past form of leap (dialect)", 0.10),
    "STOP": ("To cease moving", 0.92),
    "POTS": ("Containers for cooking (plural)", 0.55),
    "SPOT": ("A small round mark", 0.80),
    "TOPS": ("Upper parts (plural)", 0.62),
    "OPTS": ("Chooses (verb)", 0.35),
    "POST": ("To send mail; an upright support", 0.86),
    "PORT": ("A harbor town", 0.78),
    "SORT": ("To arrange in order", 0.80),
    "ROTS": ("Decays (verb)", 0.30),
    "TORS": ("Rocky peaks (plural)", 0.12),
    "ROSE": ("A thorny flowering plant", 0.85),
    "SORE": ("Painful to the touch", 0.74),
    "EROS": ("The Greek god of love", 0.28),
    "ORES": ("Rocks containing metal (plural)", 0.40),
    "ROES": ("Fish eggs (plural)", 0.15),
    "GONE": ("Having departed", 0.88),
    "GENE": ("A unit of heredity", 0.70),
    "OGRE": ("A man-eating giant", 0.50),
    "GORE": ("Blood from a wound", 0.45),
    "EGO": ("A person's sense of self", 0.70),
    "AGE": ("The length of time lived", 0.94),
    "GEAR": ("Equipment; a toothed wheel", 0.72),
    "RAGE": ("Violent anger", 0.72),
    "OMEN": ("A sign of the future", 0.55),
    "NOME": ("A province of ancient Egypt", 0.15),
    "MOAN": ("A low sound of pain", 0.55),
    "ROMAN": ("Of ancient Rome", 0.72),
    "MANOR": ("A large country house", 0.55),
    "NORM": ("A standard or typical pattern", 0.72),
    "TRON": ("A science-fiction film", 0.20),
    # additional building blocks -------------------------------------------
    "AS": ("To the same degree; because", 0.95),
    "AT": ("Indicating location", 0.97),
    "TO": ("Expressing motion toward", 0.98),
    "ON": ("Physically in contact with", 0.97),
    "OR": ("Presenting an alternative", 0.96),
    "NO": ("Not any; a negative reply", 0.97),
    "SO": ("To such a great extent", 0.96),
    "ME": ("The objective form of I", 0.95),
    "AN": ("The indefinite article", 0.95),
    "IN": ("Located inside", 0.98),
    "IS": ("Third person of the verb be", 0.98),
    "IT": ("The thing referred to", 0.98),
    "RE": ("Concerning; with regard to", 0.40),
    "TON": ("A unit of weight", 0.68),
    "NOT": ("Used to form the negative", 0.95),
    "ARE": ("Present plural of be", 0.96),
    "EAR": ("The organ of hearing", 0.85),
    "ERA": ("A period of history", 0.72),
    "ART": ("Creative human expression", 0.88),
    "RAT": ("A large rodent", 0.70),
    "TAR": ("A dark sticky substance", 0.55),
    "TEA": ("A hot drink from leaves", 0.85),
    "ATE": ("Past tense of eat", 0.82),
    "EAT": ("To consume food", 0.90),
    "SEA": ("A large body of salt water", 0.90),
    "SET": ("To put in place; a group", 0.93),
    "EST": ("Established (abbrev.)", 0.20),
    "LET": ("To allow", 0.88),
    "MET": ("Past tense of meet", 0.86),
    "MEN": ("Adult males (plural)", 0.90),
    "NET": ("A mesh for catching", 0.80),
    "TEN": ("The number after nine", 0.88),
    "PEN": ("A writing instrument", 0.82),
    "PET": ("A domestic animal companion", 0.80),
    "TIP": ("A pointed end; gratuity", 0.75),
    "PIT": ("A hole in the ground", 0.70),
    "SIP": ("To drink in small amounts", 0.60),
    "PIE": ("A baked dish with a crust", 0.78),
    "LIP": ("The edge of the mouth", 0.75),
    "SON": ("A male child", 0.88),
    "NOR": ("And not", 0.75),
    "OAR": ("A pole for rowing", 0.55),
    "ROE": ("Fish eggs", 0.30),
    "ORE": ("Rock containing metal", 0.55),
    "ROT": ("To decay", 0.55),
    "TOR": ("A rocky hill", 0.20),
    "ONE": ("The number after zero", 0.92),
    "EON": ("An immensely long time", 0.40),
    "GEM": ("A precious stone", 0.60),
    "MEG": ("A megabyte (informal)", 0.30),
    "GAS": ("An airlike substance; fuel", 0.85),
    "SAG": ("To sink or droop", 0.45),
    "RIP": ("To tear apart", 0.65),
    "PRO": ("A professional; in favor", 0.72),
    "OPT": ("To make a choice", 0.55),
    "TOP": ("The highest part", 0.88),
    "POT": ("A cooking container", 0.78),
    "SOP": ("To soak up liquid", 0.25),
    "OPS": ("Operations (informal)", 0.30),
    "SPA": ("A place for health treatments", 0.60),
    "TAP": ("To strike lightly", 0.70),
    "PAT": ("A light touch", 0.62),
    "APT": ("Suitable; likely", 0.55),
    "PEA": ("A small round green vegetable", 0.68),
    "APE": ("A large tailless primate", 0.65),
    "NAP": ("A short sleep", 0.62),
    "PAN": ("A metal cooking vessel", 0.75),
    "MAP": ("A drawing of an area", 0.82),
    "AMP": ("A unit of electric current", 0.45),
    "RAP": ("A style of music; to knock", 0.62),
    "PAR": ("An accepted standard", 0.60),
    "ARC": ("A curved line", 0.62),
    "CAR": ("A road vehicle", 0.92),
    "ACE": ("A playing card; an expert", 0.70),
    "ICE": ("Frozen water", 0.85),
    "RICE": ("A cereal grain staple", 0.80),
    "CITE": ("To quote as evidence", 0.55),
    "NICE": ("Pleasant; agreeable", 0.85),
    # longer targets (final words, len >= 8) -------------------------------
    "ASTRONOMER": ("A scientist who studies the stars", 0.66),
    "MOONSTARER": ("(playful) one who stares at the moon", 0.05),
    "TOLERANCE": ("The capacity to endure difficulty", 0.70),
    "GENERATOR": ("A machine that produces electricity", 0.70),
    "MODERATES": ("Makes less extreme", 0.55),
    "REINSTATE": ("To restore to a former position", 0.55),
    "PROMOTING": ("Encouraging or advancing", 0.60),
    "STAMPEDE": ("A sudden rush of animals", 0.55),
    "PLEASANT": ("Giving a sense of enjoyment", 0.10),
    "MANEATER": ("An animal that eats people", 0.35),
    "SALTIER": ("More salty", 0.35),
    "SALTINE": ("A thin crisp cracker", 0.30),
    "ENTAILS": ("Involves as a necessary part", 0.45),
    "NAILSET": ("A tool for driving nails", 0.10),
    "TENAILS": ("(rare) small fortifications", 0.05),
    "LATRINES": ("Communal toilets", 0.30),
    "RATLINES": ("Rope ladders on a ship's rigging", 0.10),
    "ENTRAILS": ("The internal organs", 0.40),
    "RETAINS": ("Keeps possession of", 0.50),
    "RETINAS": ("Light-sensitive eye layers (plural)", 0.30),
    "STAINER": ("One who or that which stains", 0.10),
    "NASTIER": ("More unpleasant", 0.40),
    "ANTSIER": ("More restless", 0.15),
    "RATINES": ("Coarse ribbed fabrics", 0.03),
    "STEARIN": ("A solid fat used in candles", 0.05),
    "TRAINEES": ("People being trained (plural)", 0.45),
    "TERNARIES": ("Groups of three (plural)", 0.05),
    "OPERATES": ("Controls the working of", 0.55),
    "PROTEASE": ("An enzyme that breaks down protein", 0.30),
    "SEAPORTS": ("Towns with harbors (plural)", 0.35),
    "ESPRESSO": ("A strong concentrated coffee", 0.60),
    "GENOMES": ("Complete sets of genes (plural)", 0.35),
    "MONGREL": ("A dog of mixed breed", 0.45),
    "STRONGER": ("More powerful", 0.72),
    "ROENTGENS": ("Units of radiation exposure (plural)", 0.05),
    "MOONGATES": ("(playful) gateways to the moon", 0.02),
    "MEGATONS": ("Units of explosive force (plural)", 0.20),
    "MAGNETOS": ("Small electric generators (plural)", 0.15),
    "ROOMMATE": ("A person who shares a room", 0.55),
    "NAMEPLATE": ("A sign showing a name", 0.45),
    "PARENTAL": ("Relating to a parent", 0.55),
    "PATERNAL": ("Relating to a father", 0.50),
    "PRENATAL": ("Before birth", 0.50),
    "PLANETARY": ("Relating to planets", 0.45),
    "PALTRIER": ("Meaner or more meager", 0.10),
    "PORTABLE": ("Able to be carried", 0.65),
    "PRORATES": ("Divides proportionally", 0.20),
    "PRAETORS": ("Ancient Roman magistrates (plural)", 0.05),
    "TEARDROP": ("A single tear", 0.45),
    "PREDATOR": ("An animal that hunts others", 0.65),
    "TERRAPIN": ("A small freshwater turtle", 0.35),
    "REPAINTS": ("Paints again", 0.30),
    "PERTAINS": ("Is relevant or applicable", 0.45),
    "PANTRIES": ("Food storage rooms (plural)", 0.35),
    "PAINTERS": ("Artists who paint (plural)", 0.50),
    "PINASTER": ("A Mediterranean pine tree", 0.03),
    "PRISTANE": ("A colorless liquid hydrocarbon", 0.02),
    "TERRAINS": ("Types of land (plural)", 0.40),
    "TRAINERS": ("People who train others (plural)", 0.50),
    "STRAINER": ("A utensil for filtering liquids", 0.40),
    "RESTRAIN": ("To hold back", 0.50),
    "RETRAINS": ("Trains again", 0.25),
    "SEROTONIN": ("A brain chemical affecting mood", 0.45),
    "OPERATION": ("A surgical procedure; an action", 0.65),
    "REPUTATION": ("The beliefs held about someone", 0.62),
}


def build_starter_defs():
    """Return words_defs.json-shaped dict from STARTER_WORDS."""
    out = {}
    for word, (definition, freq) in STARTER_WORDS.items():
        out[word] = {"def": definition, "freq": float(freq)}
    return out


# ----------------------------------------------------------------------------
# Loading / cleaning
# ----------------------------------------------------------------------------
def load_words_defs():
    """Load words_defs.json if present, else the embedded starter set.

    Returns (defs_dict, source_label).
    """
    if os.path.exists(WORDS_DEFS_PATH):
        with open(WORDS_DEFS_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        source = "data/words_defs.json (Agent 1)"
    else:
        raw = build_starter_defs()
        source = "embedded STARTER dictionary (bootstrap; words_defs.json absent)"

    clean = {}
    for word, meta in raw.items():
        if not isinstance(word, str):
            continue
        w = word.strip().upper()
        if not w.isalpha() or not w.isascii():
            continue
        if not (2 <= len(w) <= 15):
            continue
        if not isinstance(meta, dict):
            continue
        definition = meta.get("def")
        if not isinstance(definition, str) or not definition.strip():
            continue
        try:
            freq = float(meta.get("freq", 0.0))
        except (TypeError, ValueError):
            freq = 0.0
        freq = max(0.0, min(1.0, freq))
        clean[w] = {"def": definition.strip(), "freq": freq}
    return clean, source


def signature(word):
    return "".join(sorted(word))


def _word_stem(word):
    """Cheap stem: lowercase word minus common inflectional suffixes.

    Used to catch circular clues that restate the answer. Not linguistically
    perfect, just enough to flag 'OPERATION' clue containing 'operat...'.
    """
    w = word.lower()
    for suf in ("ations", "ation", "ings", "ing", "ers", "er", "ies", "ied",
                "ed", "es", "s", "ly", "al", "ial", "ive", "ion"):
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def is_circular_clue(word, clue):
    """True if the clue restates the answer (contains the word or its stem).

    Guards against self-referential defs like OPERATION -> "...operating...".
    """
    if not clue:
        return True
    clue_l = clue.lower()
    w = word.lower()
    if w in clue_l:                      # exact answer appears in its own clue
        return True
    stem = _word_stem(word)
    if len(stem) >= 4 and stem in clue_l:  # shared stem (operat-, think-, ...)
        return True
    return False


# ----------------------------------------------------------------------------
# Cognate / same-root detection
# ----------------------------------------------------------------------------
# The three answer words (A, B, C) must not be etymologically related / share a
# root. GREAT + SET -> GREATEST is the classic offender: GREATEST is just GREAT
# with a superlative suffix, so B and C are the same root. Stemmers (Porter /
# Snowball) do NOT reduce "greatest" -> "great", so we use an explicit,
# deterministic, offline morphology check instead.
#
# Inflectional + common derivational suffixes. Single-letter 'd' is deliberately
# EXCLUDED (it would flag unrelated pairs like CAR/CARD); 'ed' still covers past
# tense. Silent-e drop, y->i, and final-consonant doubling are handled below.
_INFLECTION_SUFFIXES = frozenset({
    "s", "es", "ies", "ied", "ed", "ing", "ings",
    "er", "ers", "est", "or", "ors",
    "ly", "y", "al", "ial", "ic", "ical", "ive", "ivity",
    "ion", "ions", "tion", "sion", "ation", "ations",
    "ness", "ment", "ments", "ful", "less", "able", "ible",
    "ity", "ty", "ance", "ence", "ancy", "ency",
    "ish", "en", "ens", "ened", "ist", "ists", "ism",
    "ize", "ise", "ized", "ised", "izing", "ising",
    "age", "ery", "ary", "ory", "ous", "eous", "ious",
})


def _common_prefix_len(x, y):
    n = min(len(x), len(y))
    i = 0
    while i < n and x[i] == y[i]:
        i += 1
    return i


def _is_suffixed_form(short, long_):
    """True if ``long_`` looks like ``short`` + a known suffix, allowing the
    usual English spelling tweaks (silent-e drop, y->i, consonant doubling)."""
    if len(short) < 3:
        return False
    # 1. plain concatenation:  great + est -> greatest
    if long_.startswith(short):
        rem = long_[len(short):]
        if rem in _INFLECTION_SUFFIXES:
            return True
        # doubled final consonant:  run + n + ing -> running
        if rem[:1] == short[-1:] and rem[1:] in _INFLECTION_SUFFIXES:
            return True
    # 2. silent-e drop:  make -> mak + ing -> making
    if short.endswith("e") and long_.startswith(short[:-1]):
        rem = long_[len(short) - 1:]
        if rem in _INFLECTION_SUFFIXES:
            return True
    # 3. y -> i:  happy -> happi + est -> happiest
    if short.endswith("y") and long_.startswith(short[:-1] + "i"):
        rem = long_[len(short):]
        if rem in _INFLECTION_SUFFIXES:
            return True
    return False


def _agg_stem(word):
    """Strip ONE longest inflectional/derivational suffix (base kept >= 3)."""
    w = word.lower()
    for suf in sorted(_INFLECTION_SUFFIXES, key=len, reverse=True):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def are_cognate(w1, w2):
    """Heuristic: True if two words share a root / are etymologically related
    (an inflection or derivation of a common stem).

    Deterministic and offline. Tuned to catch same-root pairs like
    GREAT/GREATEST, NATION/NATIONAL, PLAY/PLAYER, HISTORY/HISTORIC while leaving
    unrelated look-alikes (STAR/START, CAR/CARD) untouched.
    """
    a, b = w1.lower(), w2.lower()
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    # 1. One word is an inflected / derived form of the other.
    if _is_suffixed_form(short, long_):
        return True
    # 2. Same aggressive stem AND a solid shared prefix (the prefix guards
    #    against accidental stem collisions between unrelated words).
    if _agg_stem(a) == _agg_stem(b) and _common_prefix_len(a, b) >= 3:
        return True
    # 3. A long shared prefix (>= 5) implies a shared root family
    #    (HISTORY/HISTORIC); STAR/START share only 4 and are left alone.
    if _common_prefix_len(a, b) >= 5:
        return True
    return False


def triple_has_cognates(a_word, b_word, c_word):
    """True if ANY pair among the three answer words is cognate/same-root."""
    return (are_cognate(a_word, b_word)
            or are_cognate(a_word, c_word)
            or are_cognate(b_word, c_word))


def source_is_substring_of_final(a_word, b_word, c_word):
    """True if source word A or B appears as a SUBSTRING of the final word C.

    Catches compounds / embedded roots the cognate heuristic misses, e.g.
    SOME + BODY -> SOMEBODY, or GET inside TOGETHER. Source words must never be
    literally contained in the answer.
    """
    cu = c_word.upper()
    return a_word.upper() in cu or b_word.upper() in cu


# Final (C) words to exclude entirely. Populated from the SEMANTIC (AI) audit of
# same-root / compound / etymologically-related answers that the mechanical
# heuristics above can't catch (e.g. irregular derivations, loan compounds).
# Dropping a flagged C makes regeneration pick a clean alternative for that day.
BLOCKED_FINAL_WORDS = {
    "SOMEBODY",    # SOME + BODY (compound); reported day -33
    # --- Flagged by the semantic (AI) audit, 2026-07-06 ---
    "FORGOTTEN",   # FORGET + N -> FORGOTTEN is the past participle of FORGET
    "SEPARATE",    # APART / SEPARATE share the Latin pars/separare root
    "ENTRANCE",    # ENTER / ENTRANCE (noun derivation of the verb enter)
    "MONETARY",    # MONEY / MONETARY both from Latin moneta
    "CHARTERED",   # CARD / CHARTERED both from Latin charta (paper)
}


# ----------------------------------------------------------------------------
# Anagram engine
# ----------------------------------------------------------------------------
def build_index(defs):
    """signature -> list of words (sorted best-first by freq)."""
    groups = {}
    for word, meta in defs.items():
        sig = signature(word)
        groups.setdefault(sig, []).append(word)
    for sig, words in groups.items():
        words.sort(key=lambda w: (-defs[w]["freq"], w))
    return groups


def sub_multiset_signatures(counter):
    """Yield every non-empty proper sub-multiset signature of a Counter.

    Bounded by product(count_i + 1). We yield signatures (sorted strings).
    """
    letters = sorted(counter.keys())
    ranges = [range(counter[ch] + 1) for ch in letters]
    total = 1
    for ch in letters:
        total *= (counter[ch] + 1)
    for combo in itertools.product(*ranges):
        # combo[i] = how many of letters[i] to take
        n = sum(combo)
        if n == 0:
            continue
        yield "".join(ch * cnt for ch, cnt in zip(letters, combo) if cnt)


def find_splits(defs, groups):
    """Find valid (a_word, b_word, c_word) triples satisfying all rules.

    Returns a list of triple dicts with a quality score for curation.
    """
    all_sigs = set(groups.keys())
    triples = []
    seen_letter_splits = set()  # (c_word, a_sig) dedupe within a C

    for c_word, c_meta in defs.items():
        clen = len(c_word)
        if clen < MIN_C_LEN:
            continue
        if c_meta["freq"] < MIN_C_FREQ:
            continue
        # Skip final words flagged by the semantic (AI) audit as related to their
        # sources / compounds.
        if c_word in BLOCKED_FINAL_WORDS:
            continue
        # Skip final words whose clue is circular / self-referential.
        if is_circular_clue(c_word, c_meta["def"]):
            continue
        c_counter = Counter(c_word)

        # Enumerate sub-multisets of C -> candidate A signature.
        for a_sig in sub_multiset_signatures(c_counter):
            a_len = len(a_sig)
            if a_len < MIN_PART_LEN or a_len > clen - MIN_PART_LEN:
                continue
            if a_sig not in all_sigs:
                continue
            # remainder = C minus A
            rem = c_counter - Counter(a_sig)
            b_sig = "".join(sorted(rem.elements()))
            if len(b_sig) < MIN_PART_LEN:
                continue
            if b_sig not in all_sigs:
                continue
            # Order-independent: skip mirror (we require a_sig <= b_sig lexically
            # to avoid emitting both (A,B) and (B,A)).
            key_pair = tuple(sorted((a_sig, b_sig)))
            dedupe_key = (c_word, key_pair)
            if dedupe_key in seen_letter_splits:
                continue
            seen_letter_splits.add(dedupe_key)

            # Materialize best words for each side. Pick highest-freq word that
            # is NOT equal to c_word itself.
            a_word = _pick_word(groups[a_sig], defs, exclude=c_word)
            b_word = _pick_word(groups[b_sig], defs, exclude=c_word)
            if a_word is None or b_word is None:
                continue
            if a_word == b_word and a_sig == b_sig:
                # need two distinct words if same signature; try second-best
                alt = [w for w in groups[b_sig] if w != a_word]
                if not alt:
                    continue
                b_word = alt[0]

            # Freq gate on the visible source words.
            a_freq = defs[a_word]["freq"]
            b_freq = defs[b_word]["freq"]
            if a_freq < MIN_WORD_FREQ or b_freq < MIN_WORD_FREQ:
                continue

            # Drop triples whose source clues are circular (cheap guard).
            if is_circular_clue(a_word, defs[a_word]["def"]) or \
                    is_circular_clue(b_word, defs[b_word]["def"]):
                continue

            # Drop triples whose answers are cognate / share a root
            # (e.g. GREAT + SET -> GREATEST). Answers must be unrelated words.
            if triple_has_cognates(a_word, b_word, c_word):
                continue

            # Drop triples where a source word is embedded in the final word
            # (e.g. SOME + BODY -> SOMEBODY, GET in TOGETHER).
            if source_is_substring_of_final(a_word, b_word, c_word):
                continue

            c_freq = c_meta["freq"]
            quality = _quality(clen, a_freq, b_freq, c_freq,
                               len(a_word), len(b_word))
            triples.append({
                "a": a_word,
                "b": b_word,
                "c": c_word,
                "a_freq": a_freq,
                "b_freq": b_freq,
                "c_freq": c_freq,
                "clen": clen,
                "quality": quality,
                "difficulty": _difficulty(clen, a_freq, b_freq, c_freq),
            })
    return triples


def _pick_word(candidates, defs, exclude=None):
    for w in candidates:
        if w != exclude:
            return w
    return None


def _quality(clen, a_freq, b_freq, c_freq, a_len=3, b_len=3):
    """Higher is better for curation. Rewards common words + sweet-spot C
    length, and PENALIZES 2-letter source words (weak, repetitive clues)."""
    freq_score = (a_freq + b_freq + 1.5 * c_freq)
    lo, hi = PREFERRED_C_LEN
    if lo <= clen <= hi:
        len_bonus = 1.0
    else:
        len_bonus = max(0.0, 1.0 - 0.15 * min(abs(clen - lo), abs(clen - hi)))
    quality = freq_score * (0.5 + 0.5 * len_bonus)
    # Soft penalty per len-2 source word so len>=3 triples win when available.
    for slen in (a_len, b_len):
        if slen < PREFERRED_MIN_SRC_LEN:
            quality *= LEN2_PENALTY
    return quality


def _raw_hardness(clen, a_freq, b_freq, c_freq):
    """Continuous hardness score (higher = harder). Rarer + longer => harder.

    The rarest source word dominates (the puzzle is only as easy as its hardest
    clue), tempered by the final word's freq and C length.
    """
    min_src = min(a_freq, b_freq)          # hardest clue drives difficulty
    avg_freq = (a_freq + b_freq + c_freq) / 3.0
    rarity = 1.0 - (0.6 * min_src + 0.4 * avg_freq)
    length = min(1.0, max(0.0, (clen - 8) / 5.0))
    return 0.7 * rarity + 0.3 * length


def _difficulty(clen, a_freq, b_freq, c_freq):
    """Absolute fallback map to 1..5 (used before pool-relative rescaling)."""
    score = _raw_hardness(clen, a_freq, b_freq, c_freq)
    return max(1, min(5, int(round(1 + score * 4))))


# ----------------------------------------------------------------------------
# Curation into a contiguous daily buffer
# ----------------------------------------------------------------------------
def curate(triples, num_days):
    """Select and order num_days puzzles. Deterministic given the input.

    Pipeline:
      1. Best triple per unique C word (dedupe C).
      2. Assign pool-relative difficulty quintiles (1..5) across the top pool.
      3. Greedy day-by-day placement that honors: weekday difficulty ramp,
         source-word reuse caps + min-gap, no repeated C, and a strong day-0.
    """
    # 1. Best triple per unique C word.
    best_per_c = {}
    for t in triples:
        c = t["c"]
        if c not in best_per_c or t["quality"] > best_per_c[c]["quality"]:
            best_per_c[c] = t
    unique = list(best_per_c.values())
    unique.sort(key=lambda t: (-t["quality"], t["c"]))

    # 2. Difficulty over a generous candidate pool (so bands stay populated even
    # after the reuse caps thin things out). Use up to ~6x the buffer.
    pool = unique[: max(num_days * 6, num_days)]
    _assign_relative_difficulty(pool)

    # 3. Greedy placement with constraints.
    selected = _place_days(pool, unique, num_days)
    return selected


def _assign_relative_difficulty(pool):
    """Rank a pool by continuous hardness and split into 5 equal quintiles ->
    difficulty 1..5. Guarantees a spread even when the pool is fairly common."""
    ranked = sorted(
        pool,
        key=lambda t: (_raw_hardness(t["clen"], t["a_freq"], t["b_freq"],
                                     t["c_freq"]), t["c"]),
    )
    n = len(ranked)
    for rank, t in enumerate(ranked):
        q = min(4, (rank * 5) // n) if n else 0
        t["difficulty"] = q + 1


def _place_days(pool, full_pool, num_days):
    """Fill days 0..num_days-1 greedily.

    Constraints per placement:
      * final word C not already used;
      * neither source word used more than MAX_SOURCE_WORD_USES total;
      * neither source word used within SOURCE_WORD_MIN_GAP days;
      * prefer a candidate whose difficulty matches the weekday target band.
    Constraints are relaxed in a fixed order only if a day cannot otherwise be
    filled, so the buffer is always complete and deterministic.
    """
    if not pool:
        raise RuntimeError("No valid triples were found; cannot build puzzles.")

    # weekday index: 0=Mon .. 6=Sun. Target difficulty band per weekday.
    # Gentle ramp: easy at the start of the week, hardest on the weekend, and
    # spanning the full 1..5 range so every difficulty band gets used.
    weekday_target = {0: 1, 1: 2, 2: 3, 3: 3, 4: 4, 5: 5, 6: 4}

    used_c = set()
    last_use_day = {}          # source word -> last day index it appeared
    use_count = {}             # source word -> total appearances

    # Candidate ordering: pool first (quality/difficulty assigned), then the
    # remainder of full_pool as a fallback so we never run dry. Assign a default
    # difficulty to any fallback candidate not in pool.
    in_pool = set(id(t) for t in pool)
    ordered = list(pool) + [t for t in full_pool if id(t) not in in_pool]
    for t in ordered:
        t.setdefault("difficulty", _difficulty(
            t["clen"], t["a_freq"], t["b_freq"], t["c_freq"]))

    def constraints_ok(t, day, enforce_gap, enforce_cap):
        if t["c"] in used_c:
            return False
        for w in (t["a"], t["b"]):
            if enforce_cap and use_count.get(w, 0) >= MAX_SOURCE_WORD_USES:
                return False
            if enforce_gap and w in last_use_day \
                    and day - last_use_day[w] < SOURCE_WORD_MIN_GAP:
                return False
        return True

    def commit(t, day):
        used_c.add(t["c"])
        for w in (t["a"], t["b"]):
            use_count[w] = use_count.get(w, 0) + 1
            last_use_day[w] = day

    # Day 0 (launch day) deserves a clean, common, satisfying puzzle: both
    # sources len>=3, high freq everywhere, C in the sweet spot. Pick the best.
    def day0_pick():
        # Day 0 must honor its weekday's C-length rule too (2026-07-05 = Sunday
        # -> 8 letters), while still being clean/common/satisfying.
        day0_lens = len_target_for_weekday(ANCHOR_DATE.weekday())
        cands = [
            t for t in ordered
            if len(t["a"]) >= PREFERRED_MIN_SRC_LEN
            and len(t["b"]) >= PREFERRED_MIN_SRC_LEN
            and t["clen"] in day0_lens
            and min(t["a_freq"], t["b_freq"]) >= 0.35
            and t["c_freq"] >= 0.45
        ]
        if not cands:
            return None
        # Best = highest combined freq (very common, instantly satisfying).
        cands.sort(key=lambda t: (-(t["a_freq"] + t["b_freq"] + t["c_freq"]),
                                  t["c"]))
        return cands[0]

    # Pre-select and RESERVE the launch-day (day 0) puzzle up front so no earlier
    # historical day consumes the same triple, its C, or over-uses its sources.
    launch_pick = day0_pick()
    if launch_pick is not None:
        used_c.add(launch_pick["c"])   # reserve C; sources are committed at day 0

    arranged = []
    # Iterate over ACTUAL day indices FIRST_DAY..LAST_DAY (inclusive). Negative
    # days are historical playtest days; date(day) = ANCHOR_DATE + day. The
    # gap/cap bookkeeping keys off these true indices, so it spans negatives.
    for day in range(FIRST_DAY, LAST_DAY + 1):
        allowed_lens = len_target_for_weekday(
            (ANCHOR_DATE + timedelta(days=day)).weekday())
        pick = None

        if day == 0 and launch_pick is not None:  # public launch day
            # C was reserved above; commit its sources now (single placement).
            for w in (launch_pick["a"], launch_pick["b"]):
                use_count[w] = use_count.get(w, 0) + 1
                last_use_day[w] = day
            arranged.append(launch_pick)
            continue

        # C-length is the PRIMARY driver (weekday ramp). Prefer the exact allowed
        # lengths at every constraint level before falling back to any length, so
        # a busy source-word calendar never overrides the weekday rule.
        for lens in (allowed_lens, None):
            for enforce_gap, enforce_cap in ((True, True), (True, False),
                                             (False, True), (False, False)):
                for t in ordered:
                    if lens is not None and t["clen"] not in lens:
                        continue
                    if constraints_ok(t, day, enforce_gap, enforce_cap):
                        pick = t
                        break
                if pick:
                    break
            if pick:
                break

        if pick is None:
            # Last resort: any unused C (ignore source constraints entirely).
            for t in ordered:
                if t["c"] not in used_c:
                    pick = t
                    break
        if pick is None:
            # Truly exhausted unique Cs: reuse best that isn't adjacent.
            for t in ordered:
                if not arranged or arranged[-1]["c"] != t["c"]:
                    pick = t
                    break

        commit(pick, day)
        arranged.append(pick)

    return arranged


def build_puzzles(defs, selected):
    puzzles = []
    for offset, t in enumerate(selected):
        day = FIRST_DAY + offset            # true index; may be negative
        d = ANCHOR_DATE + timedelta(days=day)
        puzzles.append({
            "day": day,
            "date": d.isoformat(),
            "a": {"word": t["a"], "clue": defs[t["a"]]["def"]},
            "b": {"word": t["b"], "clue": defs[t["b"]]["def"]},
            "c": {"word": t["c"], "clue": defs[t["c"]]["def"]},
            "difficulty": t["difficulty"],
        })
    return puzzles


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------
def write_outputs(puzzles):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PUZZLES_JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(puzzles, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    array_json = json.dumps(puzzles, ensure_ascii=False, indent=2)
    with open(PUZZLES_JS_PATH, "w", encoding="utf-8") as fh:
        fh.write("window.PUZZLES = " + array_json + ";\n")
    _write_days_js(puzzles)


def _write_days_js(puzzles):
    """Emit the SvelteKit ES module app/src/lib/game/data/days.js.

    Slimmed to just the fields the game component needs, plus the platform
    contract helpers dayIndexes()/loadDay(idx).
    """
    slim = [
        {
            "day": p["day"],
            "date": p["date"],
            "difficulty": p["difficulty"],
            "a": {"word": p["a"]["word"], "clue": p["a"]["clue"]},
            "b": {"word": p["b"]["word"], "clue": p["b"]["clue"]},
            "c": {"word": p["c"]["word"], "clue": p["c"]["clue"]},
        }
        for p in puzzles
    ]
    body = json.dumps(slim, ensure_ascii=False, indent=2)
    out = (
        "// AUTO-GENERATED by scripts/gen_puzzles.py -- do not edit by hand.\n"
        "// One entry per day: { day, date, difficulty, a:{word,clue}, "
        "b:{word,clue}, c:{word,clue} }.\n"
        "// sorted(a.word + b.word) === sorted(c.word); answers are never "
        "cognate/same-root.\n\n"
        "export const DAYS = " + body + ";\n\n"
        "const BY_DAY = new Map(DAYS.map((d) => [d.day, d]));\n\n"
        "// Platform contract: which day indexes exist, and how to load one.\n"
        "export function dayIndexes() {\n  return DAYS.map((d) => d.day);\n}\n\n"
        "export function loadDay(idx) {\n  return BY_DAY.get(idx) || null;\n}\n"
    )
    days_dir = os.path.dirname(DAYS_JS_PATH)
    if os.path.isdir(days_dir):
        with open(DAYS_JS_PATH, "w", encoding="utf-8") as fh:
            fh.write(out)


def main():
    defs, source = load_words_defs()
    print(f"[gen] data source: {source}")
    print(f"[gen] usable words: {len(defs)}")

    groups = build_index(defs)
    print(f"[gen] anagram signatures: {len(groups)}")

    triples = find_splits(defs, groups)
    print(f"[gen] valid A+B==C triples found: {len(triples)}")

    unique_c = len({t['c'] for t in triples})
    print(f"[gen] unique final (C) words: {unique_c}")

    if not triples:
        print("[gen] ERROR: no valid triples; aborting.", file=sys.stderr)
        return 1

    selected = curate(triples, NUM_DAYS)
    puzzles = build_puzzles(defs, selected)
    write_outputs(puzzles)
    print(f"[gen] wrote {len(puzzles)} days -> {PUZZLES_JSON_PATH}")
    print(f"[gen] wrote {len(puzzles)} days -> {PUZZLES_JS_PATH}")
    print(f"[gen] day {puzzles[0]['day']} = {puzzles[0]['date']} .. "
          f"day {puzzles[-1]['day']} = {puzzles[-1]['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
