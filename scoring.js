/*
 * Anagram Daily — scoring / stats / share module (Agent 3)
 *
 * Pure, framework-free. Exposes a global `window.AnagramScoring` in the browser
 * and `module.exports` under Node (for tests). No external dependencies.
 *
 * The UI must NOT compute any costs. It calls these methods and renders state().
 *
 * Scoring (from CONTRACT.md — final, agreed):
 *   - Start 20.00 each day. Floor at 0 (never negative). Shuffle is free.
 *   - Check a source word (A/B): -0.5 each check.
 *   - Reveal ONE letter of a source word (A/B): -1 each.
 *   - Reveal ENTIRE source word (A/B): -4 flat, capping that word's cumulative
 *     hint cost at 4 (max(0, 4 - L) if L already paid in per-letter reveals).
 *   - Reveal ONE letter of the final word C: -1.5 each.
 *   - Wrong guess on the final word C: -1 each.
 *   - Give up / reveal final word: day score -> 0, finished.
 *   - A correct final guess finishes the day and locks the score.
 *   - Score tracked to 1 decimal. Displayed score = max(0, round(score, 1)).
 */
(function (root) {
  'use strict';

  // ---- Constants ------------------------------------------------------------
  var MAX_SCORE = 20;
  var COST_CHECK = 0.5;
  var COST_SOURCE_LETTER = 1;
  var COST_SOURCE_WORD_CAP = 4;
  var COST_FINAL_LETTER = 1.5;
  var COST_WRONG_FINAL = 1;
  var COST_FINAL_CLUE = 4; // reveal the final word's clue/definition (once)
  var KEY_PREFIX = 'anagram_day';

  // ---- Small helpers --------------------------------------------------------

  // Round to 1 decimal, avoiding binary-float artifacts (e.g. 19.5 - 1.5).
  function round1(n) {
    return Math.round(n * 10) / 10;
  }

  function displayScore(n) {
    return Math.max(0, round1(n));
  }

  function normWord(s) {
    return String(s == null ? '' : s)
      .toUpperCase()
      .replace(/[^A-Z]/g, '');
  }

  // Best-effort localStorage handle (Node/tests may not have one).
  function getStore(explicit) {
    if (explicit) return explicit;
    try {
      if (typeof root !== 'undefined' && root.localStorage) return root.localStorage;
    } catch (e) {
      /* access can throw in locked-down environments */
    }
    try {
      if (typeof localStorage !== 'undefined') return localStorage;
    } catch (e2) {
      /* ignore */
    }
    return null;
  }

  function safeParse(raw) {
    if (!raw) return null;
    try {
      var o = JSON.parse(raw);
      return o && typeof o === 'object' ? o : null;
    } catch (e) {
      return null;
    }
  }

  // ---- Core game object -----------------------------------------------------

  function create(opts) {
    opts = opts || {};
    var dayIndex = opts.dayIndex | 0;
    var puzzle = opts.puzzle || {};
    var store = getStore(opts.storage);

    // Answer words (uppercased A-Z only).
    var answers = {
      a: normWord(puzzle.a && puzzle.a.word),
      b: normWord(puzzle.b && puzzle.b.word),
      c: normWord(puzzle.c && puzzle.c.word)
    };

    // Internal mutable state.
    var st = {
      started: false,
      finished: false,
      won: false,
      score: MAX_SCORE,
      // Per-source-word hint tracking.
      // revealedLetters[x] = Set-like map of revealed indices (bool array)
      // spentOn[x]        = cumulative hint spend on that word (letters + word reveal)
      // fullReveal[x]     = whether the entire word has been revealed
      revealedLetters: { a: [], b: [] },
      spentOn: { a: 0, b: 0 },
      fullReveal: { a: false, b: false },
      // Final word C letter reveals (bool array by index).
      revealedFinal: [],
      // Whether the final word's clue/definition has been revealed (costs 4, once).
      clueRevealed: false,
      guesses: 0, // wrong final guesses
      checks: 0 // source-word checks (a + b combined count)
    };

    var storageKey = KEY_PREFIX + dayIndex;

    // ---- Rehydrate from storage if a record exists --------------------------
    (function rehydrate() {
      if (!store) return;
      var raw;
      try {
        raw = store.getItem(storageKey);
      } catch (e) {
        return;
      }
      var rec = safeParse(raw);
      if (!rec || !rec._internal) return;
      var ins = rec._internal;
      // Copy known fields defensively.
      st.started = !!rec.started;
      st.finished = !!rec.finished;
      st.won = !!ins.won;
      st.score = typeof rec.score === 'number' ? rec.score : MAX_SCORE;
      st.guesses = ins.guesses | 0;
      st.checks = ins.checks | 0;
      st.revealedLetters.a = Array.isArray(ins.revealedLetters && ins.revealedLetters.a)
        ? ins.revealedLetters.a.slice()
        : [];
      st.revealedLetters.b = Array.isArray(ins.revealedLetters && ins.revealedLetters.b)
        ? ins.revealedLetters.b.slice()
        : [];
      st.spentOn.a = (ins.spentOn && ins.spentOn.a) || 0;
      st.spentOn.b = (ins.spentOn && ins.spentOn.b) || 0;
      st.fullReveal.a = !!(ins.fullReveal && ins.fullReveal.a);
      st.fullReveal.b = !!(ins.fullReveal && ins.fullReveal.b);
      st.revealedFinal = Array.isArray(ins.revealedFinal) ? ins.revealedFinal.slice() : [];
      st.clueRevealed = !!ins.clueRevealed;
    })();

    // ---- Persistence -------------------------------------------------------
    function revealedSummary() {
      // Public-facing counts for the UI.
      function srcCount(x) {
        if (st.fullReveal[x]) return 'full';
        var arr = st.revealedLetters[x];
        var n = 0;
        for (var i = 0; i < arr.length; i++) if (arr[i]) n++;
        return n;
      }
      var cCount = 0;
      for (var i = 0; i < st.revealedFinal.length; i++) if (st.revealedFinal[i]) cCount++;
      return { a: srcCount('a'), b: srcCount('b'), c: cCount };
    }

    function persist() {
      if (!store) return;
      var rec = {
        started: st.started,
        finished: st.finished,
        score: displayScore(st.score),
        maxScore: MAX_SCORE,
        revealed: revealedSummary(),
        guesses: st.guesses,
        checks: st.checks,
        // `live` mirrors the other games: true while in progress (started,
        // not finished). The hub reads this to badge an active game.
        live: st.started && !st.finished,
        result: { score: displayScore(st.score), max: MAX_SCORE },
        // Internal snapshot so refresh restores exact spend/positions.
        _internal: {
          won: st.won,
          guesses: st.guesses,
          checks: st.checks,
          revealedLetters: st.revealedLetters,
          spentOn: st.spentOn,
          fullReveal: st.fullReveal,
          revealedFinal: st.revealedFinal,
          clueRevealed: st.clueRevealed
        }
      };
      try {
        store.setItem(storageKey, JSON.stringify(rec));
      } catch (e) {
        /* quota / disabled — ignore, game still works in-memory */
      }
    }

    // ---- Score mutation ----------------------------------------------------
    function touchStarted() {
      st.started = true;
    }

    function charge(amount) {
      st.score = round1(st.score - amount);
      if (st.score < 0) st.score = 0;
    }

    // ---- Public state ------------------------------------------------------
    function state() {
      return {
        score: displayScore(st.score),
        maxScore: MAX_SCORE,
        finished: st.finished,
        won: st.won,
        revealed: revealedSummary(),
        clueRevealed: st.clueRevealed,
        guesses: st.guesses,
        checks: st.checks
      };
    }

    // ---- Actions -----------------------------------------------------------

    function shuffle() {
      // Free; UI owns letter order. No-op in scoring, but mark started so the
      // day counts as "played" once the user interacts.
      touchStarted();
      persist();
      return state();
    }

    function checkSource(which, typedWord) {
      which = which === 'b' ? 'b' : 'a';
      if (st.finished) return { correct: false, score: displayScore(st.score) };
      touchStarted();
      st.checks += 1;
      charge(COST_CHECK);
      var correct = normWord(typedWord) === answers[which] && answers[which].length > 0;
      persist();
      return { correct: correct, score: displayScore(st.score) };
    }

    function revealSourceLetter(which) {
      which = which === 'b' ? 'b' : 'a';
      if (st.finished) return { letter: null, index: -1, score: displayScore(st.score) };
      touchStarted();
      var word = answers[which];
      if (!word) return { letter: null, index: -1, score: displayScore(st.score) };
      if (st.fullReveal[which]) {
        // Already fully revealed — nothing left to charge.
        return { letter: null, index: -1, score: displayScore(st.score) };
      }
      var arr = st.revealedLetters[which];
      // Find first not-yet-revealed index (left to right).
      var idx = -1;
      for (var i = 0; i < word.length; i++) {
        if (!arr[i]) {
          idx = i;
          break;
        }
      }
      if (idx === -1) {
        // All letters individually revealed -> mark full, no extra charge.
        st.fullReveal[which] = true;
        persist();
        return { letter: null, index: -1, score: displayScore(st.score) };
      }
      arr[idx] = true;
      // Respect the cap: never spend beyond COST_SOURCE_WORD_CAP on one word.
      var remainingCap = Math.max(0, COST_SOURCE_WORD_CAP - st.spentOn[which]);
      var pay = Math.min(COST_SOURCE_LETTER, remainingCap);
      st.spentOn[which] = round1(st.spentOn[which] + pay);
      charge(pay);
      // If every letter now revealed, mark full.
      var allRevealed = true;
      for (var j = 0; j < word.length; j++) {
        if (!arr[j]) {
          allRevealed = false;
          break;
        }
      }
      if (allRevealed) st.fullReveal[which] = true;
      persist();
      return { letter: word.charAt(idx), index: idx, score: displayScore(st.score) };
    }

    function revealSourceWord(which) {
      which = which === 'b' ? 'b' : 'a';
      if (st.finished) return { word: answers[which], score: displayScore(st.score) };
      touchStarted();
      var word = answers[which];
      if (!word) return { word: '', score: displayScore(st.score) };
      if (st.fullReveal[which]) {
        return { word: word, score: displayScore(st.score) };
      }
      // Cap: total hint cost on this word is 4. Pay the remainder.
      var pay = Math.max(0, COST_SOURCE_WORD_CAP - st.spentOn[which]);
      st.spentOn[which] = COST_SOURCE_WORD_CAP;
      charge(pay);
      // Mark all letters revealed + full.
      var arr = st.revealedLetters[which];
      for (var i = 0; i < word.length; i++) arr[i] = true;
      st.fullReveal[which] = true;
      persist();
      return { word: word, score: displayScore(st.score) };
    }

    function revealFinalLetter() {
      if (st.finished) return { letter: null, index: -1, score: displayScore(st.score) };
      touchStarted();
      var word = answers.c;
      if (!word) return { letter: null, index: -1, score: displayScore(st.score) };
      var arr = st.revealedFinal;
      var idx = -1;
      for (var i = 0; i < word.length; i++) {
        if (!arr[i]) {
          idx = i;
          break;
        }
      }
      if (idx === -1) {
        // Nothing left to reveal — no charge.
        return { letter: null, index: -1, score: displayScore(st.score) };
      }
      arr[idx] = true;
      charge(COST_FINAL_LETTER);
      persist();
      return { letter: word.charAt(idx), index: idx, score: displayScore(st.score) };
    }

    // Reveal the final word's clue/definition. Costs 4, once. The clue text
    // lives in the UI (this module only knows answer words); the UI shows it
    // when state().clueRevealed is true.
    function revealFinalClue() {
      if (st.finished) return { revealed: st.clueRevealed, score: displayScore(st.score) };
      touchStarted();
      if (st.clueRevealed) return { revealed: true, score: displayScore(st.score) };
      st.clueRevealed = true;
      charge(COST_FINAL_CLUE);
      persist();
      return { revealed: true, score: displayScore(st.score) };
    }

    function guessFinal(typedWord) {
      if (st.finished) {
        return { correct: st.won, score: displayScore(st.score), finished: true };
      }
      touchStarted();
      var correct = normWord(typedWord) === answers.c && answers.c.length > 0;
      if (correct) {
        st.won = true;
        st.finished = true;
        persist();
        return { correct: true, score: displayScore(st.score), finished: true };
      }
      // Wrong guess.
      st.guesses += 1;
      charge(COST_WRONG_FINAL);
      persist();
      return { correct: false, score: displayScore(st.score), finished: false };
    }

    function giveUp() {
      if (st.finished) {
        return { score: displayScore(st.score), finished: true };
      }
      touchStarted();
      st.score = 0;
      st.won = false;
      st.finished = true;
      persist();
      return { score: 0, finished: true };
    }

    // ---- Share -------------------------------------------------------------
    // One tasteful, Wordle-like block. No URL (the hub adds it).
    //
    //   Anagram Daily #3 — 14.5/20
    //   ⭐ clean solve         (no hints/checks, won)
    //   or a compact hint summary line using distinct marks:
    //     🔍 checks   🔤 source-letter hints   🟨 full source word
    //     🎯 final-letter hints   ❌ wrong guesses   💀 gave up
    function shareText() {
      var s = state();
      var head = 'Anagram Daily #' + dayIndex + ' — ' + s.score + '/' + MAX_SCORE;

      if (!s.finished) {
        return head + '\n⏳ in progress';
      }

      if (!s.won) {
        return head + '\n💀 gave up';
      }

      // Won. Count help used.
      var srcLetterHints = 0;
      var fullSrcWords = 0;
      ['a', 'b'].forEach(function (x) {
        if (st.fullReveal[x]) {
          fullSrcWords += 1;
        } else {
          var arr = st.revealedLetters[x];
          for (var i = 0; i < arr.length; i++) if (arr[i]) srcLetterHints++;
        }
      });
      var finalHints = 0;
      for (var i = 0; i < st.revealedFinal.length; i++) if (st.revealedFinal[i]) finalHints++;

      var usedAny =
        s.checks > 0 ||
        srcLetterHints > 0 ||
        fullSrcWords > 0 ||
        finalHints > 0 ||
        st.clueRevealed ||
        s.guesses > 0;

      if (!usedAny) {
        return head + '\n⭐ clean solve';
      }

      var marks = [];
      if (fullSrcWords > 0) marks.push(repeat('🟨', fullSrcWords));
      if (srcLetterHints > 0) marks.push(repeat('🔤', srcLetterHints));
      if (st.clueRevealed) marks.push('💡');
      if (finalHints > 0) marks.push(repeat('🎯', finalHints));
      if (s.checks > 0) marks.push(repeat('🔍', s.checks));
      if (s.guesses > 0) marks.push(repeat('❌', s.guesses));

      return head + '\n' + marks.join(' ');
    }

    function repeat(str, n) {
      var out = '';
      for (var i = 0; i < n; i++) out += str;
      return out;
    }

    // ---- Return the game handle -------------------------------------------
    return {
      state: state,
      shuffle: shuffle,
      checkSource: checkSource,
      revealSourceLetter: revealSourceLetter,
      revealSourceWord: revealSourceWord,
      revealFinalLetter: revealFinalLetter,
      revealFinalClue: revealFinalClue,
      guessFinal: guessFinal,
      giveUp: giveUp,
      shareText: shareText,
      // Exposed for tests / debugging (not required by the UI).
      _storageKey: storageKey
    };
  }

  // ---- Stats helpers (mirror the games hub key scheme) ---------------------
  // Keys are `anagram_day<N>`. Records carry { started, finished, result:{score,max} }.

  function keyFor(dayIndex) {
    return KEY_PREFIX + (dayIndex | 0);
  }

  function readDay(dayIndex, storage) {
    var store = getStore(storage);
    if (!store) return null;
    var raw;
    try {
      raw = store.getItem(keyFor(dayIndex));
    } catch (e) {
      return null;
    }
    var rec = safeParse(raw);
    if (!rec) return null;
    return {
      started: !!rec.started,
      finished: !!rec.finished,
      live: rec.live === true,
      score: rec.result && typeof rec.result.score === 'number' ? rec.result.score : rec.score,
      max: MAX_SCORE
    };
  }

  // Per-day result lookup for the UI/archive: null if not played.
  function resultFor(dayIndex, storage) {
    var r = readDay(dayIndex, storage);
    if (!r || !r.started) return null;
    return { score: r.score, max: MAX_SCORE, finished: r.finished };
  }

  // Current streak: consecutive finished days counting back from today, with a
  // grace day so an unfinished today doesn't break yesterday's streak. Mirrors
  // the hub's currentStreak().
  function streak(todayIndex, storage) {
    var t = todayIndex | 0;
    function isFin(i) {
      var r = readDay(i, storage);
      return !!(r && r.finished);
    }
    var idx = isFin(t) ? t : t - 1;
    var n = 0;
    while (isFin(idx)) {
      n += 1;
      idx -= 1;
    }
    return n;
  }

  // Total days ever started (scan all matching keys). Mirrors hub playedCount().
  function playedCount(storage) {
    var store = getStore(storage);
    if (!store) return 0;
    var n = 0;
    var re = new RegExp('^' + KEY_PREFIX.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(-?\\d+)$');
    var len = 0;
    try {
      len = store.length;
    } catch (e) {
      return 0;
    }
    for (var i = 0; i < len; i++) {
      var k = store.key(i);
      var mm = k && k.match(re);
      if (!mm) continue;
      var r = readDay(Number(mm[1]), storage);
      if (r && r.started) n += 1;
    }
    return n;
  }

  var AnagramScoring = {
    create: create,
    // Stats helpers usable by the UI / archive.
    readDay: readDay,
    resultFor: resultFor,
    streak: streak,
    playedCount: playedCount,
    keyFor: keyFor,
    MAX_SCORE: MAX_SCORE,
    KEY_PREFIX: KEY_PREFIX
  };

  // ---- Export ------------------------------------------------------------
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AnagramScoring;
  }
  if (typeof root !== 'undefined') {
    root.AnagramScoring = AnagramScoring;
  }
})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this);


