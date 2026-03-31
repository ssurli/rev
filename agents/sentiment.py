"""SentimentAgent — uses Claude to score news sentiment per asset.

For each news item, Claude assigns a sentiment score [-1.0, +1.0] for
every tracked asset mentioned.  Scores are aggregated per asset.
"""

from __future__ import annotations

import json
import logging

import anthropic

from core.config import ANTHROPIC_API_KEY, ASSETS, CLAUDE_MODEL
from core.state import BotState

logger = logging.getLogger(__name__)

# Map from normalized asset symbol -> search keywords
ASSET_KEYWORDS: dict[str, list[str]] = {
    # Crypto
    "BTC-USD":  ["bitcoin", "btc", "crypto", "cryptocurrency"],
    "ETH-USD":  ["ethereum", "eth", "ether", "crypto"],
    "BNB-USD":  ["binance", "bnb"],
    "SOL-USD":  ["solana", "sol"],
    "XRP-USD":  ["ripple", "xrp"],
    # ETF
    "VOO":      ["s&p 500", "spx", "vanguard", "us stocks", "wall street"],
    "QQQ":      ["nasdaq", "tech stocks", "technology", "big tech"],
    "SPY":      ["s&p 500", "spx", "us stocks", "wall street"],
    # Commodities
    "GLD":      ["gold", "oro", "precious metals", "safe haven", "xau"],
    "SLV":      ["silver", "precious metals", "xag"],
    "OIL":      ["oil", "crude", "brent", "wti", "energy", "opec", "petroleum"],
    # Forex
    "EUR=X":    ["euro", "eur", "ecb", "eurozone"],
    "GBP=X":    ["pound", "gbp", "bank of england", "brexit"],
    # Stocks
    "AAPL":     ["apple", "iphone", "tim cook", "ios", "mac", "app store"],
    "TSLA":     ["tesla", "elon musk", "electric vehicle", "ev", "cybertruck"],
    "NVDA":     ["nvidia", "jensen huang", "gpu", "ai chip", "semiconductor", "cuda"],
    "MSFT":     ["microsoft", "satya nadella", "azure", "openai", "windows", "copilot"],
    "GOOGL":    ["google", "alphabet", "sundar pichai", "search", "gemini", "youtube"],
    "AMZN":     ["amazon", "andy jassy", "aws", "prime", "alexa"],
    "META":     ["meta", "mark zuckerberg", "facebook", "instagram", "threads", "whatsapp"],
}

# Add any extra assets from config that aren't in the map
for _sym in ASSETS:
    if _sym not in ASSET_KEYWORDS:
        ASSET_KEYWORDS[_sym] = [_sym.lower().replace("-usd", "").replace("=x", "")]


_SYSTEM_PROMPT = """You are a financial sentiment analysis assistant.
Given a news headline and excerpt, evaluate the sentiment for each specified asset.
Return ONLY a valid JSON object mapping each asset symbol to a sentiment score between -1.0 (very negative) and +1.0 (very positive).
Use 0.0 if the news does not mention or affect the asset.
Do not include any explanation, only the JSON."""


def _score_batch(headlines: list[str], asset_symbols: list[str]) -> dict[str, float]:
    """Ask Claude to score up to 10 headlines at once for all assets."""
    if not headlines or not ANTHROPIC_API_KEY or not ANTHROPIC_API_KEY.strip():
        return {sym: 0.0 for sym in asset_symbols}

    headlines_text = "\n".join(f"- {h}" for h in headlines[:10])
    user_msg = (
        f"Assets to score: {', '.join(asset_symbols)}\n\n"
        f"News headlines:\n{headlines_text}\n\n"
        "Return JSON: {\"SYMBOL\": score, ...}"
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = message.content[0].text.strip()
        if not raw:
            return {sym: 0.0 for sym in asset_symbols}
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("Sentiment: JSON parse failed, skipping batch")
        return {sym: 0.0 for sym in asset_symbols}
    except Exception as exc:
        logger.warning("Sentiment Claude call failed: %s", exc)
        return {sym: 0.0 for sym in asset_symbols}


def run(state: BotState) -> BotState:
    """Compute per-asset sentiment from news_items."""
    news = state.get("news_items", [])
    if not news:
        logger.info("SentimentAgent: no news to process")
        state["sentiment_scores"] = {}
        state["asset_mentions"] = {}
        return state

    monitored = [s for s in ASSETS if s in ASSET_KEYWORDS]

    # Build mentions map (keyword match) and collect ALL headlines for Claude
    # Macro news (Fed, tariffs, recession) affect all assets even without explicit mention
    all_headlines: list[str] = [item["title"] for item in news]
    mentions: dict[str, list[str]] = {sym: [] for sym in monitored}

    for item in news:
        title_lower = item["raw_text"].lower()
        for sym, kws in ASSET_KEYWORDS.items():
            if sym not in monitored:
                continue
            if any(kw in title_lower for kw in kws):
                mentions[sym].append(item["title"])

    if not all_headlines:
        logger.info("SentimentAgent: no headlines to process")
        state["sentiment_scores"] = {sym: 0.0 for sym in monitored}
        state["asset_mentions"] = mentions
        return state

    # Score in batches of 10 — use ALL headlines, not just keyword-matched ones
    aggregated: dict[str, list[float]] = {sym: [] for sym in monitored}
    for i in range(0, len(all_headlines), 10):
        batch = all_headlines[i : i + 10]
        scores = _score_batch(batch, monitored)
        for sym in monitored:
            val = scores.get(sym, 0.0)
            if val != 0.0:
                aggregated[sym].append(float(val))

    # Average the non-zero scores per asset
    final_scores: dict[str, float] = {}
    for sym in monitored:
        vals = aggregated[sym]
        final_scores[sym] = round(sum(vals) / len(vals), 3) if vals else 0.0

    logger.info("SentimentAgent: scores %s", final_scores)
    state["sentiment_scores"] = final_scores
    state["asset_mentions"] = mentions
    return state
