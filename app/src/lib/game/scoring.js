// ===========================================================================
// Anagram scoring engine — PURE (no localStorage, no DOM). The Svelte component
// drives it and hands snapshots to the platform, which owns persistence.
//
// Scoring (unchanged from the original static site's CONTRACT.md):
//   - Start 20.00 each day. Floor at 0 (never negative). Shuffle is free.
//   - Check a source word (A/B): -0.5 each.
//   - Reveal ONE letter of a source word (A/B): -1 each.
//   - Reveal ENTIRE source word (A/B): -4 flat, capping that word's cumulative
//     hint cost at 4 (max(0, 4 - already-spent)).
//   - Reveal ONE letter of the final word C: -1.5 each.
//   - Reveal the final word's clue/definition: -4, once.
//   - Wrong guess on the final word C: -1 each.
//   - Give up: day score -> 0, finished.
//   - A correct final guess finishes the day and locks the score.
//   - Score tracked to 1 decimal; display = max(0, round1(score)).
// ===========================================================================

export const MAX_SCORE = 20;
const COST_CHECK = 0.5;
const COST_SOURCE_LETTER = 1;
const COST_SOURCE_WORD_CAP = 4;
const COST_FINAL_LETTER = 1.5;
const COST_WRONG_FINAL = 1;
const COST_FINAL_CLUE = 4;

const round1 = (n) => Math.round(n * 10) / 10;
const displayScore = (n) => Math.max(0, round1(n));
const normWord = (s) =>
  String(s == null ? '' : s)
    .toUpperCase()
    .replace(/[^A-Z]/g, '');

function freshState() {
  return {
    started: false,
    finished: false,
    won: false,
    score: MAX_SCORE,
    revealedLetters: { a: [], b: [] },
    spentOn: { a: 0, b: 0 },
    fullReveal: { a: false, b: false },
    revealedFinal: [],
    clueRevealed: false,
    guesses: 0,
    checks: 0
  };
}

// Rehydrate defensively from a saved snapshot (any shape).
function hydrate(saved) {
  const st = freshState();
  if (!saved || typeof saved !== 'object') return st;
  st.started = !!saved.started;
  st.finished = !!saved.finished;
  st.won = !!saved.won;
  st.score = typeof saved.score === 'number' ? saved.score : MAX_SCORE;
  st.guesses = saved.guesses | 0;
  st.checks = saved.checks | 0;
  const rl = saved.revealedLetters || {};
  st.revealedLetters.a = Array.isArray(rl.a) ? rl.a.slice() : [];
  st.revealedLetters.b = Array.isArray(rl.b) ? rl.b.slice() : [];
  const sp = saved.spentOn || {};
  st.spentOn.a = sp.a || 0;
  st.spentOn.b = sp.b || 0;
  const fr = saved.fullReveal || {};
  st.fullReveal.a = !!fr.a;
  st.fullReveal.b = !!fr.b;
  st.revealedFinal = Array.isArray(saved.revealedFinal) ? saved.revealedFinal.slice() : [];
  st.clueRevealed = !!saved.clueRevealed;
  return st;
}

