#!/usr/bin/env python3
"""
Anagram Daily -- mandatory invariant gate (Agent 2).

Loads the generated puzzles (data/puzzles.json) and the word dictionary
(data/words_defs.json OR the embedded starter set via gen_puzzles) and asserts,
for EVERY entry:

  1. Multiset invariant:  sorted(a.word + b.word) == sorted(c.word)
  2. Length rules:        len(c) >= 8, len(a) >= 2, len(b) >= 2,
                          len(a) + len(b) == len(c)
  3. All words are UPPERCASE A-Z only.
  4. Contiguous day indices starting at day 0 (0,1,2,...).
  5. Dates are contiguous from the anchor 2026-07-05.
  6. clue fields are non-empty and match the dictionary definitions.
  7. All three words exist in words_defs.json (the effective dictionary).
  8. `accept` lists every valid full anagram of C: contains C, all entries are
     UPPERCASE A-Z words in the dictionary whose letters match C exactly, and
     nothing is missing (matches the dictionary's anagram group for C).

Exits nonzero on ANY failure with a clear message.
"""

import json
import os
import sys
from datetime import date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(ROOT, "data")
PUZZLES_JSON_PATH = os.path.join(DATA_DIR, "puzzles.json")
WORDS_DEFS_PATH = os.path.join(DATA_DIR, "words_defs.json")
PUZZLES_JS_PATH = os.path.join(DATA_DIR, "puzzles.js")

ANCHOR_DATE = date(2026, 7, 5)
MIN_C_LEN = 8
MIN_PART_LEN = 2

# The buffer's first day index is owned by gen_puzzles (FIRST_DAY). It may be
# negative (historical playtest days before the launch anchor). Import it so the
# contiguity check tracks the generator; fall back to reading the first entry.
try:
    sys.path.insert(0, SCRIPT_DIR)
    from gen_puzzles import FIRST_DAY as GEN_FIRST_DAY  # noqa: E402
except Exception:
    GEN_FIRST_DAY = None

# Same-root / cognate gate: answers (A, B, C) must be etymologically unrelated.
try:
    sys.path.insert(0, SCRIPT_DIR)
    from gen_puzzles import are_cognate as _are_cognate  # noqa: E402
except Exception:
    _are_cognate = None


