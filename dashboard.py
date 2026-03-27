"""Dashboard Streamlit — Investment Bot Monitor.

Avvio:
    streamlit run dashboard.py

Mostra:
  - Tab Portfolio : valore totale, P&L, risk score, allocazione
  - Tab Mercati   : grafico prezzi real-time per ogni asset
  - Tab Notizie   : feed notizie + sentiment per asset
  - Tab Ordini    : storico segnali e ordini eseguiti
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("TRADING_MODE", "paper")

import time
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from core.config import ASSETS, TRADING_MODE
from core.db import (
    get_latest_sentiment,
    get_portfolio_history,
    get_recent_news,
    get_recent_orders,
    get_recent_signals,
    init_db,
    load_latest_portfolio,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Investment Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📈 Investment Bot")
    st.caption(f"Modalità: **{'🟡 PAPER' if TRADING_MODE == 'paper' else '🔴 LIVE'}**")
    st.divider()

    if st.button("🔄 Aggiorna ora", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    auto_refresh = st.toggle("Auto-refresh (60s)", value=False)
    st.divider()

    selected_assets = st.multiselect(
        "Asset da mostrare",
        options=ASSETS,
        default=ASSETS,
    )
    st.divider()
    st.caption(f"Ultimo aggiornamento: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")

if auto_refresh:
    time.sleep(60)
    st.rerun()

# ---------------------------------------------------------------------------
# Data loaders (cached)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def load_market_data(symbols: list[str]) -> dict[str, dict]:
    result = {}
    if not symbols:
        return result
    try:
        data = yf.download(symbols, period="5d", interval="1h", progress=False, auto_adjust=True)
        if data.empty:
            return result
        close = data["Close"] if len(symbols) == 1 else data["Close"]
        for sym in symbols:
            try:
                col = sym if sym in close.columns else close.columns[0] if len(symbols) == 1 else None
                if col is None:
                    continue
                series = (close[col] if isinstance(close, pd.DataFrame) else close).dropna()
                if series.empty:
                    continue
                current = float(series.iloc[-1])
                prev = float(series.iloc[-2]) if len(series) > 1 else current
                prev_24 = float(series.iloc[max(0, len(series) - 25)])
                result[sym] = {
                    "price": current,
                    "change_1h_pct": (current - prev) / prev * 100 if prev else 0,
                    "change_24h_pct": (current - prev_24) / prev_24 * 100 if prev_24 else 0,
                    "history": series,
                }
            except Exception:
                continue
    except Exception as e:
        st.warning(f"Errore dati mercato: {e}")
    return result


@st.cache_data(ttl=60)
def load_portfolio_cached() -> dict | None:
    return load_latest_portfolio()


@st.cache_data(ttl=60)
def load_portfolio_history_cached() -> list[dict]:
    return get_portfolio_history(48)


@st.cache_data(ttl=60)
def load_news_cached() -> list[dict]:
    return get_recent_news(30)


@st.cache_data(ttl=60)
def load_sentiment_cached() -> list[dict]:
    return get_latest_sentiment()


@st.cache_data(ttl=60)
def load_orders_cached() -> list[dict]:
    return get_recent_orders(50)


@st.cache_data(ttl=60)
def load_signals_cached() -> list[dict]:
    return get_recent_signals(50)


# ---------------------------------------------------------------------------
# Load all data
# ---------------------------------------------------------------------------
portfolio = load_portfolio_cached()
history = load_portfolio_history_cached()
market = load_market_data(selected_assets)
news = load_news_cached()
sentiment = load_sentiment_cached()
orders = load_orders_cached()
signals = load_signals_cached()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_portfolio, tab_markets, tab_news, tab_orders = st.tabs(
    ["💼 Portfolio", "📊 Mercati", "📰 Notizie", "📋 Ordini"]
)

# ===========================================================================
# TAB 1 — PORTFOLIO
# ===========================================================================
with tab_portfolio:
    if portfolio is None:
        st.info("Nessun dato portfolio. Avvia `python main.py` per il primo ciclo.")
    else:
        total = portfolio.get("total_value_eur", 0)
        cash = portfolio.get("cash_eur", 0)
        risk_score = portfolio.get("risk_score", 0)
        risk_label = portfolio.get("risk_label", "Basso")
        positions = portfolio.get("positions", [])

        # KPI row
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💶 Valore totale", f"€{total:,.2f}")
        col2.metric("💵 Cash disponibile", f"€{cash:,.2f}", f"{cash/total*100:.1f}%" if total else "")

        risk_color = "🟢" if risk_score < 30 else ("🟡" if risk_score < 60 else "🔴")
        col3.metric(f"{risk_color} Risk Score", f"{risk_score}/100", risk_label)

        pnl_total = sum(p.get("pnl_pct", 0) * p.get("value_eur", 0) / 100 for p in positions)
        col4.metric("📈 P&L non realizzato", f"€{pnl_total:+.2f}")

        st.divider()

        col_left, col_right = st.columns([1, 1])

        # Allocazione pie chart
        with col_left:
            st.subheader("Allocazione")
            if positions:
                labels = [p["symbol"] for p in positions] + ["Cash"]
                values = [p["value_eur"] for p in positions] + [cash]
                fig = px.pie(
                    values=values, names=labels,
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set3,
                )
                fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nessuna posizione aperta.")

        # Posizioni tabella
        with col_right:
            st.subheader("Posizioni aperte")
            if positions:
                df = pd.DataFrame(positions)
                df = df[["symbol", "qty", "avg_price_eur", "current_price_eur", "value_eur", "pnl_pct", "asset_type"]]
                df.columns = ["Asset", "Qty", "Prezzo medio €", "Prezzo attuale €", "Valore €", "P&L %", "Tipo"]
                df["P&L %"] = df["P&L %"].apply(lambda x: f"{x:+.2f}%")
                df["Valore €"] = df["Valore €"].apply(lambda x: f"€{x:.2f}")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Nessuna posizione aperta.")

        # Portfolio history chart
        if history:
            st.subheader("Andamento portfolio")
            df_hist = pd.DataFrame(history)
            df_hist["created_at"] = pd.to_datetime(df_hist["created_at"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_hist["created_at"], y=df_hist["total_value_eur"],
                mode="lines+markers", name="Valore totale €",
                line=dict(color="#00cc88", width=2),
                fill="tozeroy", fillcolor="rgba(0,204,136,0.1)",
            ))
            fig.add_trace(go.Scatter(
                x=df_hist["created_at"], y=df_hist["cash_eur"],
                mode="lines", name="Cash €",
                line=dict(color="#6699ff", width=1.5, dash="dot"),
            ))
            fig.update_layout(
                height=280, margin=dict(t=10, b=10, l=10, r=10),
                legend=dict(orientation="h", y=1.1),
                xaxis_title="", yaxis_title="€",
            )
            st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# TAB 2 — MERCATI
# ===========================================================================
with tab_markets:
    if not market:
        st.info("Nessun dato di mercato. Attendi il prossimo ciclo o clicca Aggiorna.")
    else:
        # KPI cards per asset
        cols = st.columns(min(len(market), 5))
        for i, (sym, d) in enumerate(market.items()):
            with cols[i % len(cols)]:
                delta_color = "normal"
                st.metric(
                    label=sym,
                    value=f"${d['price']:,.2f}" if "USD" in sym or "=F" in sym else f"${d['price']:,.2f}",
                    delta=f"{d['change_24h_pct']:+.2f}% 24h",
                    delta_color="normal",
                )

        st.divider()

        # Grafico prezzi per asset selezionato
        asset_choice = st.selectbox("Seleziona asset per il grafico", options=list(market.keys()))
        if asset_choice and asset_choice in market:
            series = market[asset_choice]["history"]
            df_price = pd.DataFrame({"time": series.index, "price": series.values})
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_price["time"], y=df_price["price"],
                mode="lines", name=asset_choice,
                line=dict(color="#f0a500", width=2),
            ))
            fig.update_layout(
                title=f"{asset_choice} — ultimi 5 giorni (1h)",
                height=380,
                margin=dict(t=40, b=20, l=20, r=20),
                xaxis_title="", yaxis_title="Prezzo",
            )
            st.plotly_chart(fig, use_container_width=True)

        # Sentiment bar chart
        if sentiment:
            st.subheader("Sentiment attuale per asset")
            df_sent = pd.DataFrame(sentiment)[["symbol", "score"]]
            df_sent["colore"] = df_sent["score"].apply(lambda x: "Positivo" if x > 0 else ("Negativo" if x < 0 else "Neutro"))
            fig = px.bar(
                df_sent, x="symbol", y="score", color="colore",
                color_discrete_map={"Positivo": "#00cc88", "Negativo": "#ff4444", "Neutro": "#aaaaaa"},
                range_y=[-1, 1],
                labels={"symbol": "Asset", "score": "Sentiment Score"},
            )
            fig.add_hline(y=0.4, line_dash="dot", line_color="green", annotation_text="BUY soglia")
            fig.add_hline(y=-0.4, line_dash="dot", line_color="red", annotation_text="SELL soglia")
            fig.update_layout(height=280, margin=dict(t=20, b=20, l=20, r=20), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# TAB 3 — NOTIZIE
# ===========================================================================
with tab_news:
    col_news, col_sent = st.columns([2, 1])

    with col_news:
        st.subheader("Ultime notizie raccolte")
        if news:
            for item in news[:15]:
                with st.container():
                    st.markdown(f"**[{item['title']}]({item['url']})**")
                    st.caption(f"📡 {item['source']} · {item.get('published_at', '')[:16]}")
                    st.divider()
        else:
            st.info("Nessuna notizia. Avvia il bot per raccogliere dati.")

    with col_sent:
        st.subheader("Sentiment per asset")
        if sentiment:
            for s in sentiment:
                score = s["score"]
                emoji = "🟢" if score > 0.2 else ("🔴" if score < -0.2 else "⚪")
                bar = int(abs(score) * 10)
                direction = "▲" if score > 0 else ("▼" if score < 0 else "—")
                st.markdown(f"{emoji} **{s['symbol']}** {direction} `{score:+.2f}`")
                if s.get("headlines"):
                    with st.expander("Notizie correlate"):
                        for h in s["headlines"][:3]:
                            st.caption(f"• {h}")
        else:
            st.info("Nessun dato sentiment disponibile.")

# ===========================================================================
# TAB 4 — ORDINI
# ===========================================================================
with tab_orders:
    col_sig, col_ord = st.columns([1, 1])

    with col_sig:
        st.subheader("Segnali recenti")
        if signals:
            df_sig = pd.DataFrame(signals)
            df_sig["created_at"] = pd.to_datetime(df_sig["created_at"]).dt.strftime("%m-%d %H:%M")
            df_sig["validated"] = df_sig["validated"].apply(lambda x: "✅" if x else "⏳")
            df_sig["confidence"] = df_sig["confidence"].apply(lambda x: f"{x:.0%}")
            df_sig["sentiment"] = df_sig["sentiment"].apply(lambda x: f"{x:+.2f}")
            df_sig = df_sig.rename(columns={
                "created_at": "Ora", "symbol": "Asset", "action": "Azione",
                "confidence": "Conf.", "sentiment": "Sent.", "validated": "Val.",
            })
            st.dataframe(
                df_sig[["Ora", "Asset", "Azione", "Conf.", "Sent.", "Val."]],
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("Nessun segnale registrato.")

    with col_ord:
        st.subheader("Ordini eseguiti")
        if orders:
            df_ord = pd.DataFrame(orders)
            df_ord["created_at"] = pd.to_datetime(df_ord["created_at"]).dt.strftime("%m-%d %H:%M")
            df_ord["amount_eur"] = df_ord["amount_eur"].apply(lambda x: f"€{x:.2f}")
            df_ord["price_eur"] = df_ord["price_eur"].apply(lambda x: f"€{x:,.2f}")
            status_emoji = {"simulated": "🟡", "filled": "🟢", "rejected": "🔴", "submitted": "🔵"}
            df_ord["status"] = df_ord["status"].apply(lambda x: f"{status_emoji.get(x, '⚪')} {x}")
            df_ord = df_ord.rename(columns={
                "created_at": "Ora", "symbol": "Asset", "action": "Azione",
                "amount_eur": "Importo", "price_eur": "Prezzo", "status": "Stato", "mode": "Modo",
            })
            st.dataframe(
                df_ord[["Ora", "Asset", "Azione", "Importo", "Prezzo", "Stato", "Modo"]],
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("Nessun ordine eseguito.")
