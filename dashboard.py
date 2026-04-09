"""Dashboard Streamlit — Investment Bot Monitor.

Avvio:
    streamlit run dashboard.py

Mostra:
  - Tab Portfolio   : valore totale, P&L, risk score, allocazione
  - Tab Mercati     : grafico prezzi real-time per ogni asset
  - Tab Previsioni  : forecast multi-fattore + indicatori tecnici
  - Tab Notizie     : feed notizie + sentiment per asset
  - Tab Ordini      : storico segnali e ordini eseguiti
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Streamlit Cloud: leggi secrets e iniettali come env vars (sovrascrive .env)
# ---------------------------------------------------------------------------
try:
    import streamlit as _st_secrets
    for _k in ["ANTHROPIC_API_KEY", "NEWSAPI_KEY", "FRED_API_KEY", "TRADING_MODE"]:
        if _k in _st_secrets.secrets:
            os.environ[_k] = _st_secrets.secrets[_k]
except Exception:
    pass  # locale: usa .env normale

os.environ.setdefault("TRADING_MODE", "paper")

import time
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from core.config import ASSETS, TRADING_MODE, STOP_LOSS_PCT, TAKE_PROFIT_PCT, MAX_POSITION_PCT, MIN_CASH_PCT, MAX_TRADE_EUR
from core.db import (
    get_latest_forecasts,
    get_latest_macro,
    get_latest_sentiment,
    get_macro_history,
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
# Password protection (solo se DASHBOARD_PASSWORD è configurata nei secrets)
# ---------------------------------------------------------------------------
_pwd_required = os.environ.get("DASHBOARD_PASSWORD", "")
if _pwd_required:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🔐 Investment Bot — Accesso")
        pwd = st.text_input("Password", type="password")
        if st.button("Accedi"):
            if pwd == _pwd_required:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Password errata")
        st.stop()

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

    # --- Pannello SL/TP ---
    with st.expander("⚙️ Regole Stop Loss / Take Profit", expanded=False):
        sl = st.slider("Stop Loss %", min_value=-30, max_value=-1, value=int(STOP_LOSS_PCT), step=1)
        tp = st.slider("Take Profit %", min_value=5, max_value=100, value=int(TAKE_PROFIT_PCT), step=5)
        max_pos = st.slider("Max posizione %", min_value=5, max_value=50, value=int(MAX_POSITION_PCT), step=5)
        min_cash = st.slider("Min cash %", min_value=5, max_value=40, value=int(MIN_CASH_PCT), step=5)
        max_trade = st.number_input("Max trade €", min_value=5, max_value=500, value=int(MAX_TRADE_EUR), step=5)
        st.caption("ℹ️ Per rendere permanenti le modifiche, aggiorna il `.env`")
        st.code(
            f"STOP_LOSS_PCT={sl}\n"
            f"TAKE_PROFIT_PCT={tp}\n"
            f"MAX_POSITION_PCT={max_pos}\n"
            f"MIN_CASH_PCT={min_cash}\n"
            f"MAX_TRADE_EUR={max_trade}",
            language="ini",
        )

        # Visual summary
        st.markdown("**Strategia attiva:**")
        risk_color = "🔴" if abs(sl) > 20 else "🟡"
        reward_color = "🟢" if tp >= 30 else "🟡"
        st.markdown(
            f"{risk_color} SL: `{sl}%`  •  "
            f"{reward_color} TP: `+{tp}%`  •  "
            f"R/R: `1:{tp/abs(sl):.1f}`"
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
        # Fetch EUR/USD for conversion
        eur_usd = 1.10
        try:
            fx = yf.download("EURUSD=X", period="1d", interval="1h", progress=False, auto_adjust=True)
            if not fx.empty:
                eur_usd = float(fx["Close"].iloc[-1])
        except Exception:
            pass

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
                price_eur = current / eur_usd
                result[sym] = {
                    "price": current,
                    "price_eur": price_eur,
                    "eur_usd": eur_usd,
                    "change_1h_pct": (current - prev) / prev * 100 if prev else 0,
                    "change_24h_pct": (current - prev_24) / prev_24 * 100 if prev_24 else 0,
                    "history": series,
                    "history_eur": series / eur_usd,
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


@st.cache_data(ttl=60)
def load_forecasts_cached() -> list[dict]:
    return get_latest_forecasts()


@st.cache_data(ttl=300)
def load_macro_cached() -> list[dict]:
    return get_latest_macro()


@st.cache_data(ttl=300)
def load_macro_history_cached(indicator_id: str) -> list[dict]:
    return get_macro_history(indicator_id, limit=90)


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
forecasts_data = load_forecasts_cached()
macro_data = load_macro_cached()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_portfolio, tab_markets, tab_forecast, tab_macro, tab_news, tab_orders, tab_daytrading, tab_chat, tab_guide = st.tabs(
    ["💼 Portfolio", "📊 Mercati", "🔮 Previsioni", "🏦 Macro", "📰 Notizie", "📋 Ordini", "⚡ Day Trading", "💬 Analista AI", "📚 Guida"]
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
        # -----------------------------------------------------------------
        # Asset category mapping
        # -----------------------------------------------------------------
        _CATEGORIES: dict[str, str] = {
            # Crypto
            "BTC-USD": "🪙 Crypto", "ETH-USD": "🪙 Crypto", "BNB-USD": "🪙 Crypto",
            "SOL-USD": "🪙 Crypto", "XRP-USD": "🪙 Crypto", "ADA-USD": "🪙 Crypto",
            "DOGE-USD": "🪙 Crypto", "AVAX-USD": "🪙 Crypto",
            # ETF
            "VOO": "📦 ETF", "QQQ": "📦 ETF", "SPY": "📦 ETF", "IVV": "📦 ETF",
            "VTI": "📦 ETF", "TLT": "📦 ETF", "IEF": "📦 ETF", "SHY": "📦 ETF",
            "HYG": "📦 ETF", "ARKK": "📦 ETF", "EEM": "📦 ETF",
            "VWCE.DE": "📦 ETF", "CSPX.L": "📦 ETF", "IWDA.L": "📦 ETF",
            "EXS1.DE": "📦 ETF", "MEUD.PA": "📦 ETF",
            # Commodities
            "GLD": "🥇 Commodity", "SLV": "🥇 Commodity", "GDX": "🥇 Commodity",
            "USO": "🥇 Commodity", "CL=F": "🥇 Commodity", "GC=F": "🥇 Commodity",
            "SI=F": "🥇 Commodity", "NG=F": "🥇 Commodity",
            # Forex
            "EURUSD=X": "💱 Forex", "GBPUSD=X": "💱 Forex",
            "USDJPY=X": "💱 Forex", "USDCNY=X": "💱 Forex",
            # Indices
            "^GSPC": "📈 Indice", "^DJI": "📈 Indice", "^IXIC": "📈 Indice",
            "^FTSE": "📈 Indice", "^DAX": "📈 Indice", "^GDAXI": "📈 Indice",
            "^FCHI": "📈 Indice", "^STOXX50E": "📈 Indice",
            "^N225": "📈 Indice", "^HSI": "📈 Indice",
        }
        def _cat(sym: str) -> str:
            return _CATEGORIES.get(sym, "📊 Stock")

        # Build lookup dicts for forecast & sentiment
        _fc_map = {f["symbol"]: f for f in forecasts_data} if forecasts_data else {}
        _sent_map = {s["symbol"]: s["score"] for s in sentiment} if sentiment else {}

        # -----------------------------------------------------------------
        # Summary table — all assets at a glance
        # -----------------------------------------------------------------
        st.subheader("Panoramica mercati")
        rows = []
        for sym, d in market.items():
            fc = _fc_map.get(sym, {})
            sent_score = _sent_map.get(sym, None)
            direction = fc.get("direction", "—")
            dir_emoji = "🟢" if direction == "BULLISH" else ("🔴" if direction == "BEARISH" else "⚪")
            chg24 = d["change_24h_pct"]
            chg1h = d["change_1h_pct"]
            rows.append({
                "Asset": sym,
                "Categoria": _cat(sym),
                "Prezzo €": d.get("price_eur", d["price"]),
                "1h %": chg1h,
                "24h %": chg24,
                "Sentiment": sent_score if sent_score is not None else float("nan"),
                "Forecast": f"{dir_emoji} {direction}",
                "Score": fc.get("forecast_score", float("nan")),
            })
        df_summary = pd.DataFrame(rows)

        # Style helper
        def _color_pct(val):
            if pd.isna(val):
                return ""
            color = "#00cc88" if val > 0 else ("#ff4444" if val < 0 else "#aaaaaa")
            return f"color: {color}; font-weight: bold"

        def _color_score(val):
            if pd.isna(val):
                return ""
            color = "#00cc88" if val > 0.1 else ("#ff4444" if val < -0.1 else "#aaaaaa")
            return f"color: {color}"

        styled = (
            df_summary.style
            .format({
                "Prezzo €": lambda x: f"€{x:,.2f}",
                "1h %": lambda x: f"{x:+.2f}%" if not pd.isna(x) else "—",
                "24h %": lambda x: f"{x:+.2f}%" if not pd.isna(x) else "—",
                "Sentiment": lambda x: f"{x:+.2f}" if not pd.isna(x) else "—",
                "Score": lambda x: f"{x:+.3f}" if not pd.isna(x) else "—",
            })
            .map(_color_pct, subset=["1h %", "24h %"])
            .map(_color_score, subset=["Sentiment", "Score"])
        )
        st.dataframe(styled, use_container_width=True, hide_index=True, height=min(40 * len(rows) + 38, 520))

        st.divider()

        # -----------------------------------------------------------------
        # Group cards by category
        # -----------------------------------------------------------------
        by_cat: dict[str, list[str]] = {}
        for sym in market:
            by_cat.setdefault(_cat(sym), []).append(sym)

        for cat_name, cat_syms in by_cat.items():
            st.markdown(f"#### {cat_name}")
            cards_per_row = 5
            for chunk_start in range(0, len(cat_syms), cards_per_row):
                chunk = cat_syms[chunk_start:chunk_start + cards_per_row]
                cols = st.columns(len(chunk))
                for col, sym in zip(cols, chunk):
                    d = market[sym]
                    fc = _fc_map.get(sym, {})
                    price_eur = d.get("price_eur", d["price"])
                    chg24 = d["change_24h_pct"]
                    direction = fc.get("direction", "")
                    dir_emoji = " 🟢" if direction == "BULLISH" else (" 🔴" if direction == "BEARISH" else "")
                    sent = _sent_map.get(sym)
                    sent_str = f"  |  Sent: {sent:+.2f}" if sent is not None else ""
                    col.metric(
                        label=f"{sym}{dir_emoji}",
                        value=f"€{price_eur:,.2f}",
                        delta=f"{chg24:+.2f}% 24h",
                        delta_color="normal",
                        help=f"1h: {d['change_1h_pct']:+.2f}%{sent_str}",
                    )

        st.divider()

        # -----------------------------------------------------------------
        # Grafico dettaglio per asset selezionato
        # -----------------------------------------------------------------
        st.subheader("Grafico dettaglio")
        col_chart_sel, col_chart_info = st.columns([3, 1])
        with col_chart_sel:
            asset_choice = st.selectbox("Seleziona asset", options=list(market.keys()), key="market_asset_select")
        with col_chart_info:
            if asset_choice and asset_choice in market:
                d_sel = market[asset_choice]
                fc_sel = _fc_map.get(asset_choice, {})
                st.metric("Prezzo", f"€{d_sel.get('price_eur', d_sel['price']):,.2f}",
                          f"{d_sel['change_24h_pct']:+.2f}% 24h")
                if fc_sel:
                    dir_s = fc_sel.get("direction", "—")
                    dir_e = "🟢" if dir_s == "BULLISH" else ("🔴" if dir_s == "BEARISH" else "⚪")
                    st.caption(f"{dir_e} {dir_s} · conf {fc_sel.get('confidence', 0):.0%}")

        if asset_choice and asset_choice in market:
            series_eur = market[asset_choice].get("history_eur", market[asset_choice]["history"])
            df_price = pd.DataFrame({"time": series_eur.index, "price": series_eur.values})
            # Color line based on overall trend
            line_color = "#00cc88" if df_price["price"].iloc[-1] >= df_price["price"].iloc[0] else "#ff4444"
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_price["time"], y=df_price["price"],
                mode="lines", name=asset_choice,
                line=dict(color=line_color, width=2),
                fill="tozeroy",
                fillcolor=line_color.replace(")", ", 0.08)").replace("rgb", "rgba") if "rgb" in line_color else (
                    "rgba(0,204,136,0.08)" if line_color == "#00cc88" else "rgba(255,68,68,0.08)"
                ),
            ))
            # Add 24h moving average
            if len(df_price) >= 24:
                df_price["ma24"] = df_price["price"].rolling(24).mean()
                fig.add_trace(go.Scatter(
                    x=df_price["time"], y=df_price["ma24"],
                    mode="lines", name="MA 24h",
                    line=dict(color="#888888", width=1.2, dash="dot"),
                ))
            fc_sel = _fc_map.get(asset_choice, {})
            reasoning = fc_sel.get("reasoning", "")
            title_suffix = f" · {fc_sel.get('direction', '')} {fc_sel.get('forecast_score', ''):+.2f}" if fc_sel else ""
            fig.update_layout(
                title=f"{asset_choice} — 5 giorni (1h) — €{title_suffix}",
                height=380,
                margin=dict(t=40, b=20, l=20, r=20),
                xaxis_title="", yaxis_title="Prezzo €",
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig, use_container_width=True)
            if reasoning:
                st.caption(f"💬 Analisi bot: {reasoning}")

        # -----------------------------------------------------------------
        # Sentiment & forecast combined bar chart
        # -----------------------------------------------------------------
        if sentiment or forecasts_data:
            st.subheader("Sentiment vs Forecast score")
            all_syms = list({s["symbol"] for s in (sentiment or [])} |
                            {f["symbol"] for f in (forecasts_data or [])})
            sent_scores = [float(_sent_map.get(s) or 0) for s in all_syms]
            fc_scores = [float(_fc_map.get(s, {}).get("forecast_score") or 0) for s in all_syms]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name="Sentiment", x=all_syms, y=sent_scores,
                marker_color=["#00cc88" if v > 0 else "#ff4444" for v in sent_scores],
                opacity=0.7,
            ))
            fig.add_trace(go.Bar(
                name="Forecast", x=all_syms, y=fc_scores,
                marker_color=["#4a9eff" if v > 0 else "#ff8800" for v in fc_scores],
                opacity=0.7,
            ))
            fig.add_hline(y=0.35, line_dash="dot", line_color="green", annotation_text="BUY")
            fig.add_hline(y=-0.35, line_dash="dot", line_color="red", annotation_text="SELL")
            fig.update_layout(
                barmode="group", height=300,
                margin=dict(t=20, b=20, l=10, r=10),
                yaxis=dict(range=[-1, 1]),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# TAB 3 — PREVISIONI
# ===========================================================================
with tab_forecast:
    if not forecasts_data:
        st.info("Nessuna previsione disponibile. Avvia `python main.py` per generare forecasts.")
    else:
        st.subheader("Previsioni per asset")

        # Direction summary cards
        bullish = [f for f in forecasts_data if f["direction"] == "BULLISH"]
        bearish = [f for f in forecasts_data if f["direction"] == "BEARISH"]
        neutral = [f for f in forecasts_data if f["direction"] == "NEUTRAL"]
        c1, c2, c3 = st.columns(3)
        c1.metric("🟢 BULLISH", len(bullish))
        c2.metric("🔴 BEARISH", len(bearish))
        c3.metric("⚪ NEUTRAL", len(neutral))
        st.divider()

        # Forecast table
        col_fc, col_tech = st.columns([3, 2])

        with col_fc:
            st.subheader("Forecast multi-fattore")
            for f in forecasts_data:
                dir_emoji = "🟢" if f["direction"] == "BULLISH" else ("🔴" if f["direction"] == "BEARISH" else "⚪")
                score = f["forecast_score"]
                conf = f["confidence"]
                with st.container():
                    c_sym, c_dir, c_score, c_conf = st.columns([2, 2, 2, 2])
                    c_sym.markdown(f"**{f['symbol']}**")
                    c_dir.markdown(f"{dir_emoji} {f['direction']}")
                    c_score.markdown(f"Score: `{score:+.2f}`")
                    c_conf.markdown(f"Conf: `{conf:.0%}`")
                    if f.get("reasoning"):
                        st.caption(f"💬 {f['reasoning']}")
                    st.divider()

        with col_tech:
            st.subheader("Indicatori tecnici")
            # Build heatmap data from market + forecast
            tech_rows = []
            for f in forecasts_data:
                sym = f["symbol"]
                md = market.get(sym, {})
                tech_rows.append({
                    "Asset": sym,
                    "Score": f["tech_score"],
                    "Sentiment": f["sentiment_score"],
                    "24h %": md.get("change_pct_24h", 0.0),
                })
            if tech_rows:
                df_tech = pd.DataFrame(tech_rows)
                fig = go.Figure(data=go.Heatmap(
                    z=df_tech[["Score", "Sentiment", "24h %"]].values.T,
                    x=df_tech["Asset"].tolist(),
                    y=["Tech Score", "Sentiment", "24h %"],
                    colorscale="RdYlGn",
                    zmid=0,
                    text=df_tech[["Score", "Sentiment", "24h %"]].values.T.round(2),
                    texttemplate="%{text}",
                ))
                fig.update_layout(height=220, margin=dict(t=10, b=10, l=10, r=10))
                st.plotly_chart(fig, use_container_width=True)

        # Forecast score bar chart
        st.subheader("Score previsionale per asset")
        df_fc = pd.DataFrame(forecasts_data)
        df_fc["color"] = df_fc["direction"].map(
            {"BULLISH": "Positivo", "BEARISH": "Negativo", "NEUTRAL": "Neutro"}
        )
        fig = px.bar(
            df_fc, x="symbol", y="forecast_score",
            color="color",
            color_discrete_map={"Positivo": "#00cc88", "Negativo": "#ff4444", "Neutro": "#aaaaaa"},
            range_y=[-1, 1],
            labels={"symbol": "Asset", "forecast_score": "Forecast Score"},
            text="forecast_score",
        )
        fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
        fig.add_hline(y=0.35, line_dash="dot", line_color="green", annotation_text="BUY soglia")
        fig.add_hline(y=-0.35, line_dash="dot", line_color="red", annotation_text="SELL soglia")
        fig.update_layout(height=300, margin=dict(t=30, b=20), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


# ===========================================================================
# TAB 4 — MACRO
# ===========================================================================
with tab_macro:
    st.subheader("Indicatori Macro-Economici")

    if not macro_data:
        st.info(
            "Nessun dato macro. Aggiungi **FRED_API_KEY** nel `.env` "
            "(chiave gratuita: [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html)) "
            "e avvia il bot."
        )
    else:
        # Group by country
        by_country: dict[str, list[dict]] = {}
        for ind in macro_data:
            by_country.setdefault(ind["country"], []).append(ind)

        country_tabs = st.tabs(list(by_country.keys()))
        for ctab, country in zip(country_tabs, by_country.keys()):
            with ctab:
                indicators = by_country[country]

                # KPI cards — up to 4 per row
                cols_per_row = 4
                for i in range(0, len(indicators), cols_per_row):
                    chunk = indicators[i:i + cols_per_row]
                    cols = st.columns(len(chunk))
                    for col, ind in zip(cols, chunk):
                        # Color logic
                        val = ind["value"]
                        name = ind["name"]
                        # Simple risk coloring: high CPI/VIX = red, low = green
                        if "CPI" in name or "VIX" in name or "Spread" in name:
                            delta_color = "inverse"  # high = bad
                        elif "GDP" in name or "Consumer" in name:
                            delta_color = "normal"   # high = good
                        else:
                            delta_color = "off"
                        col.metric(
                            label=name,
                            value=f"{val:.2f} {ind['unit']}",
                            delta=ind["source"],
                            delta_color=delta_color,
                        )

                st.divider()

                # Indicator history chart
                indicator_names = {ind["indicator_id"]: ind["name"] for ind in indicators}
                selected_ind = st.selectbox(
                    "Storico indicatore",
                    options=list(indicator_names.keys()),
                    format_func=lambda x: indicator_names.get(x, x),
                    key=f"macro_select_{country}",
                )
                if selected_ind:
                    hist = load_macro_history_cached(selected_ind)
                    if len(hist) > 1:
                        df_macro = pd.DataFrame(hist)
                        df_macro["created_at"] = pd.to_datetime(df_macro["created_at"])
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=df_macro["created_at"], y=df_macro["value"],
                            mode="lines+markers",
                            name=indicator_names.get(selected_ind, selected_ind),
                            line=dict(color="#4a9eff", width=2),
                        ))
                        fig.update_layout(
                            height=280,
                            margin=dict(t=10, b=10, l=10, r=10),
                            xaxis_title="", yaxis_title=indicators[0]["unit"] if indicators else "",
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("Dati storici insufficienti — cresce ad ogni ciclo del bot.")

        # Summary heatmap across all indicators
        st.divider()
        st.subheader("Heatmap indicatori")
        if len(macro_data) >= 2:
            df_heat = pd.DataFrame(macro_data)[["name", "value", "country"]]
            fig = go.Figure(data=go.Bar(
                x=df_heat["name"],
                y=df_heat["value"],
                marker_color=[
                    "#00cc88" if v >= 0 else "#ff4444"
                    for v in df_heat["value"]
                ],
                text=df_heat["value"].round(2),
                textposition="outside",
            ))
            fig.update_layout(
                height=320,
                margin=dict(t=20, b=80, l=10, r=10),
                xaxis_tickangle=-35,
                xaxis_title="",
                yaxis_title="Valore",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)


# ===========================================================================
# TAB 5 — NOTIZIE
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
# TAB 6 — ORDINI
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

# ===========================================================================
# TAB 7 — DAY TRADING
# ===========================================================================
with tab_daytrading:
    import json as _json
    from pathlib import Path as _Path

    _cfg_path = _Path(__file__).parent / "config.json"
    try:
        with open(_cfg_path) as _f:
            _full_cfg = _json.load(_f)
        _dt_cfg = _full_cfg.get("day_trading", {})
    except Exception:
        _dt_cfg = {}
        _full_cfg = {}

    _dt_enabled = _dt_cfg.get("enabled", False)

    # ── Header status ────────────────────────────────────────────────────
    _status_col, _toggle_col = st.columns([3, 1])
    with _status_col:
        if _dt_enabled:
            st.success("⚡ Day Trading **ATTIVO** — ciclo ogni "
                       f"{_dt_cfg.get('cycle_minutes', 5)} minuti")
        else:
            st.warning("⏸️ Day Trading **DISATTIVATO** — abilita in `config.json → day_trading.enabled: true`")

    with _toggle_col:
        if st.button("✅ Attiva" if not _dt_enabled else "⏸️ Disattiva", use_container_width=True):
            _full_cfg["day_trading"]["enabled"] = not _dt_enabled
            with open(_cfg_path, "w") as _f:
                _json.dump(_full_cfg, _f, indent=2)
            st.rerun()

    st.divider()

    # ── Session state (live, from session_manager) ───────────────────────
    st.subheader("📊 Sessione corrente")
    try:
        from agents.session_manager import get_session as _get_session
        _sess = _get_session()
    except Exception:
        _sess = {}

    _m1, _m2, _m3, _m4 = st.columns(4)
    _m1.metric("📅 Data sessione",  _sess.get("date", "—"))
    _m2.metric("🔁 Trade oggi",     _sess.get("trades_today", 0),
               help=f"Max: {_dt_cfg.get('max_daily_trades', 10)}")
    _pnl_pct = _sess.get("daily_pnl_pct", 0.0)
    _m3.metric("📈 P&L giornaliero", f"{_pnl_pct:+.2f}%",
               delta=f"€{_sess.get('daily_pnl_eur', 0.0):+.2f}",
               delta_color="normal")
    _open_pos = _sess.get("open_intraday_positions", {})
    _m4.metric("📂 Posizioni aperte", len(_open_pos),
               help=f"Max: {_dt_cfg.get('max_concurrent_positions', 3)}")

    # Circuit breaker bars
    _max_trades = _dt_cfg.get("max_daily_trades", 10)
    _max_loss   = abs(_dt_cfg.get("max_daily_loss_pct", 2.0))
    st.progress(
        min(1.0, _sess.get("trades_today", 0) / max(1, _max_trades)),
        text=f"Trade usati: {_sess.get('trades_today',0)}/{_max_trades}",
    )
    st.progress(
        min(1.0, abs(_pnl_pct) / _max_loss) if _pnl_pct < 0 else 0.0,
        text=f"Loss giornaliero: {_pnl_pct:.2f}% / -{_max_loss:.1f}% limite",
    )

    # Open intraday positions table
    if _open_pos:
        st.subheader("📂 Posizioni intraday aperte")
        _rows = []
        for _sym, _pos in _open_pos.items():
            _rows.append({
                "Asset":    _sym,
                "Entry":    f"{_pos.get('entry_price', 0):.4f}",
                "Stop Loss":f"{_pos.get('stop_loss', 0):.4f}",
                "Take Profit": f"{_pos.get('take_profit', 0):.4f}",
                "Importo":  f"€{_pos.get('amount_eur', 0):.2f}",
                "P&L %":    f"{_pos.get('pnl_pct', 0.0):+.2f}%",
                "Aperta":   _pos.get("opened_at", "")[:16],
            })
        st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)

    # Closed trades today
    _closed = _sess.get("closed_today", [])
    if _closed:
        st.subheader("✅ Trade chiusi oggi")
        _df_cl = pd.DataFrame(_closed)
        _df_cl["pnl_pct"] = _df_cl["pnl_pct"].apply(lambda x: f"{x:+.2f}%")
        _df_cl["pnl_eur"] = _df_cl["pnl_eur"].apply(lambda x: f"€{x:+.2f}")
        st.dataframe(_df_cl, use_container_width=True, hide_index=True)

    # Cooldowns
    _cooldowns = {s: v for s, v in _sess.get("cooldown_symbols", {}).items()}
    if _cooldowns:
        import time as _time
        _now = _time.time()
        _cd_rows = []
        for _s, _until in _cooldowns.items():
            _rem = max(0, int((_until - _now) / 60))
            if _rem > 0:
                _cd_rows.append({"Asset": _s, "Cooldown rimanente": f"{_rem} min"})
        if _cd_rows:
            st.warning("⏳ Cooldown attivi (stop-loss recente)")
            st.dataframe(pd.DataFrame(_cd_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Config parameters ────────────────────────────────────────────────
    st.subheader("⚙️ Parametri configurazione")
    _c1, _c2, _c3 = st.columns(3)

    with _c1:
        st.markdown("**Segnali**")
        st.metric("Score threshold",   _dt_cfg.get("score_threshold", 0.40))
        st.metric("RSI overbought",    _dt_cfg.get("rsi_overbought", 65))
        st.metric("RSI oversold",      _dt_cfg.get("rsi_oversold",  35))
        st.metric("Ciclo (minuti)",    _dt_cfg.get("cycle_minutes",  5))

    with _c2:
        st.markdown("**Risk / Size**")
        st.metric("Stop-loss (ATR ×)", _dt_cfg.get("stop_loss_atr_multiplier", 1.5))
        st.metric("Take-profit (ATR ×)",_dt_cfg.get("take_profit_atr_multiplier", 2.5))
        st.metric("Size posizione %",  f"{_dt_cfg.get('position_size_pct', 2.0):.1f}%")
        st.metric("Max posizione €",   f"€{_dt_cfg.get('max_position_eur', 100):.0f}")

    with _c3:
        st.markdown("**Limiti sessione**")
        st.metric("Max trade/giorno",   _dt_cfg.get("max_daily_trades", 10))
        st.metric("Max loss/giorno",   f"{_dt_cfg.get('max_daily_loss_pct', -2.0):.1f}%")
        st.metric("Max pos. concorrenti", _dt_cfg.get("max_concurrent_positions", 3))
        st.metric("Cooldown SL (min)", _dt_cfg.get("cooldown_after_stop_minutes", 30))

    with st.expander("🕐 Orari mercato"):
        _mh = _dt_cfg.get("market_hours", {})
        _st_mh = _mh.get("stocks", {})
        st.markdown(f"""
