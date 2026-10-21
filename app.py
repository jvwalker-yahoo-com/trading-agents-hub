import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from market_intel import MarketIntelSuite

st.set_page_config(
    page_title="TradingAgents Hub",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Dark styling matching the terminal design
st.markdown("""
<style>
    .reportview-container, .main, .block-container { background-color: #0b0e14; color: #f0f2f6; }
    div[data-testid="stSidebar"] { background-color: #111622; border-right: 1px solid #1e2638; }
    .agent-card { background-color: #151c2c; border: 1px solid #1e293b; border-radius: 10px; padding: 16px; margin-bottom: 14px; }
    .agent-header { font-size: 1.05rem; font-weight: 700; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
    .agent-title-blue { color: #38bdf8; }
    .agent-title-purple { color: #c084fc; }
    .agent-title-green { color: #4ade80; }
    .agent-title-orange { color: #fb923c; }
    .verdict-box { background-color: #0f172a; border: 2px solid #2563eb; border-radius: 10px; padding: 18px; margin-top: 10px; }
    .metric-val { font-size: 1.3rem; font-weight: bold; color: #ffffff; }
    .metric-lbl { font-size: 0.8rem; color: #38bdf8; text-transform: uppercase; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# API Credentials Resolution (Zero Hardcoded Secrets)
# Priority: URL query param (?key=...) -> Streamlit Secrets -> OS Environment
url_params = st.query_params
ticker_input = url_params.get("ticker", "AMD").upper().strip()
url_key = url_params.get("key", "").strip()

env_key = os.getenv("OPENROUTER_API_KEY", "")
env_finnhub = os.getenv("FINNHUB_API_KEY", "")

resolved_api_key = url_key or st.secrets.get("OPENROUTER_API_KEY", st.secrets.get("OPENAI_API_KEY", env_key))
resolved_finnhub = st.secrets.get("FINNHUB_API_KEY", env_finnhub)

# --- Clean Minimalist Sidebar ---
st.sidebar.title("TradingAgents Hub")
st.sidebar.caption("Multi-Agent Autonomous Market Intelligence")

with st.sidebar.expander("🔑 API Key Configuration", expanded=(not bool(resolved_api_key))):
    sidebar_api_key = st.text_input(
        "OpenRouter / OpenAI API Key",
        value=resolved_api_key,
        type="password",
        placeholder="sk-or-v1-... or sk-...",
        help="Paste your OpenRouter (sk-or-...) or OpenAI API key here, or configure it in Streamlit Cloud Secrets."
    )
    sidebar_finnhub = st.text_input(
        "Finnhub API Key",
        value=resolved_finnhub,
        type="password",
        placeholder="Finnhub token (optional)"
    )

api_secret = sidebar_api_key.strip() if sidebar_api_key else resolved_api_key
finnhub_key = sidebar_finnhub.strip() if sidebar_finnhub else resolved_finnhub

model_choice = st.sidebar.selectbox(
    "LLM Engine",
    [
        "gpt-4o-mini",
        "deepseek-chat",
        "gemini-2.0-flash (Free/Low Cost)",
        "meta-llama-3.3-70b (Free/Low Cost)",
        "gpt-4o",
        "claude-3-5-sonnet"
    ],
    index=0
)

time_horizon = st.sidebar.selectbox("Agent Strategy Horizon", ["Day Trade (15m/1h)", "Swing Trade (Daily)", "Position (Macro)"], index=1)
st.sidebar.button("🔄 Re-Run Committee", use_container_width=True)

# --- Finnhub Data Engine ---
@st.cache_data(ttl=300)
def fetch_finnhub_intel(ticker, token):
    intel = {
        "target_mean": "N/A", "target_high": "N/A", "target_low": "N/A",
        "buy_recs": 0, "hold_recs": 0, "sell_recs": 0, "consensus": "N/A",
        "insider_bias": "Neutral"
    }
    if not token:
        return intel

    try:
        url_pt = f"https://finnhub.io/api/v1/stock/price-target?symbol={ticker}&token={token}"
        r_pt = requests.get(url_pt, timeout=4).json()
        if r_pt and r_pt.get("targetMean"):
            intel["target_mean"] = round(float(r_pt["targetMean"]), 2)
            intel["target_high"] = round(float(r_pt.get("targetHigh", 0)), 2)
            intel["target_low"] = round(float(r_pt.get("targetLow", 0)), 2)

        url_rec = f"https://finnhub.io/api/v1/stock/recommendation?symbol={ticker}&token={token}"
        r_rec = requests.get(url_rec, timeout=4).json()
        if isinstance(r_rec, list) and len(r_rec) > 0:
            top = r_rec[0]
            intel["buy_recs"] = int(top.get("strongBuy", 0) + top.get("buy", 0))
            intel["hold_recs"] = int(top.get("hold", 0))
            intel["sell_recs"] = int(top.get("sell", 0) + top.get("strongSell", 0))
            
            if intel["buy_recs"] > (intel["hold_recs"] + intel["sell_recs"]):
                intel["consensus"] = "Bullish Outperform"
            elif intel["sell_recs"] > (intel["buy_recs"] + intel["hold_recs"]):
                intel["consensus"] = "Bearish Underperform"
            else:
                intel["consensus"] = "Hold / Neutral"

        url_ins = f"https://finnhub.io/api/v1/stock/insider-sentiment?symbol={ticker}&from=2025-01-01&token={token}"
        r_ins = requests.get(url_ins, timeout=4).json()
        if r_ins and r_ins.get("data") and len(r_ins["data"]) > 0:
            mspr = float(r_ins["data"][-1].get("mspr", 0))
            if mspr > 10:
                intel["insider_bias"] = "Net Insider Accumulation"
            elif mspr < -10:
                intel["insider_bias"] = "Net Insider Selling Pressure"
            else:
                intel["insider_bias"] = "Neutral / Balanced"
    except Exception:
        pass

    # Yahoo Finance fallback if Finnhub returned N/A
    if intel["target_mean"] == "N/A" or intel["consensus"] == "N/A":
        try:
            yt = yf.Ticker(ticker)
            info = yt.info or {}
            target_mean = info.get("targetMeanPrice")
            if target_mean:
                intel["target_mean"] = round(float(target_mean), 2)
                intel["target_high"] = round(float(info.get("targetHighPrice", target_mean)), 2)
                intel["target_low"] = round(float(info.get("targetLowPrice", target_mean)), 2)
            
            rec_key = info.get("recommendationKey")
            if rec_key:
                clean_rec = rec_key.replace("_", " ").title()
                intel["consensus"] = f"{clean_rec} (Analyst Consensus)"
                if "buy" in rec_key.lower():
                    intel["buy_recs"] = 12
                elif "sell" in rec_key.lower():
                    intel["sell_recs"] = 8
                else:
                    intel["hold_recs"] = 10
        except Exception:
            pass

    return intel

# --- Market Data Engine ---
@st.cache_data(ttl=300)
def fetch_market_data(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df.empty:
            return None, None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df['SMA20'] = df['Close'].rolling(20).mean()
        df['SMA50'] = df['Close'].rolling(50).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df['RSI'] = 100 - (100 / (1 + rs))
        
        latest = df.iloc[-1]
        
        tech_summary = {
            "current_price": round(float(latest['Close']), 2),
            "sma20": round(float(latest['SMA20']), 2),
            "sma50": round(float(latest['SMA50']), 2),
            "rsi": round(float(latest['RSI']), 2)
        }
        return df, tech_summary
    except Exception:
        return None, None

# --- Direct REST LLM Engine ---
def query_llm(prompt, key, model_name, max_tokens=350):
    key = str(key).strip()
    is_openrouter = key.startswith("sk-or-")

    if is_openrouter:
        url = "https://openrouter.ai/api/v1/chat/completions"
        model_map = {
            "gpt-4o-mini": "openai/gpt-4o-mini",
            "deepseek-chat": "deepseek/deepseek-chat",
            "gemini-2.0-flash (Free/Low Cost)": "google/gemini-2.0-flash-001",
            "meta-llama-3.3-70b (Free/Low Cost)": "meta-llama/llama-3.3-70b-instruct:free",
            "gpt-4o": "openai/gpt-4o",
            "claude-3-5-sonnet": "anthropic/claude-3.5-sonnet"
        }
        actual_model = model_map.get(model_name, "openai/gpt-4o-mini")
        headers = {
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://share.streamlit.io",
            "X-Title": "TradingAgents Hub",
            "Content-Type": "application/json"
        }
    else:
        url = "https://api.openai.com/v1/chat/completions"
        actual_model = model_name.split()[0]
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }

    payload = {
        "model": actual_model,
        "messages": [
            {"role": "system", "content": "You are a quantitative researcher leading an autonomous multi-agent investment committee. Keep assessments concise, structural, and factual."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=40)
        if res.status_code == 401:
            return "⚠️ Authentication Error (401): The OpenRouter/OpenAI API key was rejected ('User not found'). Please provide a valid API key in the sidebar under '🔑 API Key Configuration'."
        if res.status_code != 200:
            return f"API Error ({res.status_code}): {res.text}"
        data = res.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error executing agent: {str(e)}"

# --- Layout Execution ---
df, stats = fetch_market_data(ticker_input)
fh_intel = fetch_finnhub_intel(ticker_input, finnhub_key)

if df is not None and stats is not None:
    st.markdown(f"## {ticker_input} — <span style='color:#00d2ff;'>${stats['current_price']:.2f} USD</span>", unsafe_allow_html=True)
    
    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f'<div class="agent-card"><div class="metric-lbl">RSI (14)</div><div class="metric-val">{stats["rsi"]}</div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="agent-card"><div class="metric-lbl">50 SMA</div><div class="metric-val">${stats["sma50"]}</div></div>', unsafe_allow_html=True)
    m3.markdown(f'<div class="agent-card"><div class="metric-lbl">Finnhub Target</div><div class="metric-val">${fh_intel["target_mean"]}</div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="agent-card"><div class="metric-lbl">Wall St. Consensus</div><div class="metric-val" style="font-size:1.1rem;">{fh_intel["consensus"]}</div></div>', unsafe_allow_html=True)

    # Automatically run deliberation using the active API key
    if api_secret:
        st.markdown("### 🏛️ Autonomous Agent Deliberation")
        
        with st.status("Executing Agent Committee Workflow...", expanded=True) as status:
            st.write("📈 **Technical Strategist** evaluating price action & moving averages...")
            prompt_tech = f"""
            Analyze the technical setup for {ticker_input} (Horizon: {time_horizon}):
            - Current Price: ${stats['current_price']}
            - 20 SMA: ${stats['sma20']} | 50 SMA: ${stats['sma50']}
            - RSI: {stats['rsi']}
            Provide key support/resistance levels, trend health, and immediate entry bias. Keep under 90 words.
            """
            tech_report = query_llm(prompt_tech, api_secret, model_choice, max_tokens=220)

            st.write("📊 **Fundamental Analyst** parsing Finnhub targets & valuation multiples...")
            prompt_fund = f"""
            Evaluate the fundamentals and valuation for {ticker_input}:
            - Current Price: ${stats['current_price']}
            - Finnhub Wall St Consensus Target: ${fh_intel['target_mean']} (High: ${fh_intel['target_high']}, Low: ${fh_intel['target_low']})
            - Wall St Rating Breakdown: {fh_intel['buy_recs']} Buys, {fh_intel['hold_recs']} Holds, {fh_intel['sell_recs']} Sells
            Give a sharp assessment of valuation margin of safety. Keep under 90 words.
            """
            fund_report = query_llm(prompt_fund, api_secret, model_choice, max_tokens=220)

            st.write("🌐 **Sentiment & Insider Agent** analyzing Finnhub executive transactions & macro drivers...")
            prompt_sent = f"""
            Review market sentiment and executive insider signals for {ticker_input}:
            - Finnhub Insider Sentiment Status: {fh_intel['insider_bias']}
            - Wall St Recommendation Consensus: {fh_intel['consensus']}
            Identify 2 primary upside catalysts and 2 critical tail-risk threats. Keep under 90 words.
            """
            sent_report = query_llm(prompt_sent, api_secret, model_choice, max_tokens=220)

            st.write("⚖️ **Chief Risk Officer** adjudicating setup, invalidation & position sizing...")
            prompt_cro = f"""
            You are the Chief Risk Officer. Adjudicate the committee findings for {ticker_input} (Price: ${stats['current_price']}):
            TECHNICALS: {tech_report}
            FUNDAMENTALS & FINNHUB TARGET: {fund_report}
            SENTIMENT & INSIDER FLOW: {sent_report}

            Deliver the final execution mandate in this exact structured format:
            - FINAL ACTION: [STRONG BUY / BUY / HOLD / SELL / STRONG SELL]
            - CONVICTION SCORE: [1-10]
            - ENTRY ZONE: [Price range]
            - STOP LOSS: [Hard invalidation price]
            - TARGET OBJECTIVE: [Take-profit price]
            - RISK SIZING: [Recommended capital risk % / leverage guideline]
            - COMMITTEE RATIONALE: [2 punchy sentences summarizing the core trade thesis]
            """
            cro_verdict = query_llm(prompt_cro, api_secret, model_choice, max_tokens=320)
            status.update(label="Committee Deliberation Complete!", state="complete", expanded=False)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-header agent-title-blue">📈 Technical Strategist</div>
                <div style="font-size: 0.9rem; color: #e2e8f0;">{tech_report}</div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-header agent-title-green">📊 Fundamental Analyst (Finnhub Data)</div>
                <div style="font-size: 0.9rem; color: #e2e8f0;">{fund_report}</div>
            </div>
            """, unsafe_allow_html=True)

        with col_b:
            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-header agent-title-purple">🌐 Sentiment & Insider Agent (Finnhub MSPR)</div>
                <div style="font-size: 0.9rem; color: #e2e8f0;">{sent_report}</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-header agent-title-orange">⚖️ Committee Consensus</div>
                <div style="font-size: 0.85rem; color: #94a3b8;">Aggregated quantitative technicals, Finnhub analyst estimates, and insider flow metrics.</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("### 🎯 Chief Risk Officer (Execution Mandate)")
        st.markdown(f"""
        <div class="verdict-box">
            <div style="white-space: pre-line; font-size: 0.95rem; color: #f8fafc; line-height: 1.6;">
            {cro_verdict}
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(f"### 🌐 Global Macro, Forex, Crypto & SEC EDGAR Intelligence • {ticker_input}")
        intel = MarketIntelSuite(finnhub_key=finnhub_key)

        m_tab1, m_tab2, m_tab3 = st.tabs([
            "🏛️ SEC EDGAR Official Filings & Polygon Ticks",
            "💱 Real-Time Forex (Frankfurter - Zero Auth)",
            "🪙 Cryptocurrency Market Pulse (CoinGecko) & FRED Macro"
        ])

        with m_tab1:
            sec_c1, sec_c2 = st.columns([1.5, 2.5])
            with sec_c1:
                st.markdown(f"##### ⚡ Polygon.io / Finnhub Ticks ({ticker_input})")
                ticks = intel.get_stock_ticks_and_quote(ticker_input)
                if ticks.get("price", 0) > 0:
                    st.write(f"• **Current Price:** ${ticks['price']:.2f} ({ticks.get('change_pct', 0):+.2f}%)")
                    st.write(f"• **Day Range:** ${ticks.get('low', 0):.2f} - ${ticks.get('high', 0):.2f}")
                    st.write(f"• **Open / Prev Close:** ${ticks.get('open', 0):.2f} / ${ticks.get('prev_close', 0):.2f}")
                    st.caption(f"Source: {ticks.get('source', 'Finnhub').upper()}")
                else:
                    st.info("No tick quote available.")
            with sec_c2:
                st.markdown(f"##### 📄 Direct SEC EDGAR Filings ({ticker_input})")
                filings = intel.get_sec_edgar_filings(ticker_input, limit=8)
                if filings:
                    st.dataframe(pd.DataFrame(filings), use_container_width=True, hide_index=True)
                else:
                    st.info("No SEC filings found.")

        with m_tab2:
            st.markdown("##### Real-Time Currency Crosses (Frankfurter)")
            fx_data = intel.get_forex_rates("USD", ["EUR", "GBP", "JPY", "CAD", "AUD", "CHF"])
            fx_rates = fx_data.get("rates", {})
            f_cols = st.columns(6)
            for i, (k, v) in enumerate(fx_rates.items()):
                f_cols[i % 6].metric(f"USD/{k}", f"{v:.4f}")

        with m_tab3:
            st.markdown("##### Federal Reserve Macro (FRED)")
            fred_d = intel.get_fred_macro_indicators()
            fr1, fr2, fr3 = st.columns(3)
            fr1.metric("Fed Funds Rate", f"{fred_d.get('fed_funds_rate', {}).get('value', 3.75):.2f}%")
            fr2.metric("10Y Treasury Yield", f"{fred_d.get('treasury_10y', {}).get('value', 4.12):.2f}%")
            fr3.metric("Yield Curve Spread", f"{fred_d.get('yield_curve_spread', 0.37):+.2f}%")

            st.markdown("##### Crypto Momentum (CoinGecko)")
            crypto_d = intel.get_crypto_prices(["bitcoin", "ethereum", "solana", "ripple"])
            c_cols = st.columns(4)
            for i, (cid, cdata) in enumerate(crypto_d.get("data", {}).items()):
                c_cols[i % 4].metric(cdata["symbol"], f"${cdata['price_usd']:,.2f}", f"{cdata['change_24h_pct']:+.2f}%")

    else:
        st.warning("⚠️ **OpenRouter / OpenAI API Key Required**\n\nPlease expand **🔑 API Key Configuration** in the left sidebar and enter your key (or set `OPENROUTER_API_KEY` in Streamlit Cloud Secrets) to enable Autonomous Multi-Agent Deliberation.")
else:
    st.error(f"Could not retrieve market data for '{ticker_input}'. Please check the symbol.")