def _load_effective_defs():
    """Load words_defs.json if present, else the embedded starter dictionary
    from gen_puzzles (so verification works even in bootstrap mode)."""
    if os.path.exists(WORDS_DEFS_PATH):
        with open(WORDS_DEFS_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        # normalize keys to uppercase
        return {k.strip().upper(): v for k, v in raw.items()}, \
            "data/words_defs.json"
    # bootstrap: reuse gen_puzzles' starter set
    sys.path.insert(0, SCRIPT_DIR)
    import gen_puzzles  # noqa: E402
    return gen_puzzles.build_starter_defs(), "embedded STARTER (bootstrap)"


def fail(msg):
    print(f"[verify] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    if not os.path.exists(PUZZLES_JSON_PATH):
        fail(f"missing {PUZZLES_JSON_PATH} -- run gen_puzzles.py first")

    with open(PUZZLES_JSON_PATH, "r", encoding="utf-8") as fh:
        puzzles = json.load(fh)

    if not isinstance(puzzles, list) or not puzzles:
        fail("puzzles.json is not a non-empty JSON array")

    defs, defs_source = _load_effective_defs()
    print(f"[verify] dictionary source: {defs_source} ({len(defs)} words)")
    print(f"[verify] loaded {len(puzzles)} puzzle entries")

    # Anagram index: signature -> set of dictionary words. Lets us confirm each
    # entry's `accept` list is exactly the full anagram group for its C word.
    sig_index = {}
    for w in defs:
        sig_index.setdefault("".join(sorted(w)), set()).add(w)

    non_unique = 0

    # ---- puzzles.js consistency -------------------------------------------
    if os.path.exists(PUZZLES_JS_PATH):
        with open(PUZZLES_JS_PATH, "r", encoding="utf-8") as fh:
            js = fh.read().strip()
        prefix = "window.PUZZLES = "
        if not js.startswith(prefix) or not js.endswith(";"):
            fail("puzzles.js must be exactly 'window.PUZZLES = <array>;'")
        try:
            js_array = json.loads(js[len(prefix):-1])
        except json.JSONDecodeError as exc:
            fail(f"puzzles.js payload is not valid JSON: {exc}")
        if js_array != puzzles:
            fail("puzzles.js content does not match puzzles.json")
        print("[verify] puzzles.js matches puzzles.json OK")
    else:
        fail(f"missing {PUZZLES_JS_PATH}")

    diff_hist = {d: 0 for d in range(1, 6)}

    # Determine the expected first day index. Prefer gen_puzzles.FIRST_DAY;
    # otherwise trust (and validate) the first entry's own 'day'. Negative
    # first days (historical playtest days) are allowed.
    first_entry_day = puzzles[0].get("day")
    if not isinstance(first_entry_day, int):
        fail("first entry has a non-integer 'day'")
    first_day = GEN_FIRST_DAY if GEN_FIRST_DAY is not None else first_entry_day
    if GEN_FIRST_DAY is not None and first_entry_day != GEN_FIRST_DAY:
        fail(f"first entry day {first_entry_day} != gen_puzzles.FIRST_DAY "
             f"{GEN_FIRST_DAY}")
    print(f"[verify] expected first day index: {first_day}")

    for i, p in enumerate(puzzles):
        ctx = f"entry index {i}"

        # ---- schema / day index -------------------------------------------
        for field in ("day", "date", "a", "b", "c", "accept", "difficulty"):
            if field not in p:
                fail(f"{ctx}: missing field '{field}'")
        expected_day = first_day + i
        if p["day"] != expected_day:
            fail(f"{ctx}: day index is {p['day']}, expected {expected_day} "
                 f"(must be contiguous from {first_day})")

        # date must equal anchor + dayIndex (correct for negative days too).
        expected_date = (ANCHOR_DATE + timedelta(days=expected_day)).isoformat()
        if p["date"] != expected_date:
            fail(f"{ctx}: date is {p['date']}, expected {expected_date}")

        if p["difficulty"] not in (1, 2, 3, 4, 5):
            fail(f"{ctx}: difficulty {p['difficulty']} not in 1..5")
        diff_hist[p["difficulty"]] += 1

        a_word = p["a"]["word"]
        b_word = p["b"]["word"]
        c_word = p["c"]["word"]

        # ---- uppercase A-Z only -------------------------------------------
        for label, w in (("a", a_word), ("b", b_word), ("c", c_word)):
            if not isinstance(w, str) or not w.isalpha() or not w.isascii() \
                    or w.upper() != w:
                fail(f"{ctx}: {label}.word '{w}' is not UPPERCASE A-Z")

        # ---- length rules -------------------------------------------------
        if len(c_word) < MIN_C_LEN:
            fail(f"{ctx}: len(C)={len(c_word)} < {MIN_C_LEN} (C='{c_word}')")
        if len(a_word) < MIN_PART_LEN:
            fail(f"{ctx}: len(A)={len(a_word)} < {MIN_PART_LEN} (A='{a_word}')")
        if len(b_word) < MIN_PART_LEN:
            fail(f"{ctx}: len(B)={len(b_word)} < {MIN_PART_LEN} (B='{b_word}')")
        if len(a_word) + len(b_word) != len(c_word):
            fail(f"{ctx}: len(A)+len(B)={len(a_word) + len(b_word)} != "
                 f"len(C)={len(c_word)}")

        # ---- MULTISET INVARIANT (the core rule) ---------------------------
        if sorted(a_word + b_word) != sorted(c_word):
            fail(f"{ctx}: multiset invariant broken: "
                 f"sorted('{a_word}'+'{b_word}') != sorted('{c_word}')")

        # ---- answers must NOT be cognate / share a root -------------------
        if _are_cognate is not None:
            for x, y, lbl in ((a_word, b_word, "A/B"),
                              (a_word, c_word, "A/C"),
                              (b_word, c_word, "B/C")):
                if _are_cognate(x, y):
                    fail(f"{ctx}: {lbl} answers '{x}' & '{y}' are cognate / "
                         f"share a root (answers must be unrelated words)")

        # ---- neither source may be a SUBSTRING of the final word ----------
        if a_word.upper() in c_word.upper():
            fail(f"{ctx}: source A '{a_word}' is a substring of C '{c_word}'")
        if b_word.upper() in c_word.upper():
            fail(f"{ctx}: source B '{b_word}' is a substring of C '{c_word}'")

        # ---- words exist in dictionary ------------------------------------
        for label, w in (("a", a_word), ("b", b_word), ("c", c_word)):
            if w not in defs:
                fail(f"{ctx}: {label}.word '{w}' not found in dictionary")

        # ---- accept list: solution-uniqueness contract --------------------
        accept = p["accept"]
        if not isinstance(accept, list) or not accept:
            fail(f"{ctx}: 'accept' must be a non-empty list")
        for w in accept:
            if not isinstance(w, str) or not w.isalpha() or not w.isascii() \
                    or w.upper() != w:
                fail(f"{ctx}: accept entry '{w}' is not UPPERCASE A-Z")
            if sorted(w) != sorted(c_word):
                fail(f"{ctx}: accept entry '{w}' is not an anagram of C "
                     f"'{c_word}'")
            if w not in defs:
                fail(f"{ctx}: accept entry '{w}' not found in dictionary")
        if c_word not in accept:
            fail(f"{ctx}: accept list must contain C '{c_word}'")
        if len(accept) != len(set(accept)):
            fail(f"{ctx}: accept list has duplicates: {accept}")
        # `accept` must be the COMPLETE anagram group for C (no valid word the
        # pooled letters spell may be left uncredited).
        expected_accept = sig_index.get("".join(sorted(c_word)), set())
        if set(accept) != expected_accept:
            missing = sorted(expected_accept - set(accept))
            extra = sorted(set(accept) - expected_accept)
            fail(f"{ctx}: accept list != full anagram group for '{c_word}' "
                 f"(missing={missing}, extra={extra})")
        if len(accept) > 1:
            non_unique += 1

        # ---- clues non-empty & match definitions --------------------------
        for label, w in (("a", a_word), ("b", b_word), ("c", c_word)):
            clue = p[label].get("clue")
            if not isinstance(clue, str) or not clue.strip():
                fail(f"{ctx}: {label}.clue is empty")
            expected_def = str(defs[w].get("def", "")).strip()
            if clue.strip() != expected_def:
                fail(f"{ctx}: {label}.clue does not match dictionary def "
                     f"for '{w}'")

    # ---- final summary -----------------------------------------------------
    print("[verify] ALL CHECKS PASSED")
    print(f"[verify] days: {puzzles[0]['day']}..{puzzles[-1]['day']} "
          f"({puzzles[0]['date']} .. {puzzles[-1]['date']})")
    print(f"[verify] difficulty histogram: {diff_hist}")
    print(f"[verify] non-unique solutions (accept > 1): {non_unique}/"
          f"{len(puzzles)} (each credits any listed anagram)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