| Mercato | Orari |
|---------|-------|
| **Stocks/ETF (NYSE)** | {_st_mh.get('open','09:30')} – {_st_mh.get('close','16:00')} ET (lun–ven) |
| **Crypto** | {_mh.get('crypto','24/7')} |
        """)

    with st.expander("📋 Simboli day trading"):
        _dt_syms = _dt_cfg.get("symbols", [])
        if _dt_syms:
            st.write(", ".join(_dt_syms))
        else:
            st.info("Nessun simbolo specifico — usa la watchlist globale (ASSETS da config)")

    st.divider()

    # ── How it works ─────────────────────────────────────────────────────
    with st.expander("ℹ️ Come funziona il day trading"):
        st.markdown("""
**Pipeline intraday (ogni 5 minuti):**

1. **SessionManager** — verifica orari mercato, circuit breakers (max loss / max trade)
2. **IntradayData** — scarica candle 5m / 15m / 1h (Binance per crypto, yfinance per stocks)
3. **IntradaySignals** — calcola EMA 9/21, VWAP, RSI(5), ATR(14), Stochastic(5,3,3)
4. **IntradayStrategy** — genera segnali con stop-loss e take-profit dinamici su ATR
5. **Execution** — esegue via Revolut X (crypto) o Alpaca (stocks)

