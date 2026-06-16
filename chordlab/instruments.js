/* ChordLab — instruments.js
 * window.Instruments : diagrammi accordo (chitarra/ukulele) + tastiera piano.
 * Vanilla JS, nessuna dipendenza, funziona sotto file://.
 * Si appoggia a window.ChordEngine (caricato prima) per parse()/pcs().
 */
(function () {
  'use strict';

  // ---- Tema ----
  var COL = {
    grid: '#555',
    string: '#888',
    dot: '#c8a45a',
    dotText: '#1a1a1a',
    text: '#e8e8e8',
    muted: '#888',
    whiteKey: '#f4f4f4',
    whiteKeyEdge: '#777',
    blackKey: '#222',
    keyHi: '#c8a45a',
    rootHi: '#e07b39'
  };
  var FONT = 'sans-serif';

  // ============================================================
  //  Curated open-chord dictionaries
  //  Per fret string: index 0 = string più bassa (E grave per chitarra,
  //  G per ukulele). Valori: numero di fret, 0 = open (corda a vuoto),
  //  -1 = muted (x). barre opzionale: {fret, from, to}
  // ============================================================

  // GUITAR (EADGBE, 6 strings). Frets array length 6, low E .. high E.
  var GUITAR_OPEN = {
    'C':      { frets: [-1, 3, 2, 0, 1, 0] },
    'Cmaj7':  { frets: [-1, 3, 2, 0, 0, 0] },
    'C7':     { frets: [-1, 3, 2, 3, 1, 0] },
    'C6':     { frets: [-1, 3, 2, 2, 1, 0] },
    'Cm':     { frets: [-1, 3, 5, 5, 4, 3], barre: { fret: 3, from: 1, to: 5 } },
    'Csus4':  { frets: [-1, 3, 3, 0, 1, 1] },
    'Csus2':  { frets: [-1, 3, 0, 0, 1, 3] },

    'D':      { frets: [-1, -1, 0, 2, 3, 2] },
    'Dm':     { frets: [-1, -1, 0, 2, 3, 1] },
    'D7':     { frets: [-1, -1, 0, 2, 1, 2] },
    'Dm7':    { frets: [-1, -1, 0, 2, 1, 1] },
    'Dmaj7':  { frets: [-1, -1, 0, 2, 2, 2] },
    'Dsus4':  { frets: [-1, -1, 0, 2, 3, 3] },
    'Dsus2':  { frets: [-1, -1, 0, 2, 3, 0] },
    'D6':     { frets: [-1, -1, 0, 2, 0, 2] },
    'Ddim':   { frets: [-1, -1, 0, 1, 0, 1] },

    'E':      { frets: [0, 2, 2, 1, 0, 0] },
    'Em':     { frets: [0, 2, 2, 0, 0, 0] },
    'E7':     { frets: [0, 2, 0, 1, 0, 0] },
    'Em7':    { frets: [0, 2, 0, 0, 0, 0] },
    'Emaj7':  { frets: [0, 2, 1, 1, 0, 0] },
    'Esus4':  { frets: [0, 2, 2, 2, 0, 0] },
    'E6':     { frets: [0, 2, 2, 1, 2, 0] },

    'F':      { frets: [1, 3, 3, 2, 1, 1], barre: { fret: 1, from: 0, to: 5 } },
    'Fmaj7':  { frets: [-1, -1, 3, 2, 1, 0] },
    'Fm':     { frets: [1, 3, 3, 1, 1, 1], barre: { fret: 1, from: 0, to: 5 } },
    'F7':     { frets: [1, 3, 1, 2, 1, 1], barre: { fret: 1, from: 0, to: 5 } },

    'G':      { frets: [3, 2, 0, 0, 0, 3] },
    'Gm':     { frets: [3, 5, 5, 3, 3, 3], barre: { fret: 3, from: 0, to: 5 } },
    'G7':     { frets: [3, 2, 0, 0, 0, 1] },
    'Gmaj7':  { frets: [3, 2, 0, 0, 0, 2] },
    'Gm7':    { frets: [3, 5, 3, 3, 3, 3], barre: { fret: 3, from: 0, to: 5 } },
    'Gsus4':  { frets: [3, 3, 0, 0, 1, 3] },
    'G6':     { frets: [3, 2, 0, 0, 0, 0] },

    'A':      { frets: [-1, 0, 2, 2, 2, 0] },
    'Am':     { frets: [-1, 0, 2, 2, 1, 0] },
    'A7':     { frets: [-1, 0, 2, 0, 2, 0] },
    'Am7':    { frets: [-1, 0, 2, 0, 1, 0] },
    'Amaj7':  { frets: [-1, 0, 2, 1, 2, 0] },
    'Asus4':  { frets: [-1, 0, 2, 2, 3, 0] },
    'Asus2':  { frets: [-1, 0, 2, 2, 0, 0] },
    'A6':     { frets: [-1, 0, 2, 2, 2, 2] },
    'Adim':   { frets: [-1, 0, 1, 2, 1, -1] },

    'B':      { frets: [-1, 2, 4, 4, 4, 2], barre: { fret: 2, from: 1, to: 5 } },
    'Bm':     { frets: [-1, 2, 4, 4, 3, 2], barre: { fret: 2, from: 1, to: 5 } },
    'B7':     { frets: [-1, 2, 1, 2, 0, 2] },
    'Bm7':    { frets: [-1, 2, 4, 2, 3, 2], barre: { fret: 2, from: 1, to: 5 } },

    'Bb':     { frets: [-1, 1, 3, 3, 3, 1], barre: { fret: 1, from: 1, to: 5 } },
    'Bbm':    { frets: [-1, 1, 3, 3, 2, 1], barre: { fret: 1, from: 1, to: 5 } },
    'Bb7':    { frets: [-1, 1, 3, 1, 3, 1], barre: { fret: 1, from: 1, to: 5 } },
    'Bbmaj7': { frets: [-1, 1, 3, 2, 3, 1], barre: { fret: 1, from: 1, to: 5 } }
  };

  // UKULELE (GCEA, 4 strings). Frets array length 4, g C E A.
  var UKE_OPEN = {
    'C':      { frets: [0, 0, 0, 3] },
    'Cmaj7':  { frets: [0, 0, 0, 2] },
    'C7':     { frets: [0, 0, 0, 1] },
    'Cm':     { frets: [0, 3, 3, 3] },
    'Cm7':    { frets: [3, 3, 3, 3], barre: { fret: 3, from: 0, to: 3 } },
    'C6':     { frets: [0, 0, 0, 0] },
    'Csus4':  { frets: [0, 0, 1, 3] },
    'Csus2':  { frets: [0, 2, 3, 3] },
    'Cdim':   { frets: [2, 3, 2, 3] },

    'D':      { frets: [2, 2, 2, 0] },
    'Dm':     { frets: [2, 2, 1, 0] },
    'D7':     { frets: [2, 2, 2, 3] },
    'Dm7':    { frets: [2, 2, 1, 3] },
    'Dmaj7':  { frets: [2, 2, 2, 4] },
    'Dsus4':  { frets: [0, 2, 3, 0] },
    'Dsus2':  { frets: [2, 2, 0, 0] },
    'D6':     { frets: [2, 2, 2, 2] },

    'E':      { frets: [4, 4, 4, 2] },
    'Em':     { frets: [0, 4, 3, 2] },
    'E7':     { frets: [1, 2, 0, 2] },
    'Em7':    { frets: [0, 2, 0, 2] },
    'Emaj7':  { frets: [1, 3, 0, 2] },

    'F':      { frets: [2, 0, 1, 0] },
    'Fm':     { frets: [1, 0, 1, 3] },
    'F7':     { frets: [2, 3, 1, 0] },
    'Fm7':    { frets: [1, 3, 1, 3] },
    'Fmaj7':  { frets: [2, 4, 1, 3] },
    'Fsus4':  { frets: [3, 0, 1, 1] },
    'F6':     { frets: [2, 2, 1, 3] },

    'G':      { frets: [0, 2, 3, 2] },
    'Gm':     { frets: [0, 2, 3, 1] },
    'G7':     { frets: [0, 2, 1, 2] },
    'Gm7':    { frets: [0, 2, 1, 1] },
    'Gmaj7':  { frets: [0, 2, 2, 2] },
    'Gsus4':  { frets: [0, 2, 3, 3] },
    'Gsus2':  { frets: [0, 2, 3, 0] },
    'G6':     { frets: [0, 2, 0, 2] },

    'A':      { frets: [2, 1, 0, 0] },
    'Am':     { frets: [2, 0, 0, 0] },
    'A7':     { frets: [0, 1, 0, 0] },
    'Am7':    { frets: [0, 0, 0, 0] },
    'Amaj7':  { frets: [1, 1, 0, 0] },
    'Asus4':  { frets: [2, 2, 0, 0] },
    'Asus2':  { frets: [2, 4, 5, 2] },
    'A6':     { frets: [2, 4, 3, 4] },

    'B':      { frets: [4, 3, 2, 2], barre: { fret: 2, from: 2, to: 3 } },
    'Bm':     { frets: [4, 2, 2, 2], barre: { fret: 2, from: 1, to: 3 } },
    'B7':     { frets: [2, 3, 2, 2], barre: { fret: 2, from: 0, to: 3 } },
    'Bm7':    { frets: [2, 2, 2, 2], barre: { fret: 2, from: 0, to: 3 } },

    'Bb':     { frets: [3, 2, 1, 1], barre: { fret: 1, from: 2, to: 3 } },
    'Bbm':    { frets: [3, 1, 1, 1], barre: { fret: 1, from: 1, to: 3 } },
    'Bb7':    { frets: [1, 2, 1, 1], barre: { fret: 1, from: 0, to: 3 } },
    'Bbm7':   { frets: [1, 1, 1, 1], barre: { fret: 1, from: 0, to: 3 } },
    'Bbmaj7': { frets: [3, 2, 1, 0] }
  };

  // Movable barre templates for guitar — relative to a base fret.
  // 'E-shape' rooted on low E string, 'A-shape' rooted on A string.
  // offsets: per string fret offset (0 = barre fret), null = muted.
  var GUITAR_ESHAPE = {
    '':     [0, 2, 2, 1, 0, 0],
    'm':    [0, 2, 2, 0, 0, 0],
    '7':    [0, 2, 0, 1, 0, 0],
    'm7':   [0, 2, 0, 0, 0, 0],
    'maj7': [0, 2, 1, 1, 0, 0]
  };
  var GUITAR_ASHAPE = {
    '':     [null, 0, 2, 2, 2, 0],
    'm':    [null, 0, 2, 2, 1, 0],
    '7':    [null, 0, 2, 0, 2, 0],
    'm7':   [null, 0, 2, 0, 1, 0],
    'maj7': [null, 0, 2, 1, 2, 0]
  };

  var SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  var FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];

  function pcOfNote(name) {
    var i = SHARP.indexOf(name);
    if (i >= 0) return i;
    i = FLAT.indexOf(name);
    return i; // -1 if unknown
  }

  // Map a quality/suffix to one of our dictionary keys (best effort).
  function suffixKey(suffix) {
    var s = (suffix || '').trim();
    var map = {
      '': '', 'maj': '', 'M': '',
      'm': 'm', 'min': 'm', '-': 'm',
      '7': '7', 'dom7': '7',
      'maj7': 'maj7', 'M7': 'maj7', 'Δ': 'maj7',
      'm7': 'm7', 'min7': 'm7',
      'sus4': 'sus4', 'sus': 'sus4',
      'sus2': 'sus2',
      '6': '6', 'maj6': '6',
      'm6': 'm6', 'min6': 'm6',
      'dim': 'dim', '°': 'dim', 'm7b5': 'dim'
    };
    if (map.hasOwnProperty(s)) return map[s];
    return s;
  }

  // Get a canonical parse without throwing. Falls back to a local parser
  // if ChordEngine is unavailable (shouldn't happen at runtime).
  function safeParse(sym) {
    try {
      if (window.ChordEngine && typeof window.ChordEngine.parse === 'function') {
        var p = window.ChordEngine.parse(sym);
        if (p) return p;
      }
    } catch (e) { /* ignore */ }
    return localParse(sym);
  }

  function safePcs(sym) {
    try {
      if (window.ChordEngine && typeof window.ChordEngine.pcs === 'function') {
        var arr = window.ChordEngine.pcs(sym);
        if (arr && arr.length) return arr;
      }
    } catch (e) { /* ignore */ }
    var p = safeParse(sym);
    if (p && p.pcs) return p.pcs;
    if (p) {
      return [(p.rootPc + 0) % 12, (p.rootPc + 4) % 12, (p.rootPc + 7) % 12];
    }
    return [];
  }

  // Minimal local parser — only used if ChordEngine missing.
  function localParse(sym) {
    if (!sym || typeof sym !== 'string') return null;
    var m = sym.match(/^([A-G][#b]?)(.*)$/);
    if (!m) return null;
    var root = m[1];
    var rest = m[2] || '';
    var bass = null, bassPc = null;
    var slash = rest.indexOf('/');
    if (slash >= 0) {
      bass = rest.slice(slash + 1);
      rest = rest.slice(0, slash);
      bassPc = pcOfNote(bass);
    }
    var rootPc = pcOfNote(root);
    if (rootPc < 0) return null;
    var quals = {
      '': [0, 4, 7], 'm': [0, 3, 7], '7': [0, 4, 7, 10],
      'maj7': [0, 4, 7, 11], 'm7': [0, 3, 7, 10],
      'm7b5': [0, 3, 6, 10], 'dim': [0, 3, 6], 'aug': [0, 4, 8],
      '6': [0, 4, 7, 9], 'm6': [0, 3, 7, 9], 'sus2': [0, 2, 7],
      'sus4': [0, 5, 7], '9': [0, 4, 7, 10, 2], 'add9': [0, 4, 7, 2],
      'm9': [0, 3, 7, 10, 2]
    };
    var iv = quals[rest] || [0, 4, 7];
    var pcs = iv.map(function (x) { return (rootPc + x) % 12; });
    return {
      root: root, rootPc: rootPc, quality: rest, suffix: rest,
      bass: bass, bassPc: bassPc, intervals: iv, pcs: pcs, raw: sym
    };
  }

  // ============================================================
  //  SVG helpers
  // ============================================================
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ============================================================
  //  Voicing resolution for fretted instruments
  //  Returns: { frets:[...], barre:{fret,from,to}|null, base:int, approx:bool }
  //  base = lowest displayed fret number (for position label)
  // ============================================================

  function lookupOpen(dict, root, sufKey) {
    var key = root + sufKey;
    if (dict[key]) return cloneShape(dict[key]);
    // Try enharmonic equivalent for root
    var pc = pcOfNote(root);
    if (pc >= 0) {
      var alt = (SHARP[pc] === root) ? FLAT[pc] : SHARP[pc];
      if (alt !== root && dict[alt + sufKey]) return cloneShape(dict[alt + sufKey]);
    }
    return null;
  }

  function cloneShape(s) {
    return {
      frets: s.frets.slice(),
      barre: s.barre ? { fret: s.barre.fret, from: s.barre.from, to: s.barre.to } : null
    };
  }

  // Derive a guitar movable barre shape.
  function guitarMovable(rootPc, sufKey) {
    // E-shape root pitch on open low-E string = E (pc 4).
    var tplE = GUITAR_ESHAPE[sufKey];
    if (tplE) {
      var fretE = ((rootPc - 4) % 12 + 12) % 12;
      if (fretE === 0) fretE = 12; // avoid open-position barre at nut for movable
      var frets = tplE.map(function (o) { return o === null ? -1 : fretE + o; });
      return { frets: frets, barre: { fret: fretE, from: 0, to: 5 }, base: fretE };
    }
    return null;
  }

  function guitarMovableA(rootPc, sufKey) {
    var tplA = GUITAR_ASHAPE[sufKey];
    if (tplA) {
      // A-shape root on A string (pc 9).
      var fretA = ((rootPc - 9) % 12 + 12) % 12;
      if (fretA === 0) fretA = 12;
      var frets = tplA.map(function (o) { return o === null ? -1 : fretA + o; });
      return { frets: frets, barre: { fret: fretA, from: 1, to: 5 }, base: fretA };
    }
    return null;
  }

  // Derive ukulele movable shape: shift the canonical C-rooted (or other) shape.
  // We use the C-shape templates for the quality if present and shift up.
  var UKE_CSHAPE = {
    '':     { frets: [0, 0, 0, 3], rootPc: 0 },
    'm':    { frets: [0, 3, 3, 3], rootPc: 0 },
    '7':    { frets: [0, 0, 0, 1], rootPc: 0 },
    'm7':   { frets: [3, 3, 3, 3], rootPc: 0 },
    'maj7': { frets: [0, 0, 0, 2], rootPc: 0 }
  };

  function ukeMovable(rootPc, sufKey) {
    var tpl = UKE_CSHAPE[sufKey];
    if (!tpl) return null;
    var shift = ((rootPc - tpl.rootPc) % 12 + 12) % 12;
    if (shift === 0) return null; // C itself, should have been in dict
    var frets = tpl.frets.map(function (f) { return f + shift; });
    var barre = null;
    var minPlayed = Math.min.apply(null, frets);
    if (minPlayed > 0) barre = { fret: minPlayed, from: 0, to: 3 };
    return { frets: frets, barre: barre, base: minPlayed };
  }

  // Best-effort dots from chord-tone pitch classes on open strings.
  // tuning = pc of each open string (low->high).
  function approxFromPcs(tuning, pcs) {
    var frets = [];
    for (var s = 0; s < tuning.length; s++) {
      var openPc = tuning[s];
      var best = -1;
      // find lowest fret 0..4 that lands on a chord tone
      for (var f = 0; f <= 4; f++) {
        if (pcs.indexOf((openPc + f) % 12) >= 0) { best = f; break; }
      }
      frets.push(best);
    }
    return { frets: frets, barre: null, base: 0, approx: true };
  }

  var GUITAR_TUNING = [4, 9, 2, 7, 11, 4];   // E A D G B E
  var UKE_TUNING = [7, 0, 4, 9];             // G C E A

  function resolveVoicing(instrument, parsed) {
    var dict = instrument === 'ukulele' ? UKE_OPEN : GUITAR_OPEN;
    var tuning = instrument === 'ukulele' ? UKE_TUNING : GUITAR_TUNING;
    var sufKey = suffixKey(parsed.suffix);

    // 1) curated open shape
    var v = lookupOpen(dict, parsed.root, sufKey);
    if (v) {
      v.base = minNonZero(v.frets);
      v.approx = false;
      return v;
    }

    // 2) movable barre
    var mv = null;
    if (instrument === 'guitar') {
      mv = guitarMovable(parsed.rootPc, sufKey) || guitarMovableA(parsed.rootPc, sufKey);
    } else {
      mv = ukeMovable(parsed.rootPc, sufKey);
    }
    if (mv) { mv.approx = false; return mv; }

    // 3) best-effort dots from pcs
    var pcs = (parsed.pcs && parsed.pcs.length) ? parsed.pcs : safePcs(parsed.raw || '');
    return approxFromPcs(tuning, pcs);
  }

  function minNonZero(frets) {
    var min = 99;
    for (var i = 0; i < frets.length; i++) {
      if (frets[i] > 0 && frets[i] < min) min = frets[i];
    }
    return min === 99 ? 1 : min;
  }

  // ============================================================
  //  Render fretboard (guitar / ukulele)
  // ============================================================
  function renderFretboard(instrument, sym, opts) {
    opts = opts || {};
    var parsed = safeParse(sym);
    var nStrings = instrument === 'ukulele' ? 4 : 6;
    var v;
    if (parsed) {
      v = resolveVoicing(instrument, parsed);
    } else {
      // unparseable: empty grid w/ message
      v = { frets: new Array(nStrings).fill(-1), barre: null, base: 1, approx: true };
    }

    var frets = v.frets;
    // Determine fret window (number of frets shown) and starting fret.
    var played = frets.filter(function (f) { return f > 0; });
    var maxFret = played.length ? Math.max.apply(null, played) : 0;
    var minFret = played.length ? Math.min.apply(null, played) : 0;
    var FRETS = 5;
    var startFret = 1;
    if (maxFret > FRETS) {
      startFret = minFret; // shift window up the neck
    }
    var span = Math.max(FRETS, maxFret - startFret + 1);
    if (span > 6) span = 6;
    FRETS = span < 4 ? 4 : span;

    var width = opts.width || (instrument === 'ukulele' ? 130 : 150);
    var padL = 22, padR = 16, padT = 30, padB = 18;
    var boxW = width - padL - padR;
    var stringGap = boxW / (nStrings - 1);
    var fretGap = 26;
    var boxH = fretGap * FRETS;
    var height = padT + boxH + padB + 14;

    var x0 = padL;
    var y0 = padT;

    var parts = [];
    parts.push('<svg xmlns="http://www.w3.org/2000/svg" width="' + width +
      '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height +
      '" font-family="' + FONT + '">');

    // Title (chord name)
    parts.push('<text x="' + (width / 2) + '" y="16" fill="' + COL.text +
      '" font-size="14" font-weight="600" text-anchor="middle">' +
      esc(sym) + '</text>');

    // Nut (thick) only if starting at fret 1
    if (startFret === 1) {
      parts.push('<rect x="' + x0 + '" y="' + (y0 - 3) + '" width="' + boxW +
        '" height="4" fill="' + COL.string + '"/>');
    } else {
      // position label on the left
      parts.push('<text x="' + (x0 - 8) + '" y="' + (y0 + fretGap - 9) +
        '" fill="' + COL.text + '" font-size="11" text-anchor="end">' +
        startFret + 'fr</text>');
    }

    // Fret lines (horizontal)
    for (var f = 0; f <= FRETS; f++) {
      var y = y0 + f * fretGap;
      parts.push('<line x1="' + x0 + '" y1="' + y + '" x2="' + (x0 + boxW) +
        '" y2="' + y + '" stroke="' + COL.grid + '" stroke-width="1"/>');
    }
    // Strings (vertical)
    for (var s = 0; s < nStrings; s++) {
      var x = x0 + s * stringGap;
      parts.push('<line x1="' + x + '" y1="' + y0 + '" x2="' + x +
        '" y2="' + (y0 + boxH) + '" stroke="' + COL.string + '" stroke-width="1"/>');
    }

    // Barre
    if (v.barre) {
      var br = v.barre;
      var brRow = br.fret - startFret; // 0-based fret row
      if (brRow >= 0 && brRow < FRETS) {
        var bx1 = x0 + br.from * stringGap;
        var bx2 = x0 + br.to * stringGap;
        var by = y0 + brRow * fretGap + fretGap / 2;
        parts.push('<rect x="' + (bx1 - 6) + '" y="' + (by - 7) + '" width="' +
          (bx2 - bx1 + 12) + '" height="14" rx="7" fill="' + COL.dot +
          '" opacity="0.92"/>');
      }
    }

    // Open / muted markers above nut + dots
    for (var si = 0; si < nStrings; si++) {
      var fr = frets[si];
      var sx = x0 + si * stringGap;
      if (fr === -1 || fr === undefined) {
        // muted x
        parts.push('<text x="' + sx + '" y="' + (y0 - 6) + '" fill="' + COL.muted +
          '" font-size="12" text-anchor="middle">×</text>');
      } else if (fr === 0) {
        // open o
        parts.push('<circle cx="' + sx + '" cy="' + (y0 - 9) + '" r="4" fill="none" stroke="' +
          COL.string + '" stroke-width="1.4"/>');
      } else {
        var row = fr - startFret;
        if (row < 0 || row >= FRETS) continue;
        // skip drawing dot if it's part of the barre at same fret (still show finger dots above barre)
        var cy = y0 + row * fretGap + fretGap / 2;
        var isBarreFret = v.barre && fr === v.barre.fret && si >= v.barre.from && si <= v.barre.to;
        if (isBarreFret) continue; // covered by barre rect
        parts.push('<circle cx="' + sx + '" cy="' + cy + '" r="7" fill="' + COL.dot + '"/>');
      }
    }

    // approx label
    if (v.approx) {
      parts.push('<text x="' + (width / 2) + '" y="' + (height - 3) +
        '" fill="' + COL.muted + '" font-size="9" text-anchor="middle">voicing approx</text>');
    }

    parts.push('</svg>');
    return parts.join('');
  }

  // ============================================================
  //  Render piano (~2 octaves)
  // ============================================================
  function renderPiano(sym, opts) {
    opts = opts || {};
    var parsed = safeParse(sym);
    var pcs = (parsed && parsed.pcs && parsed.pcs.length) ? parsed.pcs.slice() : safePcs(sym);
    var pcSet = {};
    pcs.forEach(function (p) { pcSet[((p % 12) + 12) % 12] = true; });
    var rootPc = parsed ? parsed.rootPc : (pcs.length ? pcs[0] : -1);
    var bassPc = (parsed && parsed.bassPc != null) ? parsed.bassPc : null;

    var OCT = 2;
    var whitePerOct = 7;
    var totalWhite = OCT * whitePerOct + 1; // include final C
    var width = opts.width || 220;
    var padT = 26, padB = 6, padX = 4;
    var wkW = (width - padX * 2) / totalWhite;
    var wkH = 70;
    var bkW = wkW * 0.62;
    var bkH = wkH * 0.62;
    var height = padT + wkH + padB;

    // white key semitone offsets within an octave
    var whiteSemis = [0, 2, 4, 5, 7, 9, 11];
    // black key: which white-key index it sits after, and its semitone
    var blackAfter = [
      { after: 0, semi: 1 },
      { after: 1, semi: 3 },
      { after: 3, semi: 6 },
      { after: 4, semi: 8 },
      { after: 5, semi: 10 }
    ];

    var parts = [];
    parts.push('<svg xmlns="http://www.w3.org/2000/svg" width="' + width +
      '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height +
      '" font-family="' + FONT + '">');
    parts.push('<text x="' + (width / 2) + '" y="16" fill="' + COL.text +
      '" font-size="14" font-weight="600" text-anchor="middle">' + esc(sym) + '</text>');

    function fillFor(pc) {
      if (pc === rootPc) return COL.rootHi;
      if (bassPc != null && pc === bassPc) return COL.rootHi;
      if (pcSet[pc]) return COL.keyHi;
      return null;
    }

    // Draw white keys
    var wi = 0;
    for (var o = 0; o < OCT; o++) {
      for (var k = 0; k < whitePerOct; k++) {
        var pc = whiteSemis[k];
        var x = padX + wi * wkW;
        var hl = fillFor(pc);
        var fill = hl || COL.whiteKey;
        parts.push('<rect x="' + x.toFixed(2) + '" y="' + padT + '" width="' + wkW.toFixed(2) +
          '" height="' + wkH + '" fill="' + fill + '" stroke="' + COL.whiteKeyEdge +
          '" stroke-width="1"/>');
        wi++;
      }
    }
    // final C
    (function () {
      var x = padX + wi * wkW;
      var hl = fillFor(0);
      var fill = hl || COL.whiteKey;
      parts.push('<rect x="' + x.toFixed(2) + '" y="' + padT + '" width="' + wkW.toFixed(2) +
        '" height="' + wkH + '" fill="' + fill + '" stroke="' + COL.whiteKeyEdge +
        '" stroke-width="1"/>');
    })();

    // Draw black keys on top
    for (var oo = 0; oo < OCT; oo++) {
      var base = oo * whitePerOct;
      for (var b = 0; b < blackAfter.length; b++) {
        var ba = blackAfter[b];
        var wcenter = padX + (base + ba.after + 1) * wkW;
        var bx = wcenter - bkW / 2;
        var pcb = ba.semi;
        var hlb = fillFor(pcb);
        var fillb = hlb || COL.blackKey;
        parts.push('<rect x="' + bx.toFixed(2) + '" y="' + padT + '" width="' + bkW.toFixed(2) +
          '" height="' + bkH.toFixed(2) + '" fill="' + fillb + '" stroke="#000" stroke-width="1" rx="1"/>');
      }
    }

    parts.push('</svg>');
    return parts.join('');
  }

  // ============================================================
  //  Public API
  // ============================================================
  var LABELS = { guitar: 'Chitarra', ukulele: 'Ukulele', piano: 'Piano' };

  window.Instruments = {
    LIST: ['guitar', 'ukulele', 'piano'],
    label: function (id) {
      return LABELS[id] || id;
    },
    render: function (instrument, sym, opts) {
      try {
        if (instrument === 'piano') return renderPiano(sym, opts);
        if (instrument === 'guitar' || instrument === 'ukulele') {
          return renderFretboard(instrument, sym, opts);
        }
        // unknown instrument -> default to guitar
        return renderFretboard('guitar', sym, opts);
      } catch (e) {
        // never throw: return a minimal valid svg
        var w = (opts && opts.width) || 140;
        return '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="40" ' +
          'font-family="' + FONT + '"><text x="' + (w / 2) + '" y="24" fill="' + COL.text +
          '" font-size="12" text-anchor="middle">' + esc(sym || '') + ' — voicing n/d</text></svg>';
      }
    }
  };
})();
