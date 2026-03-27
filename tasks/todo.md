# Investment Bot — Task Tracker

## Sessione corrente

### [x] Setup iniziale sistema multi-agente
- [x] `core/state.py` — BotState TypedDict (LangGraph)
- [x] `core/config.py` — configurazione da .env
- [x] `core/db.py` — SQLite (news, sentiment, segnali, ordini, portfolio)
- [x] `core/revolut_client.py` — wrapper Revolut API + mock paper
- [x] `agents/news_monitor.py` — RSS + NewsAPI
- [x] `agents/sentiment.py` — Claude sentiment [-1,+1] per asset
- [x] `agents/market_data.py` — yfinance + Binance
- [x] `agents/strategy.py` — BUY/SELL/TRIM/HOLD + Claude borderline
- [x] `agents/risk_manager.py` — risk score 0-100
- [x] `agents/execution.py` — ordini Revolut (paper/live)
- [x] `agents/portfolio.py` — P&L, posizioni, snapshot
- [x] `agents/orchestrator.py` — LangGraph StateGraph
- [x] `main.py` — entry point + scheduler
- [x] `tests/test_paper_trading.py` — 5 test unitari (tutti passati)
- [x] `workflow_base.md` — aggiornato con template utente
- [x] `tasks/todo.md` e `tasks/lessons.md` — struttura task

### Review
- 5/5 test passati ✓
- Regole ereditate da `revolut_invest_v3.html` (maxPos=20%, minCash=15%, SL=-15%, TP=30%)
- Default: paper mode (nessuna API reale richiesta)
- Branch: `claude/investment-bot-system-JHxMs`

---

## Backlog

- [ ] Dashboard web (aggiornamento da `revolut_invest_v3.html`)
- [ ] Notifiche Telegram per ordini eseguiti
- [ ] Backtesting su dati storici (SQLite history)
- [ ] WebSocket Binance per prezzi real-time
- [ ] Integrazione Twitter/X per sentiment CEO
- [ ] Test integrazione Revolut sandbox (credenziali live)
