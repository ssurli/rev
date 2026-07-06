# SKILL — rev-bot v2: trading autonomo per piccoli capitali

Sistema di trading autonomo 24/7 per capitali **50–2000 €**, tax-aware per
residente fiscale italiano in **regime dichiarativo**.
Priorità: **sopravvivenza del capitale > rendimento**.

> ⚠️ Sistema sperimentale a scopo personale/educativo. Il trading
> automatizzato può amplificare le perdite. Nessuna garanzia di rendimento.
> Le decisioni fiscali restano responsabilità dell'utente.

---

## 1. Architettura

```
main.py (runner persistente: --loop, kill-switch a ogni ciclo)
│
├── DATA        agents/market_data, news_monitor, macro      → prezzi, news, macro
├── SIGNALS     agents/technical, sentiment, forecast, regime → score -1..+1 + confidence
│               • tecnico: EMA/RSI/MACD/ATR (pesi componibili, ENABLE_*)
│               • sentiment/forecast Claude: SEGNALE pesato, MAI trigger unico
│                 (prompt+risposta loggati in DB per audit)
│               • regime detector: trend_up | trend_down | range
├── RISK        agents/risk_manager + core/safety, costs, sizing
│               • cost gate, cooldown, max trade/giorno, max turnover
│               • risk per trade ≤ RISK_PER_TRADE_PCT, drawdown circuit-breaker
├── EXECUTION   core/order_router → RevolutXClient (crypto, TPSL nativo)
│                                 → AlpacaClient  (stock/ETF, modulo opzionale)
├── ACCOUNTING  core/ledger (fills → Quadro RT LIFO, RW/IVAFE, export annuale)
└── UI          ui/monitor.html (read-only, mobile-first) ← data/status.json
```

Osservabilità: `data/decisions.jsonl` (ogni decisione ordine/non-ordine in
JSON), `data/status.json` (feed dashboard), alert email SMTP.

---

## 2. Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # compila le variabili (vedi sotto)
```

### Chiavi e segreti (MAI nel repo)

**Revolut X (crypto — motore principale):**
1. Genera una coppia Ed25519:
   `openssl genpkey -algorithm ed25519 -out ~/secrets/revx_private.pem`
2. Registra la chiave pubblica nel pannello API di Revolut X.
3. Permessi restrittivi: `chmod 600 ~/secrets/revx_private.pem`
4. In `.env`: `REVOLUT_X_PRIVATE_KEY_PATH=/home/tuo_utente/secrets/revx_private.pem`

**Alpaca (stock/ETF frazionari — opzionale, disattivabile):** chiavi
in `.env` (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`). Se vuote, il modulo
resta inattivo.

Regole non negoziabili:
- `private.pem` e `.env` fuori dal repo (`.gitignore` li copre), permessi 0600;
- dove possibile (firewall PythonAnywhere / container), restringi l'egress
  di rete ai soli host: `api.revolut.com`, `paper-api.alpaca.markets`,
  `query1.finance.yahoo.com` e al tuo SMTP.

---

## 3. Run

```bash
python main.py                    # PAPER, un ciclo
python main.py --loop             # PAPER, ogni CYCLE_INTERVAL_MINUTES (default 30)
python -m backtest.run_backtest --symbol BTC-USD --period 2y --equity 200
python -m core.safety --status    # stato kill-switch / halt / HWM
```

Su PythonAnywhere: task "Always-on" con `python main.py --loop`
(oppure container: `CMD ["python", "main.py", "--loop"]`).

Dashboard mobile: servi `ui/monitor.html` e `data/status.json` con
qualsiasi static server **read-only** (la UI non può inviare ordini):
```bash
python -m http.server 8080   # poi apri /ui/monitor.html?src=/data/status.json
```

---

## 4. Controlli di rischio (letti a ogni ciclo)

| Controllo | Config (.env) | Default | Effetto |
|---|---|---|---|
| Cost gate | `COST_GATE_MAX_PCT` | 0.40% | blocca ordine se fee+½spread > X% del size |
| Min order | `MIN_ORDER_EUR` | 10 € | sotto il minimo → nessun ordine |
| Risk/trade | `RISK_PER_TRADE_PCT` | 1% | perdita max a stop ≤ 1% equity |
| Stop/TP | `ATR_STOP_MULT` / `ATR_TP_MULT` | 2 / 3 | TPSL nativo su ogni posizione |
| Cooldown | `TRADE_COOLDOWN_MINUTES` | 240 | no trade ripetuti sullo stesso asset |
| Max trade/giorno | `MAX_TRADES_PER_DAY` | 6 | anti-overtrading |
| Max turnover | `MAX_DAILY_TURNOVER_PCT` | 30% | volume giornaliero ≤ 30% equity |
| Circuit-breaker | `MAX_DRAWDOWN_HALT_PCT` | 10% | flat & halt sotto il HWM |
| Kill-switch | file `data/KILL` o env `KILL_SWITCH=1` | — | ciclo saltato |

**Kill-switch:** `python -m core.safety --kill` / `--resume`.
**Circuit-breaker:** quando scatta crea `data/HALT` e manda email; il bot
resta flat finché non sblocchi **manualmente**: `python -m core.safety --unlock`.

---

## 5. Procedura go-live (obbligatoria, in ordine)

1. **Backtest** su almeno 1–2 anni di candele per ogni asset tradato:
   `python -m backtest.run_backtest --symbol BTC-USD --period 2y --out exports/bt_btc.json`
   Valuta: Sharpe, max drawdown, hit rate, profit factor, **costi totali**.
   Se i costi mangiano il rendimento con il tuo capitale, fermati qui.
2. **Paper trading** per almeno 2–4 settimane (`TRADING_MODE=paper`, default).
   Controlla `data/decisions.jsonl`: il cost-gate deve scattare quando previsto.
3. **Doppia conferma LIVE** (entrambe, altrimenti fallback automatico a paper):
   - env: `LIVE_TRADING_CONFIRM=YES`
   - CLI: `python main.py --mode live --confirm-live --loop`
4. **Hard-cap capitale**: `LIVE_MAX_CAPITAL_EUR` (default 500 €). Se l'equity
   supera il cap, il LIVE viene rifiutato.
5. Verifica alert email attivi (`SMTP_HOST`, `ALERT_EMAIL_TO`).

---

## 6. Fiscale (regime dichiarativo)

Ogni fill è registrato nel ledger (`fills`): timestamp UTC, asset, side,
qty, prezzo, fee, **controvalore EUR al cambio del momento**.

Export annuale per il commercialista:
```bash
python -m core.ledger --year 2025 --mode live --out exports/
```
Genera:
- `fills_2025.csv` — ledger completo;
- `quadro_rt_2025.csv/json` — plus/minusvalenze realizzate, metodo **LIFO**
  (metodo previsto per le cripto-attività; configurato in `TAX_LOT_METHOD`,
  da mantenere coerente tra gli anni), minusvalenze compensabili nei 4 anni
  successivi;
- `quadro_rw_2025.json` — giacenze di fine anno per monitoraggio RW e
  imposta di bollo 2‰ (sostituire il controvalore proxy con il valore di
  mercato al 31/12 prima dell'invio).

> Supporto alla dichiarazione, **non consulenza fiscale**; verificare con
> commercialista.

---

## 7. Test

```bash
python -m pytest tests/ -q
```
Copertura: cost gate, sizing risk-based, kill-switch/circuit-breaker,
cooldown/limiti giornalieri, ledger LIFO/RT/RW, regime detector,
metriche e motore di backtest. **Da eseguire (verdi) prima di ogni
paper trading e go-live.**
