# Lessons Learned

## 2026-03-27 — Setup sistema multi-agente

### Dipendenze Python in ambienti limitati
- **Pattern**: `feedparser>=6.x` richiede `sgmllib3k` che non si compila su Python 3.11 in alcuni ambienti
- **Regola**: per parsing RSS, preferire `xml.etree.ElementTree` (stdlib) — zero dipendenze, sempre disponibile
- **Regola**: per yfinance, installare esplicitamente tutte le dipendenze transitive (numpy, pandas, pytz, curl_cffi<0.14, bs4, frozendict, peewee, multitasking) perché `--no-deps` bypassa il build error ma lascia import rotti

### Risk score e test
- **Pattern**: il test di risk score falliva su portafoglio vuoto perché la penalità diversificazione (`+10 per <2 tipi asset`) si applicava anche senza posizioni (insieme vuoto ha len=0 < 2)
- **Regola**: le penalità basate su assenza di posizioni devono essere condizionate su `if positions:`
- **Regola**: nei test di risk_manager, non pre-settare `risk_score` nello stato — il `run()` lo ricalcola sempre. Usare invece un portafoglio con posizioni reali che producano il risk score atteso

### Accesso repo GitHub
- **Pattern**: il tool MCP GitHub è limitato ai repo configurati per la sessione (`ssurli/ig`)
- **Regola**: se un file è in un repo non configurato, usare WebFetch per recuperarlo direttamente da raw.githubusercontent.com prima di dichiararlo inaccessibile
