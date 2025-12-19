# position_manager.py
from datetime import datetime, timedelta, time as dt_time
import time
import pytz
import threading

from eligible_stocks import load_stocks_for_today
from state_manager import trading_state as state
from service_ws import ws_manager
from telegram.sender import TelegramSender

# ----------------------------
# Globals
# ----------------------------

_candle_buffers = {}     # { token(int): { ticks: [(ts, price)], current_period_end } }

TZ = pytz.timezone("Asia/Kolkata")
SQUAREOFF_TIME = dt_time(15, 0, 0)
CANDLE_INTERVAL = 3      # minutes

_monitor_thread = None




# ----------------------------
# PUBLIC API
# ----------------------------
def start_position_monitor_handler():
    print("\n=== START POSITION MONITOR REQUEST ===")

    global _monitor_thread

    kite = state.get("kite")
    positions = kite.positions()["net"]

    

    if state.get("Monitoring_Background"):
        print("❌ Monitor already running.")    
        return {"success": False, "error": "Monitor already running"}

    if not positions:
        return {"success": False, "error": "No positions found"}

    # Restart WS fresh
    ws_manager.stop()
    time.sleep(0.5)
    ws_manager.start()
    time.sleep(1)
    print("WebSocket restarted for position monitoring.")

    state["is_running"] = True
    _monitor_thread = threading.Thread(
        target=_monitor_position_loop,
        args=(positions,),
        daemon=True
    )
    _monitor_thread.start()

    return {"success": True, "message": "Monitor started"}






# ----------------------------
# Helpers
# ----------------------------
def _targets_for_side(entry, side):
    sign = -1 if side.upper() == "SELL" else 1

    percents = []
    if state.get("target_1_enabled", True):
        percents.append(state.get("target_1_percent", 0.01))

    if state.get("target_2_enabled", False):
        percents.append(state.get("target_2_percent", 0.02))

    return [round(entry * (1 + sign * p), 4) for p in percents]



# ----------------------------
# Candle Aggregation
# ----------------------------
def _init_candle_buffer(token: int):
    """
    Initialize candle buffer aligned with market standard intervals.
    Market opens at 9:15, so candles align to: 9:15, 9:18, 9:21, 9:24, etc.
    """
    now = datetime.now(TZ)
    
    # Calculate minutes since market open (9:15)
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    
    if now < market_open:
        # Before market open, align to market open
        this_start = market_open
    else:
        # Calculate minutes elapsed since 9:15
        minutes_since_open = int((now - market_open).total_seconds() / 60)
        
        # Find which candle period we're in
        candle_number = minutes_since_open // CANDLE_INTERVAL
        
        # Calculate start of current candle
        minutes_to_add = candle_number * CANDLE_INTERVAL
        this_start = market_open + timedelta(minutes=minutes_to_add)
    
    this_end = this_start + timedelta(minutes=CANDLE_INTERVAL)
    
    _candle_buffers[token] = {
        "ticks": [],
        "current_period_end": this_end,
        "current_period_start": this_start
    }
    print(f"[INIT] Candle buffer initialized (market-aligned):")
    print(f"      Start: {this_start.strftime('%H:%M:%S')}")
    print(f"      End: {this_end.strftime('%H:%M:%S')}")
    print(f"      (Aligns with 9:15, 9:18, 9:21... standard market intervals)")


def _add_tick_for_candle(token: int, price: float, ts):
    if token not in _candle_buffers:
        _init_candle_buffer(token)
    _candle_buffers[token]["ticks"].append((ts, price))


def _compute_and_clear_candle_if_period_finished(token: int):
    buf = _candle_buffers.get(token)
    if not buf:
        return None

    now = datetime.now(TZ)
    
    # Calculate time remaining in current candle
    time_remaining = (buf["current_period_end"] - now).total_seconds()

    # Check if current period has ended
    if now >= buf["current_period_end"]:
        ticks = buf["ticks"]

        if ticks:
            prices = [p for _, p in ticks]
            candle = {
                "period_start": str(buf["current_period_start"]),
                "period_end": str(buf["current_period_end"]),
                "open": prices[0],
                "high": max(prices),
                "low": min(prices),
                "close": prices[-1],
                "tick_count": len(ticks)
            }            
        else:            
            candle = None

        # Move to next candle period
        old_end = buf["current_period_end"]
        buf["current_period_start"] = old_end
        buf["current_period_end"] = old_end + timedelta(minutes=CANDLE_INTERVAL)
        buf["ticks"] = []

        print(f"➡️ Next candle: start={buf['current_period_start']}, end={buf['current_period_end']}")

        return candle
    
    # Return None but provide info about when candle will close
    return {"status": "building", "closes_in": int(time_remaining), "tick_count": len(buf["ticks"])}


