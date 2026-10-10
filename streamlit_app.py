"""
TradingBot - Autonomous Execution & Market Intelligence Cockpit (Streamlit Edition)
Supports Streamlit Community Cloud and Render deployment.
"""

import os
import json
import time
import pandas as pd
import streamlit as st
from market_intel import MarketIntelSuite

st.set_page_config(page_title="TradingBot Cockpit", page_icon="🤖", layout="wide")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "trades.log")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "account_type": "real",
        "take_profit_percent": 3.0,
        "stop_loss_percent": -2.5,
        "max_open_positions": 7,
        "trade_amount_usd": 50.0,
        "watchlist": ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "GOOGL", "META"]
    }

cfg = load_config()
intel = MarketIntelSuite()

# Header
st.title("🤖 Autonomous Trading Bot & Market Confluence Cockpit")
st.caption("Integrated Multi-Feed Execution Engine • Powered by Frankfurter, CoinGecko, FRED, SEC EDGAR & Polygon/Finnhub")

# Sidebar
st.sidebar.header("⚙️ Bot Parameters")
tp = st.sidebar.slider("Take Profit (%)", 0.5, 15.0, float(cfg.get("take_profit_percent", 3.0)))
sl = st.sidebar.slider("Stop Loss (%)", -15.0, -0.5, float(cfg.get("stop_loss_percent", -2.5)))
max_pos = st.sidebar.number_input("Max Positions", 1, 30, int(cfg.get("max_open_positions", 7)))
trade_amt = st.sidebar.number_input("Trade Amount ($)", 10.0, 500.0, float(cfg.get("trade_amount_usd", 50.0)))

selected_asset = st.sidebar.selectbox("Inspect Asset", cfg.get("watchlist", ["AAPL", "NVDA", "TSLA"]))

# Top KPI row
k1, k2, k3, k4 = st.columns(4)
macro_res = intel.get_fred_macro_indicators()
ffr = macro_res.get("fed_funds_rate", {}).get("value", 3.75)
t10 = macro_res.get("treasury_10y", {}).get("value", 4.12)
k1.metric("FED FUNDS RATE (FRED)", f"{ffr:.2f}%")
k2.metric("10Y TREASURY YIELD (FRED)", f"{t10:.2f}%")
k3.metric("TAKE PROFIT TARGET", f"+{tp:.1f}%")
k4.metric("STOP LOSS LIMIT", f"{sl:.1f}%")

st.divider()

# Tabs
tab_radar, tab_sec, tab_macro, tab_logs = st.tabs([
    "📈 Asset Radar (Polygon / Finnhub)",
    "🏛️ SEC EDGAR Corporate Filings",
    "🌍 Global Forex & Crypto Pulse",
    "📜 Bot Trade Logs"
])

with tab_radar:
    st.subheader(f"⚡ Intraday Market Radar: {selected_asset}")
    c1, c2 = st.columns([1.5, 2.5])
    with c1:
        quote = intel.get_stock_ticks_and_quote(selected_asset)
        if quote.get("price", 0) > 0:
            chg = quote.get("change", 0.0)
            chg_pct = quote.get("change_pct", 0.0)
            st.metric(f"{selected_asset} Price", f"${quote['price']:.2f}", f"{chg:+.2f} ({chg_pct:+.2f}%)")
            st.write(f"• **Open:** ${quote.get('open', 0):.2f}")
            st.write(f"• **Day High:** ${quote.get('high', 0):.2f}")
            st.write(f"• **Day Low:** ${quote.get('low', 0):.2f}")
            st.write(f"• **Previous Close:** ${quote.get('prev_close', 0):.2f}")
            st.caption(f"Feed Provider: {quote.get('source', 'Finnhub').upper()}")
        else:
            st.info("Live quotes unavailable.")

    with c2:
        st.subheader("📰 Recent Market News & Catalyst Sentiments")
        news = intel.get_market_news_sentiment(selected_asset, limit=4)
        if news:
            for item in news:
                st.markdown(f"**[{item['headline']}]({item['url']})**")
                st.caption(f"{item['source']} • {item['summary']}")
        else:
            st.info("No catalyst news for this asset.")

with tab_sec:
    st.subheader(f"📄 Direct SEC EDGAR Filings: {selected_asset}")
    filings = intel.get_sec_edgar_filings(selected_asset, limit=10)
    if filings:
        st.dataframe(pd.DataFrame(filings), use_container_width=True, hide_index=True)
    else:
        st.info("No SEC filings found.")

with tab_macro:
    st.subheader("💱 Real-Time Foreign Exchange (Frankfurter - Zero Auth)")
    fx = intel.get_forex_rates("USD", ["EUR", "GBP", "JPY", "CAD", "AUD", "CHF"])
    rates = fx.get("rates", {})
    fcols = st.columns(6)
    for i, (k, v) in enumerate(rates.items()):
        fcols[i % 6].metric(f"USD / {k}", f"{v:.4f}")

    st.markdown("---")
    st.subheader("🪙 Cryptocurrency Market Momentum (CoinGecko - Zero Auth)")
    crypto = intel.get_crypto_prices(["bitcoin", "ethereum", "solana", "ripple", "dogecoin"])
    ccols = st.columns(5)
    for i, (cid, cdata) in enumerate(crypto.get("data", {}).items()):
        ccols[i % 5].metric(cdata["symbol"], f"${cdata['price_usd']:,.2f}", f"{cdata['change_24h_pct']:+.2f}%")

with tab_logs:
    st.subheader("📜 Bot Execution & Audit Trail")
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        st.text_area("Live Log Output", value="".join(lines[-40:]), height=350)
    else:
        st.info("No trade log file found yet.")
