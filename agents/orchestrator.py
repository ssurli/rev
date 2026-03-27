"""OrchestratorAgent — builds and runs the LangGraph workflow.

Graph flow:

  START → portfolio_init → news_monitor → sentiment
        → market_data → technical → forecast
        → strategy → risk_manager → execution → portfolio_update → END
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from agents import (
    execution,
    forecast,
    market_data,
    news_monitor,
    portfolio,
    risk_manager,
    sentiment,
    strategy,
    technical,
)
from core.config import TRADING_MODE
from core.db import (
    save_forecasts,
    save_news_items,
    save_orders,
    save_sentiment,
    save_signals,
)
from core.state import BotState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node wrappers
# ---------------------------------------------------------------------------

def _node_portfolio_init(state: BotState) -> BotState:
    try:
        return portfolio.run(state)
    except Exception as exc:
        logger.error("portfolio_init error: %s", exc)
        state["errors"].append(f"portfolio_init: {exc}")
        if not state.get("portfolio"):
            state["portfolio"] = {
                "positions": [], "cash_eur": 0.0, "total_value_eur": 0.0,
                "risk_score": 0, "risk_label": "Basso", "allocations": {},
            }
        return state


def _node_news(state: BotState) -> BotState:
    try:
        state = news_monitor.run(state)
        save_news_items(state.get("news_items", []), state["cycle_id"])
    except Exception as exc:
        logger.error("news_monitor error: %s", exc)
        state["errors"].append(f"news_monitor: {exc}")
        state.setdefault("news_items", [])
    return state


def _node_sentiment(state: BotState) -> BotState:
    try:
        state = sentiment.run(state)
        save_sentiment(state["cycle_id"], state.get("sentiment_scores", {}), state.get("asset_mentions", {}))
    except Exception as exc:
        logger.error("sentiment error: %s", exc)
        state["errors"].append(f"sentiment: {exc}")
        state.setdefault("sentiment_scores", {})
        state.setdefault("asset_mentions", {})
    return state


def _node_market_data(state: BotState) -> BotState:
    try:
        state = market_data.run(state)
    except Exception as exc:
        logger.error("market_data error: %s", exc)
        state["errors"].append(f"market_data: {exc}")
        state.setdefault("market_data", {})
        state.setdefault("eur_usd", 1.08)
    return state


def _node_technical(state: BotState) -> BotState:
    try:
        state = technical.run(state)
    except Exception as exc:
        logger.error("technical error: %s", exc)
        state["errors"].append(f"technical: {exc}")
        state.setdefault("technical_indicators", {})
    return state


def _node_forecast(state: BotState) -> BotState:
    try:
        state = forecast.run(state)
        save_forecasts(state["cycle_id"], list(state.get("forecasts", {}).values()))
    except Exception as exc:
        logger.error("forecast error: %s", exc)
        state["errors"].append(f"forecast: {exc}")
        state.setdefault("forecasts", {})
    return state


def _node_strategy(state: BotState) -> BotState:
    try:
        state = strategy.run(state)
        save_signals(state["cycle_id"], state.get("signals", []), validated=False)
    except Exception as exc:
        logger.error("strategy error: %s", exc)
        state["errors"].append(f"strategy: {exc}")
        state.setdefault("signals", [])
    return state


def _node_risk_manager(state: BotState) -> BotState:
    try:
        state = risk_manager.run(state)
        save_signals(state["cycle_id"], state.get("validated_signals", []), validated=True)
    except Exception as exc:
        logger.error("risk_manager error: %s", exc)
        state["errors"].append(f"risk_manager: {exc}")
        state.setdefault("validated_signals", [])
    return state


def _node_execution(state: BotState) -> BotState:
    try:
        state = execution.run(state)
        save_orders(state["cycle_id"], state.get("executed_orders", []))
    except Exception as exc:
        logger.error("execution error: %s", exc)
        state["errors"].append(f"execution: {exc}")
        state.setdefault("executed_orders", [])
    return state


def _node_portfolio_update(state: BotState) -> BotState:
    try:
        return portfolio.run(state)
    except Exception as exc:
        logger.error("portfolio_update error: %s", exc)
        state["errors"].append(f"portfolio_update: {exc}")
    return state


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    g = StateGraph(BotState)

    g.add_node("portfolio_init",    _node_portfolio_init)
    g.add_node("news_monitor",      _node_news)
    g.add_node("sentiment",         _node_sentiment)
    g.add_node("market_data",       _node_market_data)
    g.add_node("technical",         _node_technical)
    g.add_node("forecast",          _node_forecast)
    g.add_node("strategy",          _node_strategy)
    g.add_node("risk_manager",      _node_risk_manager)
    g.add_node("execution",         _node_execution)
    g.add_node("portfolio_update",  _node_portfolio_update)

    g.add_edge(START,              "portfolio_init")
    g.add_edge("portfolio_init",   "news_monitor")
    g.add_edge("news_monitor",     "sentiment")
    g.add_edge("sentiment",        "market_data")
    g.add_edge("market_data",      "technical")
    g.add_edge("technical",        "forecast")
    g.add_edge("forecast",         "strategy")
    g.add_edge("strategy",         "risk_manager")
    g.add_edge("risk_manager",     "execution")
    g.add_edge("execution",        "portfolio_update")
    g.add_edge("portfolio_update", END)

    return g.compile()


_graph = None


def run_cycle(mode: str = TRADING_MODE) -> BotState:
    global _graph
    if _graph is None:
        _graph = build_graph()

    cycle_id = str(uuid.uuid4())[:8]
    initial: BotState = {
        "cycle_id": cycle_id,
        "mode": mode,
        "news_items": [],
        "sentiment_scores": {},
        "asset_mentions": {},
        "market_data": {},
        "eur_usd": 1.08,
        "technical_indicators": {},
        "forecasts": {},
        "signals": [],
        "validated_signals": [],
        "portfolio": {},
        "executed_orders": [],
        "errors": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info("=== CYCLE %s START [%s mode] ===", cycle_id, mode.upper())
    final = _graph.invoke(initial)

    if final.get("errors"):
        logger.warning("Cycle %s errors: %s", cycle_id, final["errors"])
    else:
        logger.info("=== CYCLE %s END — ok ===", cycle_id)

    return final