**Entry LONG — tutte le condizioni:**
- `intraday_score ≥ 0.40`
- EMA9 > EMA21 (trend 5m rialzista)
- RSI(5) < 65 (non esaurito)
- Stoch %K > %D (momentum)
- Trend 1h bullish (conferma multi-timeframe)
- Prezzo entro -1.5% dal VWAP

**Stop-loss:** `entry - ATR × 1.5`
**Take-profit:** `entry + ATR × 2.5`  → **R:R ≈ 1:1.7**

**Avvio con day trading:**
```bash
python main.py --loop --intraday        # swing 60min + intraday 5min
python main.py --intraday-only          # solo intraday
```
        """)


# ===========================================================================
# TAB 8 — ANALISTA AI (chat box)
# ===========================================================================
with tab_chat:
    st.subheader("Analista Finanziario AI")
    st.caption("Fai domande sul portfolio, sui mercati, sulle previsioni o sulla situazione macro. Risponde usando i dati reali del bot.")

    # Build market context string for Claude
    def _build_chat_context() -> str:
        lines = [f"Data: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]

        if portfolio:
            lines.append(f"\nPORTFOLIO: €{portfolio.get('total_value_eur', 0):.2f} totale | "
                         f"€{portfolio.get('cash_eur', 0):.2f} cash | "
                         f"{len(portfolio.get('positions', []))} posizioni | "
                         f"risk={portfolio.get('risk_score', 0)}/100")
            for p in portfolio.get("positions", []):
                lines.append(f"  {p['symbol']}: {p['qty']:.4f} @ €{p['avg_price_eur']:.2f} | "
                             f"P&L {p['pnl_pct']:+.1f}%")

        if forecasts_data:
            lines.append("\nFORECAST (ultimi):")
            for f in forecasts_data[:8]:
                lines.append(f"  {f['symbol']}: {f['direction']} score={f['forecast_score']:+.2f} "
                             f"conf={f['confidence']:.0%} — {f.get('reasoning', '')[:80]}")

        if macro_data:
            lines.append("\nMACRO:")
            for m in macro_data:
                lines.append(f"  {m['name']} ({m['country']}): {m['value']:.2f} {m['unit']}")

        if sentiment:
            lines.append("\nSENTIMENT: " + " | ".join(
                f"{s['symbol']}={s['score']:+.2f}" for s in sentiment[:8]
            ))

        if news:
            lines.append("\nULTIME NOTIZIE:")
            for n in news[:5]:
                lines.append(f"  • {n['title']} [{n['source']}]")

        return "\n".join(lines)

    _CHAT_SYSTEM = (
        "Sei un analista finanziario AI integrato in un investment bot. "
        "Hai accesso ai dati in tempo reale di portfolio, forecast, indicatori macro e notizie. "
        "Rispondi in italiano, in modo conciso e professionale. "
        "Usa i dati forniti nel contesto per rispondere con precisione. "
        "Non inventare dati che non hai. Se non hai informazioni sufficienti, dillo chiaramente."
    )

    # Initialize chat history in session state
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Chiedi all'analista AI... (es: 'Perché hai comprato GLD?' o 'Come vedi il mercato oggi?')"):
        # Show user message
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Build response
        with st.chat_message("assistant"):
            with st.spinner("Analisi in corso..."):
                from core.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
                if not ANTHROPIC_API_KEY:
                    reply = "⚠️ ANTHROPIC_API_KEY non configurata. Aggiungi la chiave nel `.env` per usare l'analista AI."
                else:
                    try:
                        import anthropic as _anthropic
                        context = _build_chat_context()
                        client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                        messages_for_api = [
                            {"role": "user", "content": f"Contesto dati bot:\n{context}\n\nDomanda: {m['content']}"}
                            if m["role"] == "user" and i == 0
                            else {"role": m["role"], "content": m["content"]}
                            for i, m in enumerate(st.session_state.chat_history)
                        ]
                        response = client.messages.create(
                            model=CLAUDE_MODEL,
                            max_tokens=1024,
                            system=_CHAT_SYSTEM,
                            messages=messages_for_api,
                        )
                        reply = response.content[0].text
                    except Exception as exc:
                        reply = f"⚠️ Errore: {exc}"
                st.markdown(reply)

        st.session_state.chat_history.append({"role": "assistant", "content": reply})

    # Clear chat button
    if st.session_state.chat_history:
        if st.button("🗑️ Cancella conversazione", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()

# ===========================================================================
# TAB 8 — GUIDA
# ===========================================================================
with tab_guide:
    st.title("📚 Guida all'Investimento")
    st.caption("Come funziona il bot e come investire in modo consapevole.")

    # -----------------------------------------------------------------------
    g1, g2 = st.columns([1, 1])

    with g1:
        st.subheader("🤖 Come funziona il bot")
        st.markdown("""
