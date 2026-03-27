"""ForecastAgent — sintetizza sentiment + analisi tecnica in previsioni per asset.

Claude riceve per ogni asset:
- Score sentiment [-1,+1] dalle notizie
- Score tecnico [-1,+1] dagli indicatori
- Variazione prezzi 24h e 5 giorni
- Notizie correlate

Output: forecast con direzione, confidence e reasoning in italiano.
"""

from __future__ import annotations

import json
import logging

import anthropic

from core.config import ANTHROPIC_API_KEY, ASSETS, CLAUDE_MODEL
from core.state import AssetForecast, BotState

logger = logging.getLogger(__name__)

_SYSTEM = """Sei un analista finanziario esperto. Ti vengono forniti dati tecnici e di sentiment per asset finanziari.
Per ogni asset genera una previsione a breve/medio termine.
Rispondi SOLO con un oggetto JSON valido nel formato specificato, senza testo aggiuntivo."""


def _build_prompt(asset_data: list[dict]) -> str:
    data_str = json.dumps(asset_data, indent=2, ensure_ascii=False)
    return f"""Analizza questi asset e fornisci una previsione per ciascuno.

Dati:
{data_str}

Per ogni asset ritorna:
{{
  "SYMBOL": {{
    "forecast_score": <float da -1.0 a +1.0>,
    "direction": "<BULLISH|BEARISH|NEUTRAL>",
    "confidence": <float da 0.0 a 1.0>,
    "horizon": "<short|medium>",
    "reasoning": "<spiegazione in italiano, max 2 frasi>"
  }}
}}

Considera:
- sentiment_score: impatto notizie recenti (-1=molto negativo, +1=molto positivo)
- tech_score: segnali tecnici (-1=bearish, +1=bullish)
- rsi: >70 overbought, <30 oversold
- ma_cross: golden=bullish, death=bearish
- momentum_5d: variazione % ultimi 5 giorni
- change_24h: variazione % ultime 24 ore"""


def _parse_forecasts(raw: str, symbols: list[str]) -> dict[str, dict]:
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Forecast JSON parse failed: %s", exc)
        return {}


def _fallback_forecast(sym: str, sentiment: float, tech: float) -> AssetForecast:
    """Rule-based fallback when Claude is unavailable."""
    score = sentiment * 0.5 + tech * 0.5
    if score > 0.2:
        direction = "BULLISH"
    elif score < -0.2:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"
    return AssetForecast(
        symbol=sym,
        forecast_score=round(score, 3),
        direction=direction,
        confidence=min(abs(score), 0.7),
        horizon="short",
        reasoning=f"Previsione automatica: sentiment={sentiment:.2f}, tecnico={tech:.2f}",
        sentiment_score=sentiment,
        tech_score=tech,
    )


def run(state: BotState) -> BotState:
    """Generate forecasts for all assets."""
    sentiment = state.get("sentiment_scores", {})
    technicals = state.get("technical_indicators", {})
    market = state.get("market_data", {})
    mentions = state.get("asset_mentions", {})

    forecasts: dict[str, AssetForecast] = {}

    # Build input data for Claude
    asset_data = []
    for sym in ASSETS:
        s = sentiment.get(sym, 0.0)
        t = technicals.get(sym, {})
        m = market.get(sym, {})
        headlines = mentions.get(sym, [])[:3]

        asset_data.append({
            "symbol": sym,
            "sentiment_score": s,
            "tech_score": t.get("tech_score", 0.0),
            "rsi": t.get("rsi", 50.0),
            "ma_cross": t.get("ma_cross", "neutral"),
            "macd_hist": t.get("macd_hist", 0.0),
            "momentum_5d": t.get("momentum_5d", 0.0),
            "change_24h": m.get("change_pct_24h", 0.0),
            "news_headlines": headlines,
        })

    # Call Claude if available
    if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.strip() and asset_data:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                system=_SYSTEM,
                messages=[{"role": "user", "content": _build_prompt(asset_data)}],
            )
            raw = msg.content[0].text.strip()
            parsed = _parse_forecasts(raw, ASSETS)

            for sym in ASSETS:
                data = parsed.get(sym, {})
                s = sentiment.get(sym, 0.0)
                t_score = technicals.get(sym, {}).get("tech_score", 0.0)
                if data:
                    forecasts[sym] = AssetForecast(
                        symbol=sym,
                        forecast_score=float(data.get("forecast_score", 0.0)),
                        direction=data.get("direction", "NEUTRAL"),
                        confidence=float(data.get("confidence", 0.5)),
                        horizon=data.get("horizon", "short"),
                        reasoning=data.get("reasoning", ""),
                        sentiment_score=s,
                        tech_score=t_score,
                    )
                else:
                    forecasts[sym] = _fallback_forecast(sym, s, t_score)

        except Exception as exc:
            logger.warning("ForecastAgent Claude call failed: %s", exc)
            state["errors"].append(f"forecast: {exc}")
            # Fallback for all assets
            for sym in ASSETS:
                s = sentiment.get(sym, 0.0)
                t_score = technicals.get(sym, {}).get("tech_score", 0.0)
                forecasts[sym] = _fallback_forecast(sym, s, t_score)
    else:
        # No API key — use rule-based fallback
        for sym in ASSETS:
            s = sentiment.get(sym, 0.0)
            t_score = technicals.get(sym, {}).get("tech_score", 0.0)
            forecasts[sym] = _fallback_forecast(sym, s, t_score)

    directions = {f["direction"] for f in forecasts.values()}
    logger.info("ForecastAgent: %d forecasts — %s",
                len(forecasts),
                {d: sum(1 for f in forecasts.values() if f["direction"] == d) for d in directions})

    state["forecasts"] = forecasts
    return state