// ---------------------------------------------------------------------------
// Node self-test
// ---------------------------------------------------------------------------
if (typeof require !== 'undefined' && typeof module !== 'undefined' && require.main === module) {
  (function runTests() {
    var AnagramScoring = module.exports;
    var passed = 0;
    var failed = 0;

    function eq(actual, expected, msg) {
      var a = JSON.stringify(actual);
      var e = JSON.stringify(expected);
      if (a === e) {
        passed++;
      } else {
        failed++;
        console.error('FAIL: ' + msg + '\n  expected ' + e + '\n  got      ' + a);
      }
    }
    function ok(cond, msg) {
      if (cond) passed++;
      else {
        failed++;
        console.error('FAIL: ' + msg);
      }
    }

    // Mock localStorage.
    function mockStore() {
      var m = {};
      return {
        _m: m,
        getItem: function (k) {
          return Object.prototype.hasOwnProperty.call(m, k) ? m[k] : null;
        },
        setItem: function (k, v) {
          m[k] = String(v);
        },
        removeItem: function (k) {
          delete m[k];
        },
        get length() {
          return Object.keys(m).length;
        },
        key: function (i) {
          return Object.keys(m)[i];
        }
      };
    }

    var PUZZLE = {
      a: { word: 'MOON' },
      b: { word: 'STARER' },
      c: { word: 'ASTRONOMER' }
    };

    // 1) Clean solve = 20.
    (function () {
      var g = AnagramScoring.create({ dayIndex: 1, puzzle: PUZZLE, storage: mockStore() });
      var r = g.guessFinal('astronomer');
      eq(r.correct, true, 'clean: correct guess');
      eq(r.finished, true, 'clean: finished');
      eq(g.state().score, 20, 'clean solve keeps 20');
      eq(g.state().won, true, 'clean: won flag');
      ok(g.shareText().indexOf('⭐ clean solve') !== -1, 'clean: share shows star');
      ok(g.shareText().indexOf('#1 — 20/20') !== -1, 'clean: share header');
    })();

    // 2) Each hint deducts correctly.
    (function () {
      var g = AnagramScoring.create({ dayIndex: 2, puzzle: PUZZLE, storage: mockStore() });
      eq(g.checkSource('a', 'WRONG').correct, false, 'check wrong -> false');
      eq(g.state().score, 19.5, 'check costs 0.5');
      eq(g.checkSource('a', 'moon').correct, true, 'check right -> true');
      eq(g.state().score, 19, 'second check costs 0.5');
      var rl = g.revealSourceLetter('a');
      eq(rl.letter, 'M', 'first source letter is M');
      eq(rl.index, 0, 'first source letter index 0');
      eq(g.state().score, 18, 'source letter costs 1');
      var fl = g.revealFinalLetter();
      eq(fl.letter, 'A', 'final letter is A');
      eq(g.state().score, 16.5, 'final letter costs 1.5');
      var wg = g.guessFinal('WRONG');
      eq(wg.correct, false, 'wrong final -> false');
      eq(wg.finished, false, 'wrong final not finished');
      eq(g.state().score, 15.5, 'wrong final costs 1');
      eq(g.state().guesses, 1, 'guesses counted');
      eq(g.state().checks, 2, 'checks counted');
    })();

    // 3) Entire-word cap logic.
    (function () {
      // 3a) Reveal word with no prior letters: -4 flat.
      var g = AnagramScoring.create({ dayIndex: 3, puzzle: PUZZLE, storage: mockStore() });
      var rw = g.revealSourceWord('a');
      eq(rw.word, 'MOON', 'reveal full word returns MOON');
      eq(g.state().score, 16, 'full word reveal costs 4');
      eq(g.state().revealed.a, 'full', 'revealed.a is full');
      // Revealing again is a no-op (no double charge).
      g.revealSourceWord('a');
      eq(g.state().score, 16, 'second full reveal is free');
      g.revealSourceLetter('a');
      eq(g.state().score, 16, 'letter reveal after full is free');
    })();

    (function () {
      // 3b) Pay 3 letters (-3) then reveal whole word: only -1 more (cap at 4).
      var g = AnagramScoring.create({ dayIndex: 4, puzzle: PUZZLE, storage: mockStore() });
      g.revealSourceLetter('b'); // -1
      g.revealSourceLetter('b'); // -1
      g.revealSourceLetter('b'); // -1
      eq(g.state().score, 17, '3 source letters cost 3');
      g.revealSourceWord('b'); // remainder = 4-3 = 1
      eq(g.state().score, 16, 'full word after 3 letters costs only 1 more (cap 4)');
      eq(g.state().revealed.b, 'full', 'b is full after reveal word');
    })();

    (function () {
      // 3c) Pay 4 letters on STARER (6 letters) -> next letters cost 0 (cap hit).
      var g = AnagramScoring.create({ dayIndex: 5, puzzle: PUZZLE, storage: mockStore() });
      for (var i = 0; i < 4; i++) g.revealSourceLetter('b'); // -4 total
      eq(g.state().score, 16, '4 letters cost 4');
      g.revealSourceLetter('b'); // 5th letter: cap already hit -> free
      eq(g.state().score, 16, '5th letter free (cap reached)');
      g.revealSourceWord('b'); // remainder 0
      eq(g.state().score, 16, 'full word after cap is free');
    })();

    // 4) Floor at 0.
    (function () {
      var g = AnagramScoring.create({ dayIndex: 6, puzzle: PUZZLE, storage: mockStore() });
      // Blow the budget: full reveal a(-4) + b(-4) = -8 -> 12; final letters 10 x 1.5 = 15
      g.revealSourceWord('a');
      g.revealSourceWord('b');
      for (var i = 0; i < 10; i++) g.revealFinalLetter(); // -15 -> would be -3
      eq(g.state().score, 0, 'score floors at 0, never negative');
      // Wrong guesses stay at 0 too.
      g.guessFinal('NOPE');
      eq(g.state().score, 0, 'still 0 after wrong guess at floor');
    })();

    // 5) Give up = 0, finished.
    (function () {
      var g = AnagramScoring.create({ dayIndex: 7, puzzle: PUZZLE, storage: mockStore() });
      g.checkSource('a', 'moon'); // 19.5
      var r = g.giveUp();
      eq(r.score, 0, 'giveUp -> 0');
      eq(r.finished, true, 'giveUp -> finished');
      eq(g.state().won, false, 'giveUp -> not won');
      // Actions after finish are no-ops.
      g.revealSourceLetter('a');
      g.guessFinal('astronomer');
      eq(g.state().score, 0, 'no-op after giveUp keeps 0');
      eq(g.state().finished, true, 'stays finished');
      ok(g.shareText().indexOf('💀 gave up') !== -1, 'giveUp share shows skull');
    })();

    // 6) Rehydration via mock localStorage.
    (function () {
      var store = mockStore();
      var g1 = AnagramScoring.create({ dayIndex: 8, puzzle: PUZZLE, storage: store });
      g1.checkSource('a', 'moon'); // -0.5 -> 19.5
      g1.revealSourceLetter('a'); // -1 -> 18.5 (index 0 = M)
      g1.revealSourceLetter('a'); // -1 -> 17.5 (index 1 = O)
      g1.revealFinalLetter(); // -1.5 -> 16 (index 0 = A)
      var before = g1.state();
      eq(before.score, 16, 'pre-reload score 16');

      // New instance same day/store should restore exact state.
      var g2 = AnagramScoring.create({ dayIndex: 8, puzzle: PUZZLE, storage: store });
      var after = g2.state();
      eq(after.score, 16, 'rehydrated score 16');
      eq(after.checks, 1, 'rehydrated checks');
      eq(after.revealed.a, 2, 'rehydrated 2 source-letter reveals');
      eq(after.revealed.c, 1, 'rehydrated 1 final-letter reveal');
      // Next source letter should be index 2 (N... wait MOON -> index2=O), not recharge index0/1.
      var nl = g2.revealSourceLetter('a');
      eq(nl.index, 2, 'rehydrated reveal continues at next index');
      eq(g2.state().score, 15, 'charge continues correctly after rehydrate');
    })();

    // 7) Cap survives across rehydration.
    (function () {
      var store = mockStore();
      var g1 = AnagramScoring.create({ dayIndex: 9, puzzle: PUZZLE, storage: store });
      g1.revealSourceLetter('a'); // -1
      g1.revealSourceLetter('a'); // -1
      g1.revealSourceLetter('a'); // -1  (spentOn.a = 3)
      eq(g1.state().score, 17, 'pre-reload 3 letters = 17');
      var g2 = AnagramScoring.create({ dayIndex: 9, puzzle: PUZZLE, storage: store });
      g2.revealSourceWord('a'); // remainder 4-3 = 1
      eq(g2.state().score, 16, 'cap respected across rehydrate (only 1 more)');
    })();

    // 8) Stats helpers.
    (function () {
      var store = mockStore();
      // Day 10 finished (won), day 11 finished (gave up), day 12 started only.
      var g10 = AnagramScoring.create({ dayIndex: 10, puzzle: PUZZLE, storage: store });
      g10.guessFinal('astronomer');
      var g11 = AnagramScoring.create({ dayIndex: 11, puzzle: PUZZLE, storage: store });
      g11.giveUp();
      var g12 = AnagramScoring.create({ dayIndex: 12, puzzle: PUZZLE, storage: store });
      g12.checkSource('a', 'x'); // started, not finished

      eq(AnagramScoring.playedCount(store), 3, 'playedCount = 3');
      eq(AnagramScoring.resultFor(10, store), { score: 20, max: 20, finished: true }, 'resultFor day10');
      eq(AnagramScoring.resultFor(11, store), { score: 0, max: 20, finished: true }, 'resultFor day11');
      eq(AnagramScoring.resultFor(99, store), null, 'resultFor unplayed = null');
      // Streak: days 10 and 11 finished, 12 not. Counting back from 12: grace
      // means start at 11 -> 11 finished, 10 finished, 9 unplayed -> streak 2.
      eq(AnagramScoring.streak(12, store), 2, 'streak counts back through finished days');
      eq(AnagramScoring.streak(10, store), 1, 'streak from day10 = 1');
    })();

    // 9) Persisted record shape matches the contract.
    (function () {
      var store = mockStore();
      var g = AnagramScoring.create({ dayIndex: 20, puzzle: PUZZLE, storage: store });
      g.revealSourceLetter('a');
      var rec = JSON.parse(store.getItem('anagram_day20'));
      ok('started' in rec, 'record has started');
      ok('finished' in rec, 'record has finished');
      ok('score' in rec, 'record has score');
      eq(rec.maxScore, 20, 'record maxScore 20');
      ok('revealed' in rec, 'record has revealed');
      ok('guesses' in rec, 'record has guesses');
      ok('checks' in rec, 'record has checks');
      ok('live' in rec, 'record has live');
      ok(rec.result && rec.result.max === 20, 'record result.max 20');
      eq(rec.live, true, 'live true while in progress');
    })();

    // 10) Reveal final clue: -4, once, persisted, in state + share.
    (function () {
      var store = mockStore();
      var g = AnagramScoring.create({ dayIndex: 30, puzzle: PUZZLE, storage: store });
      eq(g.state().clueRevealed, false, 'clue hidden by default');
      var r = g.revealFinalClue();
      eq(r.revealed, true, 'revealFinalClue -> revealed');
      eq(g.state().score, 16, 'reveal final clue costs 4');
      eq(g.state().clueRevealed, true, 'state.clueRevealed true');
      g.revealFinalClue();
      eq(g.state().score, 16, 'second clue reveal is free');
      // Survives rehydration.
      var g2 = AnagramScoring.create({ dayIndex: 30, puzzle: PUZZLE, storage: store });
      eq(g2.state().clueRevealed, true, 'clueRevealed rehydrated');
      eq(g2.state().score, 16, 'score rehydrated after clue reveal');
      // Counts as help in share (won but not clean).
      g2.guessFinal('astronomer');
      ok(g2.shareText().indexOf('💡') !== -1, 'share shows clue-reveal mark');
      ok(g2.shareText().indexOf('⭐ clean solve') === -1, 'clue reveal is not a clean solve');
    })();

    console.log('\n' + passed + ' passed, ' + failed + ' failed');
    if (failed > 0) process.exit(1);
  })();
}