Ogni **60 minuti** il bot esegue un ciclo swing completo (+ ciclo intraday ogni **5 minuti** se attivato):

1. **📰 Notizie** — raccoglie da Reuters, CNBC, Yahoo Finance, WSJ
2. **🏦 Macro** — legge Fed, BCE, World Bank (tassi, CPI, VIX, PIL)
3. **🧠 Sentiment** — Claude analizza le notizie e assegna un punteggio [-1,+1] per ogni asset
4. **📊 Mercato** — scarica prezzi in tempo reale (yfinance)
5. **📐 Tecnico** — calcola RSI, medie mobili, MACD, Bollinger Bands
6. **🔮 Forecast** — Claude combina tutto in una previsione BULLISH/BEARISH/NEUTRAL
7. **⚡ Strategia** — genera segnali BUY/SELL/TRIM/HOLD
8. **🛡️ Risk Manager** — valida i segnali contro le regole di rischio
9. **✅ Esecuzione** — piazza gli ordini (simulati in paper mode)
        """)

        st.subheader("📊 Indicatori tecnici usati")
        st.markdown("""
| Indicatore | Cosa misura | Segnale |
|-----------|------------|---------|
| **RSI (14)** | Forza del trend | >70 = overbought, <30 = oversold |
| **MA20/MA50** | Medie mobili | Golden cross = rialzo, Death cross = ribasso |
| **MACD** | Momentum | Histogram positivo = rialzo |
| **Bollinger Bands** | Volatilità | Vicino al lower = rimbalzo possibile |
| **Momentum 5d** | Variazione % | Positivo = trend in corso |
        """)

    with g2:
        st.subheader("🛡️ Regole Stop Loss / Take Profit")

        col_sl, col_tp = st.columns(2)
        with col_sl:
            st.error(f"**Stop Loss: {STOP_LOSS_PCT}%**")
            st.markdown(f"""