# ----------------------------
# Order / Stop / Exit Handlers
# ----------------------------
def _handle_target_hit(name, symbol, token, qty, price):
    print(f"\n🎯 Target {name} HIT for {symbol}")
    print(f"✅ [{name}] {symbol} qty={qty} booked at {price}")

    message = (
        "🎯 *TARGET ACHIEVED*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🏷 *Symbol*      : `{symbol}`\n"
        f"🎯 *Target*      : `{name}`\n"
        f"📦 *Quantity*    : `{qty}`\n"
        f"💰 *Exit Price*  : `{price}`\n"
        "\n"
        "✅ _Profit booked successfully_"
    )

    TelegramSender.send_message(
        message,
        parse_mode="Markdown"
    )



def _handle_stoploss(symbol, token, qty, price, sl, side):
    print(f"⚠️ STOPLOSS HIT for {symbol}")
    print(f"   Close Price: {price}")
    print(f"   Stop Loss: {sl}")
    print(f"   Side: {side}")

    message = (
        "⚠️ *STOPLOSS TRIGGERED*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🏷 *Symbol*        : `{symbol}`\n"
        f"🔁 *Side*          : `{side}`\n"
        f"📦 *Quantity*      : `{qty}`\n"
        f"💰 *Exit Price*    : `{price}`\n"
        f"🛑 *Stop Loss*     : `{sl}`\n"
        "\n"
        "🔻 _Position exited to control risk_"
    )

    TelegramSender.send_message(
        message,
        parse_mode="Markdown"
    )

    state["Monitoring_Background"] = False


def _position_status(symbol, token, qty_closed, price, reason):
    print(f"\n🔒 Position Closed: {symbol}")
    print(f"   Quantity: {qty_closed}")
    print(f"   Price: {price}")
    print(f"   Reason: {reason}")

    state["position_status"]["closed"] = True
    state["is_running"] = False
    state["current_step"] = "position_closed"
    state["Monitoring_Background"] = False

    try:
        ws_manager.stop()
    except Exception as e:
        print(f"Error stopping WS: {e}")


