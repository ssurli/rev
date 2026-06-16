# 🎼 ChordLab

App single-page (HTML+JS vanilla, **zero build, zero dipendenze**) che produce
schede accordi in stile *iReal Pro*: elenco accordi a misure, suddiviso per
**sezioni** (Intro / Verse / Chorus / Bridge / Solo / Outro), con
**trasposizione** di tonalità e **diagrammi/tablatura semplificata** per
**chitarra, ukulele e piano**. Apri `index.html` in qualsiasi browser
(funziona anche da `file://`).

## Funzioni
- 🔎 **Ricerca** brano per titolo / artista / tag nella sidebar.
- 🎚 **Trasposizione** ± semitoni con spelling intelligente (sceglie # o ♭ in
  base alla tonalità di arrivo). La label tonalità si aggiorna in tempo reale.
- 🎸 **Switch strumento**: chitarra · ukulele · piano. I diagrammi si
  ricalcolano per ogni accordo.
- 👆 **Click su un accordo** → popover con diagramma + note che lo compongono.
- 🖨 **Stampa** ottimizzata (nasconde UI, sfondo chiaro).
- 📱 Layout responsive con menu a scomparsa.

## Architettura (sviluppata con un team di agenti)

| File | Modulo | Ruolo |
|---|---|---|
| `engine.js` | `window.ChordEngine` | parsing accordi, scale, **trasposizione** |
| `instruments.js` | `window.Instruments` | diagrammi SVG chitarra/ukulele/piano |
| `songs.js` | `window.SONGS` | libreria brani a sezioni (dati aperti) |
| `index.html` | UI | ricerca, griglia misure, controlli, integrazione |

Il contratto delle API condivise è in [`CONTRACT.md`](./CONTRACT.md).

## Aggiungere un brano
Aggiungi un oggetto a `window.SONGS` in `songs.js`:

```js
{
  id: 'let-it-be', title: 'Let It Be', artist: 'The Beatles',
  year: '1970', key: 'C', capo: 0, tags: ['beatles'],
  sections: [
    { name: 'Verse',  bars: ['C', 'G', 'Am', 'F'] },
    { name: 'Chorus', bars: ['C', 'G', 'F', 'C'] }
  ]
}
```
Ogni elemento di `bars` è **una misura**; più accordi nella stessa misura si
separano con uno spazio (es. `'Dm/C Bbmaj7 C7'`). I simboli devono essere nel
formato di `ChordEngine.parse` (`F`, `Em7`, `A7`, `Dm/C`, `Bbmaj7`, `A7sus4`…).

## Nota sulla "ricerca sul web"
La richiesta originale prevedeva un agente che recupera la sequenza accordi da
internet. Lo **scraping di siti come Ultimate Guitar è contro i loro ToS** e
riguarda contenuti protetti da copyright, quindi *non* è implementato. La
ricerca attuale opera sulla **libreria locale aperta** (`songs.js`). Per
estendere a fonti legali (es. dataset open / API autorizzate) basta implementare
un adapter che restituisce un oggetto nello schema di `SONGS` e farne il push
nell'array — l'intera UI continua a funzionare senza modifiche.