export function createEngine(puzzle, saved) {
  const answers = {
    a: normWord(puzzle && puzzle.a && puzzle.a.word),
    b: normWord(puzzle && puzzle.b && puzzle.b.word),
    c: normWord(puzzle && puzzle.c && puzzle.c.word)
  };
  const st = hydrate(saved);

  function touchStarted() {
    st.started = true;
  }
  function charge(amount) {
    st.score = round1(st.score - amount);
    if (st.score < 0) st.score = 0;
  }

  function revealedSummary() {
    function srcCount(x) {
      if (st.fullReveal[x]) return 'full';
      const arr = st.revealedLetters[x];
      let n = 0;
      for (let i = 0; i < arr.length; i++) if (arr[i]) n++;
      return n;
    }
    let cCount = 0;
    for (let i = 0; i < st.revealedFinal.length; i++) if (st.revealedFinal[i]) cCount++;
    return { a: srcCount('a'), b: srcCount('b'), c: cCount };
  }

  function state() {
    return {
      score: displayScore(st.score),
      maxScore: MAX_SCORE,
      started: st.started,
      finished: st.finished,
      won: st.won,
      revealed: revealedSummary(),
      clueRevealed: st.clueRevealed,
      guesses: st.guesses,
      checks: st.checks
    };
  }

  // Resumable blob handed to the platform (record.state).
  function snapshot() {
    return {
      started: st.started,
      finished: st.finished,
      won: st.won,
      score: displayScore(st.score),
      revealedLetters: { a: st.revealedLetters.a.slice(), b: st.revealedLetters.b.slice() },
      spentOn: { a: st.spentOn.a, b: st.spentOn.b },
      fullReveal: { a: st.fullReveal.a, b: st.fullReveal.b },
      revealedFinal: st.revealedFinal.slice(),
      clueRevealed: st.clueRevealed,
      guesses: st.guesses,
      checks: st.checks
    };
  }

  // --- actions -------------------------------------------------------------
  function shuffle() {
    touchStarted();
    return state();
  }

  function checkSource(which, typedWord) {
    which = which === 'b' ? 'b' : 'a';
    if (st.finished) return { correct: false, score: displayScore(st.score) };
    touchStarted();
    st.checks += 1;
    charge(COST_CHECK);
    const correct = normWord(typedWord) === answers[which] && answers[which].length > 0;
    return { correct, score: displayScore(st.score) };
  }

  function revealSourceLetter(which) {
    which = which === 'b' ? 'b' : 'a';
    if (st.finished) return { letter: null, index: -1, score: displayScore(st.score) };
    touchStarted();
    const word = answers[which];
    if (!word || st.fullReveal[which]) {
      return { letter: null, index: -1, score: displayScore(st.score) };
    }
    const arr = st.revealedLetters[which];
    let idx = -1;
    for (let i = 0; i < word.length; i++) {
      if (!arr[i]) {
        idx = i;
        break;
      }
    }
    if (idx === -1) {
      st.fullReveal[which] = true;
      return { letter: null, index: -1, score: displayScore(st.score) };
    }
    arr[idx] = true;
    const remainingCap = Math.max(0, COST_SOURCE_WORD_CAP - st.spentOn[which]);
    const pay = Math.min(COST_SOURCE_LETTER, remainingCap);
    st.spentOn[which] = round1(st.spentOn[which] + pay);
    charge(pay);
    let all = true;
    for (let j = 0; j < word.length; j++) if (!arr[j]) all = false;
    if (all) st.fullReveal[which] = true;
    return { letter: word.charAt(idx), index: idx, score: displayScore(st.score) };
  }

  function revealSourceWord(which) {
    which = which === 'b' ? 'b' : 'a';
    if (st.finished) return { word: answers[which], score: displayScore(st.score) };
    touchStarted();
    const word = answers[which];
    if (!word) return { word: '', score: displayScore(st.score) };
    if (st.fullReveal[which]) return { word, score: displayScore(st.score) };
    const pay = Math.max(0, COST_SOURCE_WORD_CAP - st.spentOn[which]);
    st.spentOn[which] = COST_SOURCE_WORD_CAP;
    charge(pay);
    const arr = st.revealedLetters[which];
    for (let i = 0; i < word.length; i++) arr[i] = true;
    st.fullReveal[which] = true;
    return { word, score: displayScore(st.score) };
  }

  function revealFinalLetter() {
    if (st.finished) return { letter: null, index: -1, score: displayScore(st.score) };
    touchStarted();
    const word = answers.c;
    if (!word) return { letter: null, index: -1, score: displayScore(st.score) };
    const arr = st.revealedFinal;
    let idx = -1;
    for (let i = 0; i < word.length; i++) {
      if (!arr[i]) {
        idx = i;
        break;
      }
    }
    if (idx === -1) return { letter: null, index: -1, score: displayScore(st.score) };
    arr[idx] = true;
    charge(COST_FINAL_LETTER);
    return { letter: word.charAt(idx), index: idx, score: displayScore(st.score) };
  }

  function revealFinalClue() {
    if (st.finished) return { revealed: st.clueRevealed, score: displayScore(st.score) };
    touchStarted();
    if (st.clueRevealed) return { revealed: true, score: displayScore(st.score) };
    st.clueRevealed = true;
    charge(COST_FINAL_CLUE);
    return { revealed: true, score: displayScore(st.score) };
  }

  function guessFinal(typedWord) {
    if (st.finished) return { correct: st.won, score: displayScore(st.score), finished: true };
    touchStarted();
    const correct = normWord(typedWord) === answers.c && answers.c.length > 0;
    if (correct) {
      st.won = true;
      st.finished = true;
      return { correct: true, score: displayScore(st.score), finished: true };
    }
    st.guesses += 1;
    charge(COST_WRONG_FINAL);
    return { correct: false, score: displayScore(st.score), finished: false };
  }

  function giveUp() {
    if (st.finished) return { score: displayScore(st.score), finished: true };
    touchStarted();
    st.score = 0;
    st.won = false;
    st.finished = true;
    return { score: 0, finished: true };
  }

  // --- share marks (second line of the share block) ------------------------
  function marks() {
    const s = state();
    if (!s.finished) return '⏳';
    if (!s.won) return '💀';
    let srcLetterHints = 0;
    let fullSrcWords = 0;
    ['a', 'b'].forEach((x) => {
      if (st.fullReveal[x]) fullSrcWords += 1;
      else {
        const arr = st.revealedLetters[x];
        for (let i = 0; i < arr.length; i++) if (arr[i]) srcLetterHints++;
      }
    });
    let finalHints = 0;
    for (let i = 0; i < st.revealedFinal.length; i++) if (st.revealedFinal[i]) finalHints++;
    const usedAny =
      s.checks > 0 ||
      srcLetterHints > 0 ||
      fullSrcWords > 0 ||
      finalHints > 0 ||
      st.clueRevealed ||
      s.guesses > 0;
    if (!usedAny) return '⭐';
    const rep = (str, n) => str.repeat(n);
    const out = [];
    if (fullSrcWords > 0) out.push(rep('🟨', fullSrcWords));
    if (srcLetterHints > 0) out.push(rep('🔤', srcLetterHints));
    if (st.clueRevealed) out.push('💡');
    if (finalHints > 0) out.push(rep('🎯', finalHints));
    if (s.checks > 0) out.push(rep('🔍', s.checks));
    if (s.guesses > 0) out.push(rep('❌', s.guesses));
    return out.join(' ');
  }

  // Final-result blob handed to the platform (record.result) on finish.
  function result() {
    return { won: st.won, score: displayScore(st.score), max: MAX_SCORE, marks: marks() };
  }

  return {
    answers,
    state,
    snapshot,
    result,
    shuffle,
    checkSource,
    revealSourceLetter,
    revealSourceWord,
    revealFinalLetter,
    revealFinalClue,
    guessFinal,
    giveUp
  };
}
