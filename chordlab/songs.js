// ChordLab — songs.js
// Defines window.SONGS, an array of song objects per CONTRACT.md section 3.
// Chord symbols use the ChordEngine format (e.g. F, Em7, A7, Dm/C, Bbmaj7, A7sus4).
window.SONGS = [
  {
    id: 'yesterday',
    title: 'Yesterday',
    artist: 'The Beatles',
    year: '1965',
    key: 'F',
    capo: 0,
    tags: ['ballad', '60s', 'beatles', 'acoustic'],
    sections: [
      { name: 'Intro', bars: ['F', 'F'] },
      {
        name: 'Verse',
        bars: ['F', 'Em7 A7', 'Dm', 'Dm/C Bbmaj7 C7', 'F Em', 'Dm7 G7', 'Bb F']
      },
      {
        name: 'Bridge',
        bars: ['Em7 A7', 'Dm C Bb Dm/A', 'Gm7 C7', 'F F7', 'Em7 A7', 'Dm C Bb Dm/A', 'Gm7 C7', 'F']
      },
      {
        name: 'Verse',
        bars: ['F', 'Em7 A7', 'Dm', 'Dm/C Bbmaj7 C7', 'F Em', 'Dm7 G7', 'Bb F']
      },
      {
        name: 'Outro',
        bars: ['F/C G7/B', 'Bb F']
      }
    ]
  },
  {
    id: 'knockin-heavens-door',
    title: "Knockin' on Heaven's Door",
    artist: 'Bob Dylan',
    year: '1973',
    key: 'G',
    capo: 0,
    tags: ['folk', 'rock', '70s', 'classic'],
    sections: [
      {
        name: 'Verse',
        bars: ['G', 'D', 'Am', 'Am', 'G', 'D', 'C', 'C']
      },
      {
        name: 'Chorus',
        bars: ['G', 'D', 'C', 'C', 'G', 'D', 'C', 'C']
      }
    ]
  },
  {
    id: 'let-it-be',
    title: 'Let It Be',
    artist: 'The Beatles',
    year: '1970',
    key: 'C',
    capo: 0,
    tags: ['ballad', 'beatles', 'piano', '70s'],
    sections: [
      {
        name: 'Verse',
        bars: ['C', 'G', 'Am', 'F', 'C', 'G', 'F C', 'C']
      },
      {
        name: 'Chorus',
        bars: ['Am', 'G', 'F', 'C', 'C', 'G', 'F C', 'C']
      },
      {
        name: 'Outro',
        bars: ['C', 'G', 'F C', 'C']
      }
    ]
  },
  {
    id: 'stand-by-me',
    title: 'Stand By Me',
    artist: 'Ben E. King',
    year: '1961',
    key: 'A',
    capo: 0,
    tags: ['soul', 'oldies', '60s', 'classic'],
    sections: [
      {
        name: 'Intro',
        bars: ['A', 'A', 'F#m', 'F#m', 'D', 'E', 'A', 'A']
      },
      {
        name: 'Verse',
        bars: ['A', 'A', 'F#m', 'F#m', 'D', 'E', 'A', 'A']
      },
      {
        name: 'Chorus',
        bars: ['A', 'A', 'F#m', 'F#m', 'D', 'E', 'A', 'A']
      }
    ]
  },
  {
    id: 'wonderwall',
    title: 'Wonderwall',
    artist: 'Oasis',
    year: '1995',
    key: 'F#m',
    capo: 2,
    tags: ['britpop', 'rock', '90s', 'acoustic'],
    sections: [
      {
        name: 'Intro',
        bars: ['Em7', 'G', 'Dsus4', 'A7sus4']
      },
      {
        name: 'Verse',
        bars: ['Em7', 'G', 'Dsus4', 'A7sus4', 'Em7', 'G', 'Dsus4', 'A7sus4']
      },
      {
        name: 'Pre-Chorus',
        bars: ['C', 'D', 'A7sus4', 'A7sus4', 'C', 'D', 'G', 'G']
      },
      {
        name: 'Chorus',
        bars: ['Cadd9', 'Em7', 'G', 'Em7', 'Cadd9', 'Em7', 'G', 'G']
      }
    ]
  },
  {
    id: 'hey-jude',
    title: 'Hey Jude',
    artist: 'The Beatles',
    year: '1968',
    key: 'F',
    capo: 0,
    tags: ['ballad', 'beatles', '60s', 'anthem'],
    sections: [
      {
        name: 'Verse',
        bars: ['F', 'C', 'C7', 'F', 'Bb', 'F', 'C7', 'F']
      },
      {
        name: 'Bridge',
        bars: ['Bb', 'Bb', 'F', 'F', 'C7', 'C7', 'F', 'F']
      },
      {
        name: 'Outro',
        bars: ['F', 'Eb', 'Bb', 'F']
      }
    ]
  },
  {
    id: 'wish-you-were-here',
    title: 'Wish You Were Here',
    artist: 'Pink Floyd',
    year: '1975',
    key: 'G',
    capo: 0,
    tags: ['rock', 'acoustic', '70s', 'classic'],
    sections: [
      {
        name: 'Intro',
        bars: ['Em7', 'G', 'Em7', 'G', 'Em7', 'A7sus4', 'Em7', 'A7sus4', 'G']
      },
      {
        name: 'Verse',
        bars: ['C', 'D', 'Am', 'Am', 'G', 'D', 'C', 'C', 'Am', 'Am', 'G', 'G']
      }
    ]
  }
];
