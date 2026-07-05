# Anagram Daily — Shared Build Contract

This is the single source of truth for all four workstreams. Every agent MUST
conform to the schemas, file paths, and rules below so the pieces snap together.

## The game (mechanic)

Each day shows **two clues** → player solves them into **two source words**
(`A`, `B`). The combined letters of A and B are an **anagram of a third word**
(`C`, the final answer), which also has its own clue. A free **shuffle** button
rearranges the pooled letters to help spot the anagram.

Hard invariant (must ALWAYS hold): `sorted(A + B) == sorted(C)` (multiset of
letters is identical; A and B together use exactly the letters of C).

Example: A=`MOON`, B=`STARER`, C=`ASTRONOMER`.

## Word / length rules

- All words are UPPERCASE `A–Z` only. No spaces, hyphens, digits, or accents.
- `len(C) >= 8`  (final word is at least 8 letters)
- `len(A) >= 2` and `len(B) >= 2`  (each source word at least 2 letters)
- Therefore `len(A) + len(B) == len(C)`, and each source word ≤ `len(C) - 2`.
- All three words must have a plain (dictionary / NYT-style) definition.

## Scoring (final, agreed)

Each day starts at **20.00 points**. Floor at **0** (never negative). Shuffle is free.

| Action | Cost |
|---|---|
| Shuffle the letter pool | **Free** |
| Check a source word you typed (A or B) — tells you if it's right | **−0.5** each check |
| Reveal ONE letter of a source word (A/B) | **−1** each |
| Reveal an ENTIRE source word (A/B) | **−4 flat** (caps that word's total hint cost at 4 — see note) |
| Reveal ONE letter of the final word (C) | **−1.5** each |
| Wrong guess on the final word (C) | **−1** each |
| Give up / reveal the final word | day score → **0** |

Notes:
- "Reveal entire source word" caps that word's cumulative hint cost at 4: if the
  player already paid `L` in per-letter reveals on that word, revealing the rest
  costs `max(0, 4 - L)`. You never pay more than 4 to fully know one source word.
- Score is tracked to 1 decimal (0.5 increments possible).
- Final displayed score = `max(0, round(score, 1))`.

## Files & schemas

Repo layout (static site, NO build step; GitHub Pages served from repo root):

```
anagram-daily/
  index.html          # Agent 4 — self-contained UI (loads scoring.js + data/puzzles.js)
  scoring.js          # Agent 3 — pure scoring/stats/share module (global `AnagramScoring`)
  data/
    words_defs.json   # Agent 1 — word → {def, freq}
    puzzles.js        # Agent 2 — `window.PUZZLES = [...]` (what the UI loads)
    puzzles.json      # Agent 2 — canonical JSON (same content as puzzles.js)
  scripts/
    build_words.py    # Agent 1 — sources + cleans the dictionary
    gen_puzzles.py    # Agent 2 — anagram engine + daily puzzle generator
    verify_puzzles.py # Agent 2 — invariant gate
  README.md
  .nojekyll
```

### `data/words_defs.json` (Agent 1 → Agent 2)
Object keyed by UPPERCASE word:
```json
{
  "MOON":       { "def": "Earth's natural satellite",        "freq": 0.91 },
  "STARER":     { "def": "One who gazes fixedly",            "freq": 0.42 },
  "ASTRONOMER": { "def": "A scientist who studies the stars","freq": 0.78 }
}
```
- `def`: one concise plain-English definition (string, ≤ ~120 chars, no leading
  article requirement but keep it clean; strip HTML/markup).
- `freq`: normalized commonness in `[0,1]`, 1 = very common, 0 = rare. Use a real
  frequency list (e.g. wordfreq / SUBTLEX / Google Books). Used for difficulty +
  filtering out obscure words.
- Only keep words that are `A–Z`, length 2..15, with a usable definition.

### `data/puzzles.js` + `data/puzzles.json` (Agent 2 → Agent 4)
`puzzles.js` is exactly: `window.PUZZLES = <the JSON array below>;`
```json
[
  {
    "day": 0,
    "date": "2026-07-05",
    "a": { "word": "MOON",   "clue": "Earth's natural satellite" },
    "b": { "word": "STARER", "clue": "One who gazes fixedly" },
    "c": { "word": "ASTRONOMER", "clue": "A scientist who studies the stars" },
    "difficulty": 3
  }
]
```
- `day`: integer index; **day 0 = 2026-07-05** (anchor). One entry per day,
  contiguous from day 0 upward. Generate a buffer of at least days `0..120`.
- `date`: `YYYY-MM-DD` (local), informational.
- `clue` fields copy the definitions from `words_defs.json`.
- `difficulty`: integer 1..5 (1 easiest), derived from word rarity + C length.
  Ramp gently across the week if you like, but keep every day solvable.
- Invariant enforced by `verify_puzzles.py`: for every entry,
  `sorted(a.word+b.word)==sorted(c.word)`, all length rules hold, all three
  words exist in `words_defs.json`.

### `scoring.js` (Agent 3 → Agent 4)
Expose a global `window.AnagramScoring` with a clean, framework-free API, e.g.:
```js
const game = AnagramScoring.create({ dayIndex, puzzle });   // puzzle = a PUZZLES entry
game.state()            // -> { score, maxScore:20, finished, revealed:{a,b,c}, guesses, checks }
game.shuffle()          // free (may be a no-op in scoring; UI owns letter order)
game.checkSource('a', typedWord)   // -> { correct:bool, score }         (−0.5)
game.revealSourceLetter('a')       // -> { letter, index, score }         (−1)
game.revealSourceWord('a')         // -> { word, score }                  (−4 cap)
game.revealFinalLetter()           // -> { letter, index, score }         (−1.5)
game.guessFinal(typedWord)         // -> { correct, score, finished }     (−1 if wrong)
game.giveUp()                      // -> { score:0, finished:true }
game.shareText()        // -> "Anagram Daily #<idx> — <score>/20 ..." (+ emoji summary)
```
- Persist per day to `localStorage` key **`anagram_day<N>`** as:
  `{ started, finished, score, maxScore:20, revealed, guesses, checks, live, result:{ score, max:20 } }`
  (this shape lets the games hub read status + score, mirroring the other games).
- Enforce ALL scoring rules and the floor-at-0 here. The UI must not compute costs
  itself — it calls these methods and renders `state()`.

## House style (Agent 4)

- Neobrutalism matching the games hub: **warm light default + dark toggle** under
  its own localStorage key (use `games_theme` to stay consistent with the hub),
  fonts **Inter + JetBrains Mono**, accent **`#fdc800`**, bold borders, hard
  offset shadows.
- Self-contained: no CDN, no external fonts (inline or system fallback), works
  offline and from `file://` (that's why puzzles ship as `puzzles.js`, not fetch).
- Include a single hub link in the header: `<a>◂ All games</a>` →
  `https://imangulova.github.io/games/`.
- Layout: two clue cards (each with crossword-style letter boxes for input), a
  shared shuffle-able **letter pool**, a **final answer** entry, hint buttons
  wired to `AnagramScoring`, live score, end screen with **share** + "next puzzle
  in" countdown, and a **calendar archive** of past days.
- English UI (this game is meant to show friends).

## Day-index math (shared by UI + hub)
- Anchor day 0 = local midnight of **2026-07-05**.
- `dayIndex = floor((localMidnightToday - anchor) / 86400000)` — compute via local
  date parts (DST-safe), same approach as Train Tracks / Battleships.

## Guardrails
- Assistant does LOCAL git only; **the user pushes**. No tokens in chat.
- No external hosting services; static site only.
