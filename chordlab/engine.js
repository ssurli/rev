// engine.js — ChordLab Music Engine
// Vanilla JS, no dependencies, runs under file://. Pure music-theory functions.
(function () {
  'use strict';

  var SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  var FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];

  // Map a note name (with optional # or b, incl. double accidentals) to pitch class 0..11.
  var BASE_PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

  function noteToPc(note) {
    if (!note) return null;
    var letter = note.charAt(0).toUpperCase();
    if (!(letter in BASE_PC)) return null;
    var pc = BASE_PC[letter];
    for (var i = 1; i < note.length; i++) {
      var c = note.charAt(i);
      if (c === '#' || c === '♯') pc += 1;
      else if (c === 'b' || c === 'B' || c === '♭') pc -= 1;
      else break;
    }
    return ((pc % 12) + 12) % 12;
  }

  function noteName(pc, useFlats) {
    pc = ((pc % 12) + 12) % 12;
    return (useFlats ? FLAT : SHARP)[pc];
  }

  // Quality table: normalized quality => { suffix, intervals }
  // Order of detection matters; longer/more-specific suffixes checked first.
  // intervals are semitones above root.
  var QUALITIES = [
    // half-diminished
    { keys: ['m7b5', 'min7b5', 'm7-5', 'ø', 'o7b5'], quality: 'm7b5', suffix: 'm7b5', intervals: [0, 3, 6, 10] },
    // diminished 7
    { keys: ['dim7', '°7'], quality: 'dim7', suffix: 'dim7', intervals: [0, 3, 6, 9] },
    // diminished triad
    { keys: ['dim', '°'], quality: 'dim', suffix: 'dim', intervals: [0, 3, 6] },
    // augmented
    { keys: ['aug', '+'], quality: 'aug', suffix: 'aug', intervals: [0, 4, 8] },
    // major seventh
    { keys: ['maj7', 'M7', 'Maj7', 'ma7', '△7', 'Δ', 'Δ7'], quality: 'maj7', suffix: 'maj7', intervals: [0, 4, 7, 11] },
    { keys: ['maj9', 'M9'], quality: 'maj9', suffix: 'maj9', intervals: [0, 4, 7, 11, 14] },
    // minor extensions (check before plain 'm')
    { keys: ['m9', 'min9', '-9'], quality: 'm9', suffix: 'm9', intervals: [0, 3, 7, 10, 14] },
    { keys: ['m7', 'min7', '-7'], quality: 'm7', suffix: 'm7', intervals: [0, 3, 7, 10] },
    { keys: ['m6', 'min6', '-6'], quality: 'm6', suffix: 'm6', intervals: [0, 3, 7, 9] },
    { keys: ['madd9', 'maddd9'], quality: 'madd9', suffix: 'madd9', intervals: [0, 3, 7, 14] },
    // sus chords
    { keys: ['sus2'], quality: 'sus2', suffix: 'sus2', intervals: [0, 2, 7] },
    { keys: ['sus4', 'sus'], quality: 'sus4', suffix: 'sus4', intervals: [0, 5, 7] },
    { keys: ['7sus4', '7sus'], quality: '7sus4', suffix: '7sus4', intervals: [0, 5, 7, 10] },
    // dominants / extensions
    { keys: ['9'], quality: '9', suffix: '9', intervals: [0, 4, 7, 10, 14] },
    { keys: ['add9', 'add2'], quality: 'add9', suffix: 'add9', intervals: [0, 4, 7, 14] },
    { keys: ['6'], quality: '6', suffix: '6', intervals: [0, 4, 7, 9] },
    { keys: ['7'], quality: '7', suffix: '7', intervals: [0, 4, 7, 10] },
    // plain minor (after all m-prefixed extensions)
    { keys: ['m', 'min', '-'], quality: 'm', suffix: 'm', intervals: [0, 3, 7] }
  ];

  function findQuality(rest) {
    // rest is the suffix string after the root (already stripped of slash bass)
    if (rest === '' || rest == null) {
      return { quality: 'maj', suffix: '', intervals: [0, 4, 7] };
    }
    for (var i = 0; i < QUALITIES.length; i++) {
      var q = QUALITIES[i];
      for (var k = 0; k < q.keys.length; k++) {
        if (rest === q.keys[k]) {
          return { quality: q.quality, suffix: q.suffix, intervals: q.intervals.slice() };
        }
      }
    }
    // Unknown quality: treat chord-tones as major triad but keep textual suffix.
    return { quality: 'maj', suffix: rest, intervals: [0, 4, 7] };
  }

  // Extract a root note from the start of a string. Returns [rootStr, restStr] or null.
  function extractRoot(s) {
    if (!s) return null;
    var m = /^([A-Ga-g])([#b♯♭]*)/.exec(s);
    if (!m) return null;
    var root = m[1].toUpperCase() + m[2].replace(/♯/g, '#').replace(/♭/g, 'b');
    return [root, s.slice(m[0].length)];
  }

  function parse(sym) {
    if (typeof sym !== 'string') return null;
    var raw = sym;
    var s = sym.trim();
    if (s === '') return null;

    // Slash chord: split bass
    var bass = null, bassPc = null;
    var slashIdx = s.indexOf('/');
    var main = s;
    if (slashIdx !== -1) {
      var bassPart = s.slice(slashIdx + 1).trim();
      main = s.slice(0, slashIdx).trim();
      var be = extractRoot(bassPart);
      if (be) {
        bass = be[0];
        bassPc = noteToPc(bass);
      }
    }

    var re = extractRoot(main);
    if (!re) return null;
    var root = re[0];
    var rest = re[1].trim();
    var rootPc = noteToPc(root);
    if (rootPc == null) return null;

    var q = findQuality(rest);
    var intervals = q.intervals.slice();
    var pcs = intervals.map(function (iv) {
      return ((rootPc + iv) % 12 + 12) % 12;
    });

    return {
      root: root,
      rootPc: rootPc,
      quality: q.quality,
      suffix: q.suffix,
      bass: bass,
      bassPc: bassPc,
      intervals: intervals,
      pcs: pcs,
      raw: raw
    };
  }

  function pcs(sym) {
    var p = parse(sym);
    return p ? p.pcs.slice() : [];
  }

  function transposeChord(sym, n, useFlats) {
    var p = parse(sym);
    if (!p) return sym;
    var newRootPc = ((p.rootPc + n) % 12 + 12) % 12;
    var out = noteName(newRootPc, useFlats) + p.suffix;
    if (p.bass != null && p.bassPc != null) {
      var newBassPc = ((p.bassPc + n) % 12 + 12) % 12;
      out += '/' + noteName(newBassPc, useFlats);
    }
    return out;
  }

  // Relative-minor flat keys plus their major equivalents.
  // Flat major keys: F, Bb, Eb, Ab, Db, Gb, Cb
  // Their relative minors: Dm, Gm, Cm, Fm, Bbm, Ebm, Abm
  var FLAT_KEYS = {
    'F': true, 'Bb': true, 'Eb': true, 'Ab': true, 'Db': true, 'Gb': true, 'Cb': true,
    'DM': true, 'GM': true, 'CM': true, 'FM': true, 'BBM': true, 'EBM': true, 'ABM': true
  };

  function normalizeKey(keyName) {
    if (typeof keyName !== 'string') return '';
    var k = keyName.trim();
    // Normalize accidental glyphs
    k = k.replace(/♯/g, '#').replace(/♭/g, 'b');
    return k;
  }

  function keyUsesFlats(keyName) {
    var k = normalizeKey(keyName);
    if (k === '') return false;
    // Minor key? ends with 'm' (but not part of root name)
    var isMinor = /m$/.test(k) && k.length > 1 && !/^[A-G][#b]?$/.test(k);
    if (isMinor) {
      var minorKey = k.toUpperCase();
      return !!FLAT_KEYS[minorKey];
    }
    // Major key
    var majorKey = k.charAt(0).toUpperCase() + k.slice(1);
    return !!FLAT_KEYS[majorKey];
  }

  function transposeSmart(sym, semitones, targetKey) {
    var useFlats = keyUsesFlats(targetKey);
    return transposeChord(sym, semitones, useFlats);
  }

  function transposeKeyName(key, n) {
    var k = normalizeKey(key);
    if (k === '') return key;
    var isMinor = /m$/.test(k) && k.length > 1 && !/^[A-G][#b]?$/.test(k);
    var rootStr = isMinor ? k.slice(0, -1) : k;
    var re = extractRoot(rootStr);
    if (!re) return key;
    var pc = noteToPc(re[0]);
    if (pc == null) return key;
    var newPc = ((pc + n) % 12 + 12) % 12;
    // Choose spelling based on resulting key's flat-ness.
    var sharpName = noteName(newPc, false);
    var flatName = noteName(newPc, true);
    var candidate = (isMinor ? sharpName + 'm' : sharpName);
    var useFlats = keyUsesFlats(candidate) || keyUsesFlats(isMinor ? flatName + 'm' : flatName);
    var name = noteName(newPc, useFlats);
    return isMinor ? name + 'm' : name;
  }

  window.ChordEngine = {
    SHARP: SHARP,
    FLAT: FLAT,
    parse: parse,
    pcs: pcs,
    transposeChord: transposeChord,
    transposeSmart: transposeSmart,
    transposeKeyName: transposeKeyName,
    keyUsesFlats: keyUsesFlats,
    noteName: noteName
  };
})();