# ----------------------------
# MAIN POSITION MONITOR LOOP
def _monitor_position_loop(positions):
    active_pos = next((p for p in positions if int(p.get("quantity", 0)) != 0), None)
    print(f"Active Position: {active_pos}")

    if not active_pos:
        print("❌ No open position to monitor.")
        state["is_running"] = False
        return

    token = int(active_pos["instrument_token"])
    symbol = active_pos["tradingsymbol"]

    qty_total = abs(int(active_pos["quantity"]))
    side = "SELL" if int(active_pos["quantity"]) < 0 else "BUY"
    entry = float(active_pos["average_price"])

    # 🔒 Targets (dynamic, same math as before)
    targets = _targets_for_side(entry, side)

    # Stop loss (unchanged)
    stocks = load_stocks_for_today()
    sl = None
    for st in stocks:
        if st["instrument_token"] == token:
            sl = float(st.get("high"))
            break

    print("\n=== POSITION MONITOR STARTED ===")
    print(f"Symbol: {symbol} | Side: {side}")
    print(f"Entry: {entry} | Qty: {qty_total}")
    print(f"Targets: {targets}")
    print(f"Stop Loss: {sl}")
    print("=" * 50)

    message = (
        "🎯 *POSITION MONITOR STARTED*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🏷 *Symbol*      : `{symbol}`\n"
        f"💰 *Exit Price*  : `{entry}`\n"      
        f"📦 *Quantity*    : `{qty_total}`\n"
        f"🎯 *Target*      : `{targets}`\n"        
        "\n"
        
    )

    TelegramSender.send_message(
        message,
        parse_mode="Markdown"
    )

    # 🔒 Position state (clean but equivalent)
    state["position_status"] = {
        "targets": targets,
        "current_target": 0,
        "qty_remaining": qty_total,
        "closed": False,
    }

    # Candle buffer (UNCHANGED)
    _init_candle_buffer(token)

    ws_manager.subscribe([token])
    time.sleep(1)

    last_price = None
    tick_count = 0

    while state.get("is_running", False):
        tick_count += 1
        state["Monitoring_Background"] = True

        tick = state.get("live_data", {}).get(token)

        if tick:
            last_price = float(tick.get("last_price") or tick.get("last") or 0)
            now = datetime.now(TZ)
            _add_tick_for_candle(token, last_price, now)
            print(f"[{now.strftime('%H:%M:%S')}] {symbol} = {last_price}")

        # ==================================================
        # 🔒 CANDLE LOGIC — NOT TOUCHED
        # ==================================================
        candle = _compute_and_clear_candle_if_period_finished(token)

        if candle and isinstance(candle, dict) and "close" in candle:
            close_price = float(candle["close"])

            if sl is not None:
                sl_hit = (
                    (side == "SELL" and close_price > sl) or
                    (side == "BUY" and close_price < sl)
                )

                if sl_hit:
                    _handle_stoploss(symbol, token, qty_total, close_price, sl, side)
                    order_place(symbol , qty_total)
                    _position_status(
                        symbol,
                        token,
                        state["position_status"]["qty_remaining"],
                        close_price,
                        "STOPLOSS",
                    )
                    return

        # ==================================================
        # 🎯 TARGET LOGIC (SIMPLIFIED, SAME BEHAVIOR)
        # ==================================================
        if last_price is not None:
            ps = state["position_status"]
            idx = ps["current_target"]
            targets = ps["targets"]

            if idx < len(targets):
                target_price = targets[idx]

                hit = (
                    (side == "BUY" and last_price >= target_price) or
                    (side == "SELL" and last_price <= target_price)
                )

                if hit:
                    remaining = ps["qty_remaining"]

                    # Same quantity logic as before
                    if len(targets) > 1 and idx == 0:
                        qty_to_book = remaining // 2
                    else:
                        qty_to_book = remaining

                    _handle_target_hit(
                        f"T{idx + 1}", symbol, token, qty_to_book, last_price
                    )
                    
                    order_place(symbol , qty_total)

                    ps["qty_remaining"] -= qty_to_book
                    ps["current_target"] += 1

                    # Last target reached
                    if ps["current_target"] >= len(targets):
                        _position_status(
                            symbol, token, 0, last_price, "TARGETS_FILLED"
                        )
                        order_place(symbol , qty_total)
                        state["Monitoring_Background"] = False
                        state['engine_status'] = 'STOPPED'        
                        state['is_running'] = False
                        return

        # ==================================================
        # ⏰ EOD SQUAREOFF (UNCHANGED)
        # ==================================================
        if datetime.now(TZ).time() >= SQUAREOFF_TIME:
            _position_status(
                symbol,
                token,
                state["position_status"]["qty_remaining"],
                last_price,
                "SQUAREOFF_EOD",
            )
            order_place(symbol , qty_total)
            state["Monitoring_Background"] = False
            return
        
        state['engine_status'] = 'STOPPED'        
        state['is_running'] = False

        time.sleep(1)

    # Manual stop (UNCHANGED)
    print("🛑 Monitor stopped manually.")
    _position_status(
        symbol,
        token,
        state["position_status"]["qty_remaining"],
        last_price,
        "MANUAL_STOP",
    )



def order_place(symbol, qty  ):

    kite = state.get("kite")

    try:

        order_number = kite.place_order(
                                variety=kite.VARIETY_REGULAR,
                                exchange=kite.EXCHANGE_NSE,
                                tradingsymbol=symbol,
                                transaction_type=kite.TRANSACTION_TYPE_SELL,
                                quantity=1,
                                product=kite.PRODUCT_MIS,
                                order_type=kite.ORDER_TYPE_MARKET,                            
                                price=None,
                                validity=kite.VALIDITY_DAY,
                                trigger_price=None,
                                trailing_stoploss=None,
                                tag="ALGO_TRADE_PRADEEP")
    except Exception as e:
        order_number = 123454321
        error_message = (
            "❌ *ORDER PLACEMENT FAILED*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🏷 *Symbol*     : `{symbol}`\n"
            f"🔻 *Side*       : `SELL`\n"
            f"📦 *Quantity*  : `{qty}`\n"
            f"⚠️ *Reason*    : `Not Able to Place order Check immediately `\n"
            "\n"
            "🛑 _Order NOT sent to exchange_"
        )

        TelegramSender.send_message(
            error_message,
            parse_mode="Markdown"
        )

    message = format_order_placed_message(symbol, qty, order_number)

    TelegramSender.send_message(
        message,
        parse_mode="Markdown"
    )
    

    print(f"Placing order: {symbol} | Qty: {qty} |  | order : {order_number} "   )


def format_order_placed_message(symbol, qty, order_id):
    return (
        "📤 *ORDER PLACED SUCCESSFULLY*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Symbol*      : `{symbol}`\n"
        f"🔻 *Side*        : `SELL`\n"
        f"📦 *Quantity*   : `{qty}`\n"
        f"🧾 *Order ID*   : `{order_id}`\n"
        "\n"
        "⚡ _Order sent to exchange via Algo Engine_"
    )
