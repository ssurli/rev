# Investment Bot — Workflow Base

## Obiettivo
Sistema multi-agente per la gestione automatizzata di investimenti a partire da piccole somme (€10-100 per trade), basato su analisi predittiva del sentiment di notizie politico-economiche correlate a variazioni di prezzo su crypto, ETF e materie prime.

---

## Architettura Agenti

```
START
  │
  ▼
[portfolio_init]   Carica portafoglio da DB o Revolut API
  │
  ▼
[news_monitor]     Fetch notizie (NewsAPI + RSS) → filtra per keyword
  │
  ▼
[sentiment]        Claude scores sentiment [-1,+1] per asset
  │
  ▼
[market_data]      Prezzi real-time (yfinance + Binance)
  │
  ▼
[strategy]         Genera segnali BUY/SELL/TRIM/HOLD
  │
  ▼
[risk_manager]     Valida segnali, calcola risk score 0-100
  │
  ▼
[execution]        Piazza ordini (paper → simula | live → Revolut API)
  │
  ▼
[portfolio_update] Aggiorna posizioni, persiste snapshot su SQLite
  │
  ▼
END
```

---

## Regole di Trading (da revolut_invest_v3.html)

| Regola | Valore |
|--------|--------|
| Max peso singola posizione | 20% |
| Min riserva cash | 15% |
| Stop-loss | -15% P&L |
| Take-profit | +30% P&L |
| Max esposizione crypto | 15% |
| Max importo per trade | €50 |
| Portfolio minimo | €20 |

### Risk Score
| Condizione | Punti |
|------------|-------|
| Cash < 15% | +25 |
| Posizione > 20% (per ciascuna) | +15 |
| Crypto totale > 15% | +20 |
| < 2 tipi di asset | +10 |
| **Massimo** | **100** |

- **Basso** (verde): < 30
- **Medio** (arancio): 30–59
- **Alto** (rosso): ≥ 60

---

## Asset Monitorati (default)

| Simbolo | Tipo | Note |
|---------|------|------|
| BTC-USD | Crypto | Bitcoin |
| ETH-USD | Crypto | Ethereum |
| VOO | ETF | Vanguard S&P 500 |
| QQQ | ETF | Nasdaq 100 |
| GLD | Commodity | Gold ETF |

Modificabile in `.env` → variabile `ASSETS`.

---

## Fonti Notizie

| Fonte | Tipo | Costo |
|-------|------|-------|
| NewsAPI | REST API | Gratuito (100 req/day) |
| Reuters RSS | Feed | Gratuito |
| MarketWatch RSS | Feed | Gratuito |
| BBC Business RSS | Feed | Gratuito |
| FT RSS | Feed | Gratuito |

**Keyword monitorate**: `interest rate`, `tariff`, `bitcoin`, `crypto`, `trump`, `powell`, `lagarde`, `gold`, `s&p 500`, nomi CEO principali, ecc.

---

## Setup Rapido

```bash
# 1. Crea environment
python -m venv .venv && source .venv/bin/activate

# 2. Installa dipendenze
pip install -r requirements.txt

# 3. Configura variabili
cp .env.example .env
# → modifica ANTHROPIC_API_KEY, NEWSAPI_KEY, REVOLUT_* in .env

# 4. Test paper trading (nessuna API reale necessaria)
python main.py --mode paper

# 5. Loop automatico ogni 30 minuti (paper)
python main.py --mode paper --loop

# 6. Test unitari
pytest tests/ -v
```

---

## Modalità Operative

### Paper Trading (default)
- Nessuna chiamata a Revolut API
- Ordini simulati e salvati su SQLite
- Ideale per validare la logica prima di andare live

### Live Trading
- Richiede credenziali Revolut valide in `.env`
- Impostare `REVOLUT_SANDBOX=true` per usare la sandbox Revolut
- Impostare `TRADING_MODE=live` solo dopo test approfonditi in paper

---

## File Principali

| File | Ruolo |
|------|-------|
| `main.py` | Entry point, scheduler |
| `agents/orchestrator.py` | Grafo LangGraph |
| `agents/news_monitor.py` | Fetch notizie |
| `agents/sentiment.py` | Analisi sentiment (Claude) |
| `agents/market_data.py` | Prezzi real-time |
| `agents/strategy.py` | Segnali trading |
| `agents/risk_manager.py` | Validazione rischio |
| `agents/execution.py` | Esecuzione ordini |
| `agents/portfolio.py` | Gestione portafoglio |
| `core/state.py` | Schema stato LangGraph |
| `core/revolut_client.py` | Client Revolut API |
| `core/db.py` | Persistenza SQLite |
| `core/config.py` | Configurazione da .env |

---

## Prossimi Sviluppi

- [ ] Dashboard web (aggiornamento da `revolut_invest_v3.html`)
- [ ] Notifiche Telegram / email per ordini eseguiti
- [ ] Backtesting su dati storici
- [ ] Monitoraggio prezzi con WebSocket (Binance WS)
- [ ] Integrazione dati Twitter/X per sentiment CEO
