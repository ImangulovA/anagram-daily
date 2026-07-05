#!/usr/bin/env python3
"""
build_words.py — Agent 1 deliverable for "Anagram Daily".

Produces data/words_defs.json: an object keyed by UPPERCASE word ->
{ "def": <concise plain-English definition>, "freq": <float 0..1> }.

Sourcing method (single combo gives words + definitions + frequency):
  * WORDS + DEFINITIONS: NLTK WordNet lemmas and their synset glosses.
  * FREQUENCY:           the `wordfreq` package (Zipf scale, English), which is
                         built on real corpora (SUBTLEX / OpenSubtitles / Wikipedia
                         / news / etc.). Zipf is a log10 scale roughly in [0, 8]:
                         ~1 = extremely rare, ~7+ = extremely common ("the").
                         We normalize Zipf -> [0,1] with a linear map over a
                         sensible window so 1.0 = very common, 0.0 = rare.

Frequency normalization (documented):
  freq = clamp((zipf - ZIPF_MIN) / (ZIPF_MAX - ZIPF_MIN), 0, 1)
  with ZIPF_MIN = 1.5 and ZIPF_MAX = 7.0. Words below MIN_ZIPF_KEEP are dropped
  as "obscure junk" so the pool stays high quality (still tens of thousands).

This gives a REAL, corpus-derived frequency (not a rank proxy). If wordfreq is
unavailable at runtime the script raises with a clear message rather than
silently shipping fake numbers.

Sense selection (which definition to show as the clue):
  Definitions are the crux of the game (each word is presented ONLY by its
  clue), so we must pick the sense a normal person means by the word, not an
  obscure noun sense of a common function word.
  Strategy:
    1. Use WordNet's own per-sense corpus frequency: for each synset we take
       lemma.count() of the lemma matching this word. Higher = more common
       sense. WordNet also roughly orders synsets by frequency, so we tie-break
       on the synset's natural index (lower = more common).
    2. We do NOT force noun-first and do NOT prefer the shortest gloss (that old
       heuristic biased toward obscure noun senses of common words, e.g.
       IN -> "a unit of length ... one twelfth of a foot").
    3. Measurement-unit guard: for short/common words (len <= 3 OR high freq),
       if the top-ranked sense is a "unit of measurement" gloss (e.g. the 'are'
       = 100 m^2 unit, or IN = inch), we demote all measurement-unit glosses and
       fall back to a normal sense. If EVERY sense is a measurement unit we keep
       it (that really is what the word means, e.g. LITER).

Re-runnable / idempotent: overwrites data/words_defs.json each run; output is
deterministic (sorted keys).

Usage:
  python build_words.py            # writes ../data/words_defs.json
  python build_words.py --verify   # also load back + print stats/histogram

Run inside the project venv so nltk + wordfreq are importable:
  .venv/bin/python scripts/build_words.py --verify
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MIN_LEN = 2
MAX_LEN = 15

# Frequency normalization window (Zipf scale from wordfreq).
ZIPF_MIN = 1.5   # maps to freq 0.0
ZIPF_MAX = 7.0   # maps to freq 1.0
# Drop words rarer than this Zipf (keeps obscure junk out; keeps pool large).
MIN_ZIPF_KEEP = 2.3

MAX_DEF_LEN = 120  # soft cap on definition length

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.normpath(os.path.join(HERE, "..", "data", "words_defs.json"))

# A–Z only, no spaces / hyphens / digits / accents.
AZ_RE = re.compile(r"^[A-Za-z]+$")

# Words this short (or this common) get the measurement-unit guard applied: a
# top sense that is a "unit of measurement" gloss is demoted in favour of a
# normal everyday sense (fixes IN, ARE, etc.).
MEASUREMENT_GUARD_MAX_LEN = 3
MEASUREMENT_GUARD_MIN_FREQ = 0.55

# Detects glosses that define a word as a unit of measurement (length, area,
# mass, time, etc.). Matched against the RAW WordNet gloss.
MEASUREMENT_RE = re.compile(
    r"\b(a|an|the)?\s*unit of\s+"
    r"(measurement|length|area|surface area|mass|weight|volume|capacity|"
    r"time|force|power|energy|pressure|frequency|electric|magnetic|"
    r"luminous|radioactivity|angle|information|data|count|absorbed)",
    re.IGNORECASE,
)

# Offensive slurs / clearly inappropriate terms to exclude from a game meant to
# be shown to friends. Kept small and explicit; matched case-insensitively.
BLOCKLIST = {
    "nigger", "nigga", "faggot", "fag", "spic", "chink", "kike", "wop",
    "gook", "coon", "retard", "retarded", "cunt", "twat", "wetback",
    "tranny", "dyke", "raghead", "negro", "negroid", "mongoloid", "cripple",
    "jap", "paki", "gyp", "gypped",
}


# ---------------------------------------------------------------------------
# Definition cleaning
# ---------------------------------------------------------------------------

def clean_definition(raw: str) -> str:
    """Turn a WordNet gloss into a concise, clean plain-English definition.

    WordNet glosses look like:
      "(usually followed by `to') having the necessary means or skill"
      "the star that is the source of light and heat for the planets; ..."
    We drop leading parenthetical usage notes, cut example clauses (after ';'
    or quoted examples), strip markup, collapse whitespace, and truncate.
    """
    if not raw:
        return ""
    text = raw.strip()

    # Drop a leading parenthetical usage note like "(usually ...)".
    text = re.sub(r"^\([^)]*\)\s*", "", text)
    # Remove any remaining parentheticals.
    text = re.sub(r"\([^)]*\)", "", text)

    # WordNet separates the definition from usage examples with ';'. Keep the
    # first clause (the actual definition).
    text = text.split(";")[0]

    # Strip stray backticks / quotes used by WordNet for cited forms.
    text = text.replace("`", "").replace("''", "").replace('"', "")

    # Strip any residual HTML/markup, just in case.
    text = re.sub(r"<[^>]+>", "", text)

    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate cleanly at a word boundary near MAX_DEF_LEN.
    if len(text) > MAX_DEF_LEN:
        cut = text[:MAX_DEF_LEN]
        # back off to last space so we don't chop a word
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip(",;:. ") + "…"

    return text.strip()


def is_measurement_gloss(raw_def: str) -> bool:
    """True if the raw WordNet gloss defines the word as a unit of measurement."""
    return bool(MEASUREMENT_RE.search(raw_def or ""))


def pick_best_synset(entries, apply_measurement_guard: bool):
    """Choose the most clue-friendly sense for a word.

    `entries` is a list of (synset, sense_count) pairs, where sense_count is
    lemma.count() for the lemma of THIS word in that synset (WordNet's per-sense
    corpus frequency; higher = more common sense).

    Selection:
      * Rank by (sense_count desc, natural WordNet order asc). WordNet lists
        senses roughly most-common-first, so a low index is a good tie-break.
      * Measurement-unit guard (short/common words only): demote every sense
        whose gloss defines the word as a unit of measurement, unless ALL senses
        are measurement units.

    Returns (synset, cleaned_def) or None if no usable definition exists.
    """
    # Build candidate list of (count, order_index, is_measure, synset, cleaned).
    candidates = []
    for order_index, (syn, count) in enumerate(entries):
        cleaned = clean_definition(syn.definition())
        if not cleaned:
            continue
        candidates.append((
            count,
            order_index,
            is_measurement_gloss(syn.definition()),
            syn,
            cleaned,
        ))
    if not candidates:
        return None

    # Measurement guard: if we should apply it and at least one non-measurement
    # sense exists, restrict to non-measurement senses. If it removes EVERYTHING
    # (the only exact-match senses are measurement units, e.g. ARE whose verb
    # senses live under the lemma 'be'), signal no acceptable sense so the caller
    # can try a Morphy fallback.
    if apply_measurement_guard:
        non_measure = [c for c in candidates if not c[2]]
        if non_measure:
            candidates = non_measure
        else:
            return None

    # Higher count first; then earlier WordNet order (more common) first.
    candidates.sort(key=lambda c: (-c[0], c[1]))
    _count, _idx, _is_measure, syn, cleaned = candidates[0]
    return (syn, cleaned)


def pick_via_morphy(word_lower: str, wn):
    """Fallback for inflected function words (ARE, WERE, AM, ...): exact-lemma
    matching only found a rare/measurement noun sense. Look at ALL synsets for
    the word (WordNet resolves inflections via Morphy), skip measurement glosses,
    and take the earliest (most common) usable non-measurement sense.
    """
    for syn in wn.synsets(word_lower):
        if is_measurement_gloss(syn.definition()):
            continue
        cleaned = clean_definition(syn.definition())
        if cleaned:
            return (syn, cleaned)
    return None


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------

def normalize_zipf(zipf: float) -> float:
    if zipf <= 0:
        return 0.0
    val = (zipf - ZIPF_MIN) / (ZIPF_MAX - ZIPF_MIN)
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return round(val, 4)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build() -> dict:
    try:
        from nltk.corpus import wordnet as wn
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            "nltk / WordNet is required. Install with `pip install nltk` and run "
            "`python -c \"import nltk; nltk.download('wordnet')\"`.\n"
            f"Import error: {exc}"
        )

    try:
        from wordfreq import zipf_frequency
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            "wordfreq is required for REAL frequency data. Install with "
            "`pip install wordfreq`.\n"
            f"Import error: {exc}"
        )

    # Make sure WordNet is actually available (triggers a clear error if not
    # downloaded, instead of a lazy failure deep in the loop).
    try:
        wn.ensure_loaded()
    except LookupError:
        raise SystemExit(
            "WordNet data not found. Run: "
            "python -c \"import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')\""
        )

    # 1) Gather candidate lemmas grouped by uppercase surface form.
    #    WordNet stores proper nouns capitalized; we drop any lemma whose stored
    #    form has an uppercase letter (e.g. 'London', 'NASA') to exclude proper
    #    nouns and acronyms. We keep only A-Z, length-bounded, single-token forms.
    #    We also record a per-sense corpus frequency so the picker can prefer the
    #    sense people actually mean (see pick_best_synset). For that count we take
    #    the MAX lemma.count() across all case-variants of the word in the synset
    #    (e.g. 'Moon' the capitalized lemma carries the high count for "the
    #    natural satellite of the Earth" even though we exclude it as a surface
    #    form). Inclusion of the WORD itself still requires a lowercase surface
    #    form, so proper nouns / acronyms are still filtered out.
    candidates: dict[str, list] = {}
    for syn in wn.all_synsets():
        # Does this synset contain a valid lowercase surface form of some word?
        # Group counts by uppercase key across all matching lemmas.
        lc_forms: dict[str, bool] = {}
        counts: dict[str, int] = {}
        for lemma in syn.lemmas():
            name = lemma.name()
            if "_" in name or "-" in name:
                continue          # multi-word / hyphenated
            if not AZ_RE.match(name):
                continue          # digits / accents / punctuation
            if not (MIN_LEN <= len(name) <= MAX_LEN):
                continue
            if name.lower() in BLOCKLIST:
                continue
            key = name.upper()
            counts[key] = max(counts.get(key, 0), lemma.count())
            if name == name.lower():
                lc_forms[key] = True   # this word has a lowercase (non-proper) form
        for key, has_lc in lc_forms.items():
            if not has_lc:
                continue          # only proper-noun / acronym forms -> skip word
            candidates.setdefault(key, []).append((syn, counts[key]))

    # 2) For each candidate pick a definition, compute frequency, apply filters.
    out: dict[str, dict] = {}
    dropped_nodef = 0
    dropped_rare = 0
    for word, entries in candidates.items():
        zipf = zipf_frequency(word.lower(), "en")
        if zipf < MIN_ZIPF_KEEP:
            dropped_rare += 1
            continue
        freq = normalize_zipf(zipf)

        # Apply the measurement-unit guard for short OR common words: these are
        # the ones whose "unit of measurement" noun sense is almost never what
        # the player means (IN, ARE, ...). Longer/rarer measurement words like
        # LITER keep their unit definition because no other sense outranks it.
        apply_guard = (
            len(word) <= MEASUREMENT_GUARD_MAX_LEN
            or freq >= MEASUREMENT_GUARD_MIN_FREQ
        )
        best = pick_best_synset(entries, apply_guard)
        if best is None and apply_guard:
            # Guard removed every exact-match sense (only measurement/rare noun
            # senses matched, e.g. ARE). Try the Morphy fallback.
            best = pick_via_morphy(word.lower(), wn)
        if best is None:
            dropped_nodef += 1
            continue
        _syn, definition = best

        out[word] = {"def": definition, "freq": freq}

    print(
        f"[build] candidates={len(candidates)} kept={len(out)} "
        f"dropped_no_def={dropped_nodef} dropped_rare(<{MIN_ZIPF_KEEP} zipf)={dropped_rare}",
        file=sys.stderr,
    )
    return out


def write_json(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Sorted keys => deterministic / idempotent output.
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=True, sort_keys=True, indent=0,
                  separators=(",", ":"))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    total = len(data)
    with_freq = sum(1 for v in data.values() if isinstance(v.get("freq"), (int, float)))
    nonzero_freq = sum(1 for v in data.values() if v.get("freq", 0) > 0)

    lengths = Counter(len(w) for w in data)

    print("\n===== VERIFY words_defs.json =====")
    print(f"path:            {path}")
    print(f"total words:     {total}")
    print(f"with freq field: {with_freq}")
    print(f"freq > 0:        {nonzero_freq}")

    print("\nlength histogram (word_len: count):")
    for length in sorted(lengths):
        bar = "#" * min(60, lengths[length] // 100 + 1)
        print(f"  {length:2d}: {lengths[length]:6d}  {bar}")

    # sanity checks on schema
    bad = []
    for w, v in data.items():
        if not re.match(r"^[A-Z]+$", w):
            bad.append((w, "non-AZ key"))
        elif not (MIN_LEN <= len(w) <= MAX_LEN):
            bad.append((w, "length out of range"))
        elif not isinstance(v.get("def"), str) or not v["def"]:
            bad.append((w, "bad def"))
        elif not isinstance(v.get("freq"), (int, float)):
            bad.append((w, "bad freq"))
        elif not (0.0 <= v["freq"] <= 1.0):
            bad.append((w, "freq out of [0,1]"))
        if len(bad) >= 5:
            break
    if bad:
        print("\nSCHEMA WARNINGS (first few):")
        for w, why in bad:
            print(f"  {w}: {why}")
    else:
        print("\nschema check: OK (A-Z keys, len 2..15, def present, freq in [0,1])")

    # 5 sample entries: pick a spread across the frequency range.
    ordered = sorted(data.items(), key=lambda kv: kv[1]["freq"], reverse=True)
    if ordered:
        picks = [
            ordered[0],
            ordered[len(ordered) // 4],
            ordered[len(ordered) // 2],
            ordered[3 * len(ordered) // 4],
            ordered[-1],
        ]
        print("\n5 sample entries (high -> low freq):")
        for w, v in picks:
            print(f"  {w}  freq={v['freq']}  def={v['def']!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build words_defs.json for Anagram Daily.")
    ap.add_argument("--verify", action="store_true",
                    help="load the written JSON back and print stats/histogram/samples")
    ap.add_argument("--out", default=OUT_PATH, help="output path (default: ../data/words_defs.json)")
    args = ap.parse_args()

    data = build()
    write_json(data, args.out)
    print(f"[build] wrote {len(data)} words -> {args.out}", file=sys.stderr)

    if args.verify:
        verify(args.out)


if __name__ == "__main__":
    main()
