# ChordLab — Contratto condiviso tra moduli

App single-page, **vanilla JS**, nessun build step. Tre file JS espongono oggetti
globali su `window`. Il file `index.html` li carica in quest'ordine:
`engine.js` → `instruments.js` → `songs.js` → script UI inline.

Tutto deve funzionare aprendo il file direttamente (`file://`), senza server.

---

## 1) engine.js  →  `window.ChordEngine`

Teoria musicale + trasposizione. Solo funzioni pure, niente DOM.

```js
ChordEngine.SHARP // ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
ChordEngine.FLAT  // ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B']

// Parsifica un simbolo accordo es. "F", "Em7", "C7", "Dm/C", "Gm6/Bb", "Bbmaj7", "A7sus4"
ChordEngine.parse(sym) => {
  root:   'C',          // nota fondamentale (con eventuale # / b)
  rootPc: 0,            // pitch class 0..11
  quality:'maj7',       // stringa qualità normalizzata
  suffix: 'maj7',       // suffisso così come va mostrato dopo la root (es '', 'm', '7', 'maj7', 'm7b5', 'sus4', '6', 'dim', 'aug', 'add9')
  bass:   'E' | null,   // nota di basso dello slash chord, o null
  bassPc: 4   | null,
  intervals: [0,4,7,11],// semitoni dei chord-tone rispetto alla root
  pcs:   [0,4,7,11],    // pitch class assolute dei chord-tone (rootPc + intervals % 12), per il piano
  raw:   'Cmaj7'        // simbolo originale
} // oppure null se non parsificabile

// Trasposizione di n semitoni. useFlats=true => nomi con bemolli.
ChordEngine.transposeChord(sym, n, useFlats) => 'string'   // mantiene suffisso e slash

// Trasposizione "smart": sceglie # o b in base alla tonalità di arrivo
ChordEngine.transposeSmart(sym, semitones, targetKey) => 'string'

ChordEngine.noteName(pc, useFlats) => 'C#'|'Db' ...
ChordEngine.transposeKeyName(key, n) => 'string'   // es transpose della label tonalità
ChordEngine.keyUsesFlats(keyName) => bool           // F,Bb,Eb,Ab,Db,Gb e relative minori => true
ChordEngine.pcs(sym) => [int...]                    // alias chord-tone pitch classes (per piano)
```

Qualità da supportare almeno: maggiore (''), `m`, `7`, `maj7`/`M7`, `m7`, `m7b5`,
`dim`/`°`, `aug`/`+`, `6`, `m6`, `sus2`, `sus4`, `9`, `add9`, `m9`. Sconosciute:
trattare come triade maggiore + conservare il suffisso testuale.

---

## 2) instruments.js  →  `window.Instruments`

Diagrammi/tablature semplificate. Può usare `ChordEngine`.

```js
Instruments.LIST // ['guitar','ukulele','piano']
Instruments.label(id) // 'Chitarra' | 'Ukulele' | 'Piano'

// Ritorna una STRINGA SVG (autonoma, con width/height) per il simbolo accordo dato.
// Deve gestire tutte le 12 root con qualità comuni. Per chitarra/ukulele usare
// forme aperte note + forme mobili (barré tipo E-shape / A-shape) derivate per
// trasposizione quando non c'è una forma aperta. Per piano: tastiera ~2 ottave
// con i chord-tone evidenziati (usa ChordEngine.pcs).
// Se proprio non trova una voicing: per chitarra/uke mostra i pallini calcolati
// o un messaggio "voicing n/d"; non lanciare eccezioni.
Instruments.render(instrument, sym, opts) => '<svg ...>...</svg>'
```

Stile coerente col tema dark (vedi variabili CSS sotto): sfondo trasparente,
linee chiare, pallini color accento `#c8a45a`, testo `#e8e8e8`.

---

## 3) songs.js  →  `window.SONGS`

```js
window.SONGS = [
  {
    id: 'yesterday',
    title: 'Yesterday',
    artist: 'The Beatles',
    year: '1965',
    key: 'F',                 // tonalità originale (root maggiore o 'Am' per minore)
    capo: 0,                  // opzionale
    tags: ['ballad','60s'],   // per ricerca
    sections: [
      { name: 'Intro',  bars: ['F'] },
      { name: 'Verse',  bars: ['F','Em7 A7','Dm','Dm/C','Bb','C7','F'] },
      { name: 'Bridge', bars: ['Em7 A7','Dm C/E Bb6','...'] },
      ...
    ]
  },
  ...
]
```

Regole `bars`: ogni elemento dell'array è **una misura**; può contenere 1+ accordi
separati da spazio. Usare i simboli accordo nel formato accettato da `ChordEngine.parse`.
`name` delle sezioni preferibilmente tra: Intro, Verse, Pre-Chorus, Chorus, Bridge,
Solo, Outro, Instrumental (la UI colora per tipo).

Inserire **Yesterday** completo e fedele + almeno 5 altri brani noti e semplici
(es. Knockin' on Heaven's Door, Let It Be, Wonderwall, Stand By Me, Hey Jude...),
ognuno con sezioni reali. Tonalità e accordi corretti.