Vendi automaticamente se la posizione perde il **{abs(STOP_LOSS_PCT)}%**.

**Esempio:** Compri GLD a €100
→ Se scende a **€{100*(1+STOP_LOSS_PCT/100):.0f}** → SELL automatico
            """)

        with col_tp:
            st.success(f"**Take Profit: +{TAKE_PROFIT_PCT}%**")
            st.markdown(f"""
Vendi (parzialmente) se la posizione guadagna il **{TAKE_PROFIT_PCT}%**.

**Esempio:** Compri GLD a €100
→ Se sale a **€{100*(1+TAKE_PROFIT_PCT/100):.0f}** → TRIM automatico
            """)

        st.divider()
        st.subheader("⚙️ Altre regole di rischio")
        st.markdown(f"""
| Regola | Valore | Effetto |
|--------|--------|---------|
| **Max trade** | €{MAX_TRADE_EUR} | Ogni ordine max €{MAX_TRADE_EUR} |
| **Max posizione** | {MAX_POSITION_PCT}% | Nessun asset >20% del portfolio |
| **Min cash** | {MIN_CASH_PCT}% | Mantieni sempre liquidità |
| **Max crypto** | 15% | Limita esposizione crypto |
| **Risk score** | 0-100 | Se >60 (Alto) blocca nuovi BUY |

