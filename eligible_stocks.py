# eligible_stocks.py
import json, os, time , os, pandas as pd
from datetime import date, datetime
from flask import jsonify, session

# shared state
from state_manager import trading_state as state

# websocket & stocks service
from service_ws import ws_manager
# from service_stocks import load_stocks_for_today


from datetime import datetime, timezone

from telegram.sender import TelegramSender

now_utc = datetime.now(timezone.utc)



ELIGIBILITY_FILE = "eligibility_state.json"

def mark_stock_updated():
    state["last_stock_update"] = datetime.now(timezone.utc)


def run_eligibility_if_needed():
    last_update = state["last_stock_update"]
    last_check = state["last_eligibility_check"]

    # First time → run
    if last_check is None:
        print("🔄 First eligibility run")
        return True

    # No stock update → skip
    if last_update is None:
        print("⚡ No stock update, skipping")
        return False

    # Stock updated after last eligibility run → run
    if last_update > last_check:
        print("🔄 Stock updated after last check → run eligibility")
        return True

    # Otherwise → skip
    print("⚡ Eligibility already up to date")
    return False


def save_eligibility_json(payload):
    """Write eligibility results to JSON file."""
    try:
        with open(ELIGIBILITY_FILE, "w") as f:
            json.dump(payload, f, indent=4)
        print("✓ Saved eligibility results →", ELIGIBILITY_FILE)
    except Exception as e:
        print("❌ Error saving JSON:", e)


def get_stock_file():
    try:
        from app import STOCKS_DATABASE_FILE
        return STOCKS_DATABASE_FILE
    except:
        return "stocks_database.xlsx"


def load_stocks_for_today():
    stock_file = get_stock_file()

    if not os.path.exists(stock_file):
        print("Stock file not found:", stock_file)
        return []

    df = pd.read_excel(stock_file, dtype=str)
    today_str = date.today().strftime("%Y-%m-%d")

    # Normalize date
    def norm(v):
        if pd.isna(v): return ""
        if isinstance(v, pd.Timestamp): return v.strftime("%Y-%m-%d")
        return str(v).strip()

    df["date_norm"] = df["date"].apply(norm)
    rows = df[df["date_norm"] == today_str]
    if rows.empty: return []

    stocks = []
    for _, row in rows.iterrows():
        try:
            symbol = str(row["symbol"]).strip()
            token = int(str(row["instrument_token"]).replace(",", "").strip())
            high = float(str(row["high"]).replace(",", "").strip())
            low = float(str(row["low"]).replace(",", "").strip())

            stocks.append({
                "symbol": symbol,
                "instrument_token": token,
                "high": high,
                "low": low
            })
        except Exception as e:
            print("Row parse error:", e)
            continue
    
    print(f"✓ Loaded {len(stocks)} stocks for {today_str} from {stock_file}")

    state["stock_load_list"] = stocks
    print("Stocks for today:", state.get("stock_load_list", []))
    return stocks



def run_eligibility():    

    # 1️⃣ Load stocks
    stocks = load_stocks_for_today()
    if not stocks:
        return {"success": False, "error": "No stocks for today"}

    stock_count = len(stocks)

    if not run_eligibility_if_needed():
        print("⚡ Returning cached eligibility data")
        return state["eligibility_result"]

    print("🔄 Running fresh eligibility check")



    # 3️⃣ WebSocket setup
    if not ws_manager.kws:
        if not ws_manager.setup("PradeepApi", state["enctoken"], state["user_id"]):
            return {"success": False, "error": "WebSocket setup failed"}

    if not ws_manager.running:
        ws_manager.start()

    for _ in range(10):
        if ws_manager.connected:
            break
        time.sleep(0.5)

    if not ws_manager.connected:
        return {"success": False, "error": "WebSocket not connected"}

    state["websocket_status"] = "Connected"

    # 4️⃣ Subscribe tokens
    tokens = [s["instrument_token"] for s in stocks]
    ws_manager.subscribe(tokens)
    time.sleep(2)

    # 5️⃣ Eligibility logic
    eligible, not_el, doji, errors = [], [], [], []

    for st in stocks:
        sym = st["symbol"]
        tok = st["instrument_token"]
        H, L = st["high"], st["low"]

        tick = state["live_data"].get(tok)
        if not tick:
            errors.append(f"{sym}: No tick")
            continue

        try:
            open_p = float(tick["ohlc"]["open"])
            last = float(tick["last_price"])
        except:
            errors.append(f"{sym}: Bad tick")
            continue

        if open_p > H:
            not_el.append({**st, "open": open_p, "last": last, "reason": "open > high"})
        elif open_p == L:
            not_el.append({**st, "open": open_p, "last": last, "reason": "open == low"})
        elif L < open_p < H:
            doji.append({**st, "open": open_p, "last": last})
        elif open_p < L:
            percent = round((H - last) / last * 100, 2)
            eligible.append({**st, "open": open_p, "last": last, "percent": percent})
        else:
            errors.append(f"{sym}: Uncategorized")


    
    message = format_eligible_stocks_message(eligible)

    TelegramSender.send_message(
        message,
        parse_mode="Markdown"
    )

    # 6️⃣ Build response (frontend compatible)
    state["eligible_stocks"] = eligible
    state["not_eligible_stocks"] = not_el
    state["doji_eligible_stocks"] = doji

    result = {
        "success": True,
        "eligible": eligible,
        "not_eligible": not_el,
        "doji_eligible": doji,
        "errors": errors,
        "total_checked": stock_count,
        "websocket_status": state.get("websocket_status", "Disconnected")
    }

    save_eligibility_json(result)

    # 7️⃣ Save cache
    state.update({
        "eligibility_result": result,
        "eligibility_date": date.today().isoformat(),
        "stocks_count": stock_count
    })

    # 8️⃣ Cleanup
    ws_manager.stop()
    state["websocket_status"] = "Disconnected"
    state["last_eligibility_check"] = datetime.now(timezone.utc)
    return result



def format_eligible_stocks_message(stocks):
    # 🔢 Sort by closest to high
    stocks = sorted(stocks, key=lambda x: x.get("percent_to_high", 999))

    lines = [
        "🚀 *Trading Monitor Activated*",
        "━━━━━━━━━━━━━━━━━━",
        "🔻 *Sell-Side Eligible Stocks (Closest First)*",
        ""
    ]

    for i, stock in enumerate(stocks, start=1):
        pct = stock.get("percent_to_high", 0)

        # 🎨 Color emoji
        if pct <= 1:
            emoji = "🟢"
        elif pct <= 3:
            emoji = "🟡"
        else:
            emoji = "🔴"

        lines.extend([
            f"📌 *{i}. {stock['symbol']}* {emoji}",
            f"   🆔 Token        : `{stock['instrument_token']}`",
            f"   🔼 Day High     : `{stock['high']}`",
            f"   💰 Last Price   : `{stock['last']}`",
            f"   📈 *Move to High*: `{pct}%`",           
            ""
        ])

    lines.append("🤖 _Sell-side monitoring in progress…_")

    return "\n".join(lines)


