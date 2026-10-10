import os
import json
import time
import requests
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "trades.log")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError("config.json not found!")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    print(formatted)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def get_headers(cfg):
    return {
        "x-user-key": cfg["public_key"],
        "x-api-key": cfg["api_key"],
        "Content-Type": "application/json"
    }

def fetch_open_positions(headers):
    url = "https://public-api.etoro.com/api/v1/trading/positions"
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            return resp.json().get("positions", [])
        elif resp.status_code == 401:
            save_log("❌ Error 401: Unauthorized. Please check your public_key and api_key in config.json")
    except Exception as e:
        save_log(f"⚠️ Network error fetching positions: {e}")
    return []

def close_position(headers, position_id, symbol, reason, pnl_pct):
    url = f"https://public-api.etoro.com/api/v1/trading/positions/{position_id}/close"
    try:
        resp = requests.post(url, headers=headers, json={}, timeout=12)
        if resp.status_code in [200, 202]:
            save_log(f"🎯 CLOSED {symbol} | Reason: {reason} | P&L: {pnl_pct:+.2f}%")
            return True
        else:
            save_log(f"⚠️ Failed to close {symbol} (HTTP {resp.status_code}): {resp.text}")
    except Exception as e:
        save_log(f"❌ Error closing {symbol}: {e}")
    return False

def manage_positions_and_exit(headers, cfg, positions):
    tp_threshold = cfg.get("take_profit_percent", 3.0)
    sl_threshold = cfg.get("stop_loss_percent", -2.5)

    closed_count = 0
    for pos in positions:
        pos_id = pos.get("positionId")
        symbol = pos.get("symbol", "N/A")
        invested = pos.get("invested", 0)
        pnl = pos.get("pnl", 0)
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0.0

        # Auto-Exit Check
        if pnl_pct >= tp_threshold:
            if close_position(headers, pos_id, symbol, f"Take Profit Target (+{tp_threshold}%) Reached", pnl_pct):
                closed_count += 1
        elif pnl_pct <= sl_threshold:
            if close_position(headers, pos_id, symbol, f"Stop Loss ({sl_threshold}%) Triggered", pnl_pct):
                closed_count += 1

    return closed_count

def fetch_market_overview(headers, symbols):
    url = "https://public-api.etoro.com/api/v1/market-data/instruments/overview"
    try:
        resp = requests.get(url, headers=headers, params={"symbols": ",".join(symbols)}, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("instruments", [])
    except Exception as e:
        save_log(f"⚠️ Error querying market data: {e}")
    return []

def score_instrument(inst):
    eligibility = inst.get("eligibility", {})
    if not eligibility.get("allowOpenPosition", False):
        return 0, "Market Closed"

    perf = inst.get("performance", {})
    daily_chg = perf.get("dailyChangePercent", 0) * 100
    weekly_chg = perf.get("weeklyChangePercent", 0) * 100

    score = 0
    if daily_chg > 2.0 and weekly_chg > 0:
        score += 50
    elif daily_chg > 0.5:
        score += 30

    quote = inst.get("quote", {})
    spread = quote.get("spread", 999)
    if spread < 0.3:
        score += 30
    elif spread < 1.0:
        score += 15

    if 1.0 <= daily_chg <= 8.0:
        score += 20

    return score, f"Daily: {daily_chg:+.2f}%, Spread: {spread}"

def open_trade(headers, symbol, amount_usd):
    url = "https://public-api.etoro.com/api/v1/trading/orders"
    payload = {
        "symbol": symbol,
        "amount": amount_usd,
        "direction": "buy",
        "orderType": "mkt"
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        if resp.status_code in [200, 201, 202]:
            save_log(f"🚀 OPENED BUY Order: {symbol} (${amount_usd})")
            return True
        else:
            save_log(f"⚠️ Trade rejected for {symbol} (HTTP {resp.status_code}): {resp.text}")
    except Exception as e:
        save_log(f"❌ Error placing trade for {symbol}: {e}")
    return False

def display_dashboard(cfg, positions):
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 70)
    print(f"🤖  eToro Autonomous Multi-Asset Trading Bot (PC Local Edition)")
    print(f"📅  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  Account: {cfg.get('account_type', 'real').upper()}")
    print(f"🎯  Take Profit: +{cfg.get('take_profit_percent')}%  |  🛑  Stop Loss: {cfg.get('stop_loss_percent')}%")
    print(f"📊  Open Positions: {len(positions)} / {cfg.get('max_open_positions', 7)} max")
    print("=" * 70)

    if positions:
        print(f"{'SYMBOL':<10} {'INVESTED':<12} {'CURRENT VAL':<14} {'P&L ($)':<12} {'P&L (%)':<10}")
        print("-" * 70)
        total_pnl = 0
        for p in positions:
            sym = p.get("symbol", "N/A")
            inv = p.get("invested", 0)
            val = p.get("currentValue", 0)
            pnl = p.get("pnl", 0)
            pct = (pnl / inv * 100) if inv > 0 else 0
            total_pnl += pnl
            print(f"{sym:<10} ${inv:<11.2f} ${val:<13.2f} ${pnl:<11.2f} {pct:+.2f}%")
        print("-" * 70)
        print(f"Total Unrealized P&L: ${total_pnl:+.2f}")
    else:
        print("No open positions. Scanner is searching for opportunities...")

    print("=" * 70)
    print("Watching positions and scanning markets... (Press Ctrl+C to stop)\n")

def main():
    cfg = load_config()
    if cfg["public_key"] == "YOUR_PUBLIC_KEY_HERE" or cfg["api_key"] == "YOUR_API_KEY_HERE":
        print("⚠️  Please open config.json and enter your real eToro Public Key and API Key first!")
        return

    headers = get_headers(cfg)
    save_log("🚀 Trading Bot Started on Local PC.")

    while True:
        try:
            # 1. Fetch Positions
            positions = fetch_open_positions(headers)
            
            # 2. Check for Take Profit & Stop Loss to close
            manage_positions_and_exit(headers, cfg, positions)

            # Re-fetch positions after exits
            positions = fetch_open_positions(headers)
            display_dashboard(cfg, positions)

            # 3. If under max positions, scan watchlist for new entries
            max_pos = cfg.get("max_open_positions", 7)
            if len(positions) < max_pos:
                watchlist = cfg.get("watchlist", [])
                instruments = fetch_market_overview(headers, watchlist)
                
                scored_list = []
                held_symbols = [p.get("symbol") for p in positions]

                for inst in instruments:
                    sym = inst.get("market", {}).get("symbol")
                    if sym in held_symbols:
                        continue # Already holding this asset
                    
                    score, rationale = score_instrument(inst)
                    if score >= 75:
                        scored_list.append((sym, score, rationale))

                # Sort by score descending
                scored_list.sort(key=lambda x: x[1], reverse=True)

                if scored_list:
                    best_sym, best_score, best_rat = scored_list[0]
                    save_log(f"💡 High Opportunity Detected: {best_sym} (Score {best_score}/100 - {best_rat})")
                    trade_amt = cfg.get("trade_amount_usd", 50.0)
                    open_trade(headers, best_sym, trade_amt)

        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user.")
            break
        except Exception as e:
            save_log(f"⚠️ Unexpected error in main loop: {e}")

        interval = cfg.get("scan_interval_seconds", 60)
        time.sleep(interval)

if __name__ == "__main__":
    main()
