# 📊 Revolut Investment Manager

Sistema multi-agent (Claude Code) per monitoraggio e analisi del portafoglio Revolut Personal.

## ⚠️ Nota importante

Revolut Personal non espone API per l'esecuzione di ordini di trading.
Questo sistema usa la **Open Banking API** (sola lettura) per dati di conto e transazioni,
**Yahoo Finance** per i prezzi di mercato in tempo reale, e produce
**raccomandazioni operative** da eseguire manualmente nell'app Revolut.

## 🏗️ Struttura

```
rev/
├── CLAUDE.md                  # Prompt multi-agent per Claude Code
├── README.md
├── requirements.txt
├── .env.example               # Template credenziali
├── config.json                # Parametri di rischio personalizzati
├── watchlist.json             # Asset da monitorare
├── operations_log.jsonl       # Log decisioni e alert
└── src/
    ├── revolut_client.py      # Open Banking API wrapper
    ├── market_data.py         # Yahoo Finance wrapper
    ├── portfolio.py           # Analisi portafoglio
    └── risk_manager.py        # Regole di rischio
```

## 🚀 Setup

```bash
# 1. Clona il repo
git clone https://github.com/ssurli/rev.git
cd rev

# 2. Installa dipendenze
pip install -r requirements.txt

# 3. Configura credenziali
cp .env.example .env
# edita .env con le tue credenziali Revolut Open Banking

# 4. Personalizza profilo di rischio
# edita config.json

# 5. Avvia Claude Code
claude
```

## 🔑 Come ottenere credenziali Revolut Open Banking

1. Vai su https://developer.revolut.com
2. Registra una applicazione (Personal / Open Banking)
3. Completa il consent flow OAuth2
4. Copia `client_id`, `client_secret` nel tuo `.env`

## 📋 Comandi disponibili in Claude Code

| Comando | Descrizione |
|---|---|
| `status` | Snapshot portafoglio completo |
| `briefing` | Briefing giornaliero mercati |
| `analizza AAPL` | Analisi approfondita asset |
| `watchlist` | Gestisci watchlist |
| `rischio` | Analisi rischio portafoglio |
| `ribilancia` | Suggerimento ribilanciamento |
| `report` | Report settimanale performance |
| `news AAPL` | Ultime news su un asset |
