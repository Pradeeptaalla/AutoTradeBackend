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
from util import get_kite

now_utc = datetime.now(timezone.utc)

from logger_config import setup_logger

logger = setup_logger("eligible_stocks")

ELIGIBILITY_FILE = "eligibility_state.json"

def mark_stock_updated():
    state["last_stock_update"] = datetime.now(timezone.utc)


def run_eligibility_if_needed():
    last_update = state["last_stock_update"]
    last_check = state["last_eligibility_check"]

    # First time → run
    if last_check is None:
        logger.info("🔄 First eligibility run")
        return True

    # No stock update → skip
    if last_update is None:
        logger.info("⚡ No stock update, skipping")
        return False

    # Stock updated after last eligibility run → run
    if last_update > last_check:
        logger.info("🔄 Stock updated after last check → run eligibility")
        return True

    # Otherwise → skip
    logger.info("⚡ Eligibility already up to date")
    return False


def save_eligibility_json(payload):
    """Write eligibility results to JSON file."""
    try:
        with open(ELIGIBILITY_FILE, "w") as f:
            json.dump(payload, f, indent=4)
        logger.info(f"✓ Saved eligibility results → {ELIGIBILITY_FILE}")
    except Exception as e:
        logger.exception("❌ Error saving eligibility JSON")


def get_stock_file():
    try:
        from app import STOCKS_DATABASE_FILE
        return STOCKS_DATABASE_FILE
    except:
        return "stocks_database.xlsx"


def load_stocks_for_today():
    stock_file = get_stock_file()

    if not os.path.exists(stock_file):
        logger.info("Stock file not found:", stock_file)
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
            logger.exception("❌ Row parse error:")
            continue
    
    logger.info(f"✓ Loaded {len(stocks)} stocks for {today_str} from {stock_file}")

    state["stock_load_list"] = stocks
    logger.info(f"Stocks for today: {state.get('stock_load_list', [])}")
    return stocks


def run_eligibility(force: bool = False):
    """
    PRODUCTION-SAFE eligibility check.
    - Always starts WebSocket from clean state
    - Handles prod latency
    - Handles int/str token mismatch
    - Deterministic behavior
    """

    logger.info("🚀 run_eligibility called | force=%s", force)

    # ============================================================
    # 1️⃣ Load stocks
    # ============================================================
    stocks = load_stocks_for_today()
    if not stocks:
        logger.error("❌ No stocks loaded for today")
        return {"success": False, "error": "No stocks for today"}

    stock_count = len(stocks)
    logger.info("📦 Loaded %s stocks", stock_count)

    # ============================================================
    # 2️⃣ Cache logic
    # ============================================================
    if not force:
        if not run_eligibility_if_needed():
            logger.info("⚡ Returning cached eligibility result")
            return state.get("eligibility_result", {})
        logger.info("🔄 Running fresh eligibility check")
    else:
        logger.info("🔥 Force enabled — ignoring cache")

    # ============================================================
    # 3️⃣ FORCE CLEAN WEBSOCKET STATE (CRITICAL FOR PROD)
    # ============================================================
    logger.info("🧹 Resetting WebSocket state before eligibility")

    try:
        ws_manager.stop()
    except Exception:
        logger.exception("WS stop error (pre-eligibility)")

    time.sleep(0.5)

    # hard reset flags (prevents zombie WS in prod)
    ws_manager.kws = None
    ws_manager.connected = False
    ws_manager.running = False

    kite =get_kite(state["username"])
    # ============================================================
    # 4️⃣ Setup WebSocket (FRESH)
    # ============================================================
    logger.info("🔧 Setting up WebSocket (fresh)")

    if not ws_manager.setup("PradeepApi", state["enctoken"], state["user_id"]):
        logger.error("❌ WebSocket setup failed")
        return {"success": False, "error": "WebSocket setup failed"}

    logger.info("▶ Starting WebSocket thread")
    ws_manager.start()

    # ============================================================
    # 5️⃣ Wait for WebSocket connection (PROD SAFE)
    # ============================================================
    for i in range(20):  # longer wait for prod latency
        logger.info(
            "⏳ Waiting for WS connection (%s/20) | connected=%s running=%s",
            i + 1,
            ws_manager.connected,
            ws_manager.running
        )
        if ws_manager.connected:
            break
        time.sleep(0.5)

    if not ws_manager.connected:
        logger.error("❌ WebSocket not connected (timeout)")
        return {"success": False, "error": "WebSocket not connected"}

    state["websocket_status"] = "Connected"
    logger.info("🟢 WebSocket connected")

    # ============================================================
    # 6️⃣ Subscribe tokens (INT ONLY)
    # ============================================================
    tokens = [int(s["instrument_token"]) for s in stocks]
    logger.info("📡 Subscribing tokens (INT): %s", tokens)

    ws_manager.subscribe(tokens)

    # ============================================================
    # 7️⃣ Wait for first tick (deterministic)
    # ============================================================
    logger.info("⏳ Waiting for ticks...")
    for i in range(20):
        live_keys = list(state.get("live_data", {}).keys())
        logger.info("⏳ Tick wait %s/20 | live_data keys=%s", i + 1, live_keys)

        if any(
            str(s["instrument_token"]) in state["live_data"]
            or s["instrument_token"] in state["live_data"]
            for s in stocks
        ):
            logger.info("✅ At least one tick received")
            break

        time.sleep(0.5)

    # ============================================================
    # 8️⃣ Eligibility logic (UNCHANGED)
    # ============================================================
    eligible, not_el, doji, errors = [], [], [], []

    for st in stocks:
        sym = st["symbol"]
        token_int = int(st["instrument_token"])
        token_str = str(token_int)
        H, L = st["high"], st["low"]

        tick = (
            state["live_data"].get(token_int)
            or state["live_data"].get(token_str)
        )

        logger.info(
            "🔍 Processing %s | token=%s | tick_exists=%s",
            sym,
            token_int,
            tick is not None
        )

        if not tick:
            errors.append(f"{sym}: No tick")
            continue

        try:
            open_p = float(tick["ohlc"]["open"])
            last = float(tick["last_price"])
        except Exception:
            logger.exception("❌ Bad tick structure for %s", sym)
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

    # ============================================================
    # 9️⃣ Save + Notify
    # ============================================================
    message = format_eligible_stocks_message(eligible)
    TelegramSender.send_message(message, parse_mode="Markdown")

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
        "websocket_status": state.get("websocket_status", "Disconnected"),
    }

    save_eligibility_json(result)

    state.update({
        "eligibility_result": result,
        "eligibility_date": date.today().isoformat(),
        "stocks_count": stock_count,
    })

    # ============================================================
    # 🔟 Cleanup (FULL RESET)
    # ============================================================
    logger.info("🛑 Stopping WebSocket (eligibility cleanup)")

    try:
        ws_manager.stop()
    except Exception:
        logger.exception("WS stop error (eligibility cleanup)")

    ws_manager.kws = None
    ws_manager.connected = False
    ws_manager.running = False

    state["websocket_status"] = "Disconnected"
    state["last_eligibility_check"] = datetime.now(timezone.utc)

    logger.info("✅ Eligibility completed successfully")
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