**Come si calcola il Risk Score:**
- Cash <{MIN_CASH_PCT}% → +25 punti
- Crypto >15% → +20 punti
- Posizione >20% → +15 punti per ognuna
- <2 tipi di asset → +10 punti
        """)

    st.divider()

    # -----------------------------------------------------------------------
    st.subheader("💡 Principi base per investire")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("""
**🎯 Diversifica**

Non mettere tutto in un solo asset.
Il bot gestisce automaticamente:
- Crypto (max 15%)
- ETF (ampia base)
- Stock (settori diversi)
- Commodities (oro, petrolio)
- Bond (TLT)
        """)
    with c2:
        st.warning("""
**⚠️ Gestisci il rischio**

Prima di investire chiediti:
- Posso permettermi di perdere questa somma?
- Ho abbastanza liquidità?
- Il mercato è in fase risk-on o risk-off?

Il **VIX >30** = alta volatilità → riduci le posizioni
        """)
    with c3:
        st.success("""
**📈 Pensa al lungo periodo**

Il bot opera su orizzonti:
- **Short** (giorni): segnali tecnici
- **Medium** (settimane): trend + macro

I mercati scendono e salgono.
Il dollar-cost averaging (acquisti graduali) riduce il rischio di timing sbagliato.
        """)

    st.divider()

    # -----------------------------------------------------------------------
    st.subheader("🔑 Interpretare i segnali")
    st.markdown("""
| Segnale | Condizione | Significato |
|---------|-----------|-------------|
| 🟢 **BUY** | Forecast >+0.35, conf >50%, BULLISH | Il bot vede opportunità di acquisto |
| 🔴 **SELL** | Forecast <-0.35, conf >50%, BEARISH + posizione aperta | Uscita dal trade |
| ✂️ **TRIM** | P&L ≥+30% o posizione >20% | Presa parziale di profitto |
| 🛑 **STOP LOSS** | P&L ≤-15% | Uscita automatica per limitare le perdite |
| ⚪ **HOLD** | Tutto il resto | Mantieni, nessuna azione necessaria |

**Forecast Score:**
- `+0.5` a `+1.0` = forte segnale rialzista
- `+0.1` a `+0.5` = segnale moderato
- `-0.1` a `+0.1` = neutro / incerto
- `-0.5` a `-1.0` = forte segnale ribassista

**Confidence:**
- `>70%` = alta certezza del segnale
- `50-70%` = buona certezza
- `<50%` = segnale debole, non eseguito
    """)

    st.divider()
    st.caption("⚠️ **Disclaimer:** Questo bot è a scopo educativo. Non costituisce consulenza finanziaria. Investi solo capitale che puoi permetterti di perdere.")
