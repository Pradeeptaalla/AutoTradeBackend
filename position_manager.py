# position_manager.py
from datetime import datetime, timedelta, time as dt_time
import time
import uuid
from flask import session
import pytz
import threading

from eligible_stocks import load_stocks_for_today
from state_manager import trading_state as state
from service_ws import ws_manager
from telegram.sender import TelegramSender

from logger_config import setup_logger
from util import get_kite

logger = setup_logger("position_manager")

# ----------------------------
# Globals
# ----------------------------

_candle_buffers = {}     # { token(int): { ticks: [(ts, price)], current_period_end } }

TZ = pytz.timezone("Asia/Kolkata")


_monitor_thread = None




# ----------------------------
# PUBLIC API
# ----------------------------
def start_position_monitor_handler():
    logger.info("\n=== START POSITION MONITOR REQUEST ===")

    global _monitor_thread

    kite =get_kite(state["username"])
    positions = kite.positions()["net"]

    if not positions:
        return {"success": False, "error": "No positions found"}
    
  

    # ============================================================
    # 🔥 PRODUCTION SAFE WEBSOCKET RESET (UNCHANGED INTENT)
    # ============================================================
    if ws_manager.running:
        logger.info("🧹 Stopping previous WebSocket cleanly")
        ws_manager.stop()
        time.sleep(0.5)

    # ------------------------------------------------------------
    # 5️⃣ Setup WebSocket (UNCHANGED FLOW)
    # ------------------------------------------------------------
    if not ws_manager.setup("PradeepApi", state["enctoken"], state["user_id"]):
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "WebSocket setup failed"}

    if not ws_manager.start():
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "WebSocket start failed"}

    # ------------------------------------------------------------
    # 6️⃣ Wait for WebSocket connection (UNCHANGED)
    # ------------------------------------------------------------
    for i in range(20):
        if ws_manager.connected:
            logger.info("🟢 WS Connected")
            break
        logger.info("⏳ Waiting for WS (%s/20)", i + 1)
        time.sleep(0.5)
    else:
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "WebSocket connection failed"}


                  
    run_id = uuid.uuid4().hex
    state["is_running"] = True
    state["run_id"] = run_id
    _monitor_thread = threading.Thread(
        target=_monitor_position_loop,
        args=(positions,run_id,),
        daemon=True
    )
    _monitor_thread.start()

    return {"success": True, "message": "Monitor started"}






# ----------------------------
# Helpers
# ----------------------------
def _target_for_side(entry, side):
    sign = -1 if side.upper() == "SELL" else 1

    percent = state.get("target_1_percent", 0.01)

    return round(entry * (1 + sign * percent), 4)




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
        candle_number = minutes_since_open // state["CANDLE_INTERVAL"]
        
        # Calculate start of current candle
        minutes_to_add = candle_number * state["CANDLE_INTERVAL"]
        this_start = market_open + timedelta(minutes=minutes_to_add)
    
    this_end = this_start + timedelta(minutes=state["CANDLE_INTERVAL"])
    
    _candle_buffers[token] = {
        "ticks": [],
        "current_period_end": this_end,
        "current_period_start": this_start
    }
    logger.info(f"[INIT] Candle buffer initialized (market-aligned):")
    logger.info(f"      Start: {this_start.strftime('%H:%M:%S')}")
    logger.info(f"      End: {this_end.strftime('%H:%M:%S')}")
    logger.info(f"      (Aligns with 9:15, 9:18, 9:21... standard market intervals)")


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
        buf["current_period_end"] = old_end + timedelta(minutes=state["CANDLE_INTERVAL"])
        buf["ticks"] = []

        logger.info(f"➡️ Next candle: start={buf['current_period_start']}, end={buf['current_period_end']}")

        return candle
    
    # Return None but provide info about when candle will close
    return {"status": "building", "closes_in": int(time_remaining), "tick_count": len(buf["ticks"])}


# ----------------------------
# Order / Stop / Exit Handlers
# ----------------------------
def _handle_target_hit(name, symbol, token, qty, price):
    logger.info(f"\n🎯 Target {name} HIT for {symbol}")
    logger.info(f"✅ [{name}] {symbol} qty={qty} booked at {price}")

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
    logger.info(f"⚠️ STOPLOSS HIT for {symbol}")
    logger.info(f"   Close Price: {price}")
    logger.info(f"   Stop Loss: {sl}")
    logger.info(f"   Side: {side}")

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


def _position_status(symbol,  qty_closed, price, reason):
    logger.info(f"\n🔒 Position Closed: {symbol}")
    logger.info(f"   Quantity: {qty_closed}")
    logger.info(f"   Price: {price}")
    logger.info(f"   Reason: {reason}")

    state["position_status"]["closed"] = True
    state["is_running"] = False
    state["current_step"] = "position_closed"
    state["Monitoring_Background"] = False

    try:
        ws_manager.stop()
    except Exception as e:
        logger.exception(f"Error stopping WS: {e}")


# ----------------------------
# MAIN POSITION MONITOR LOOP
def _monitor_position_loop(positions,run_id):
    active_pos = next((p for p in positions if int(p.get("quantity", 0)) != 0), None)
    logger.info(f"Active Position: {active_pos}")

    if not active_pos:
        logger.info("❌ No open position to monitor.")
        state["is_running"] = False
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return

    token = int(active_pos["instrument_token"])
    symbol = active_pos["tradingsymbol"]

    qty_total = abs(int(active_pos["quantity"]))
    side = "SELL" if int(active_pos["quantity"]) < 0 else "BUY"
    entry = float(active_pos["average_price"])

    # 🔒 Targets (dynamic, same math as before)
    targets = _target_for_side(entry, side)

    # Stop loss (unchanged)
    stocks = load_stocks_for_today()
    sl = None
    for st in stocks:
        if st["instrument_token"] == token:
            sl = float(st.get("high"))
            break

    logger.info("\n=== POSITION MONITOR STARTED ===")
    logger.info(f"Symbol: {symbol} | Side: {side}")
    logger.info(f"Entry: {entry} | Qty: {qty_total}")
    logger.info(f"Targets: {targets}")
    logger.info(f"Stop Loss: {sl}")
    logger.info("=" * 50)

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
    state["current_step"] = "Position Monitioring Started"
    while state.get("run_id") == run_id and state.get("is_running"):         
        tick_count += 1

        tick = state.get("live_data", {}).get(token)

        if tick:
            last_price = float(tick.get("last_price") or tick.get("last") or 0)
            now = datetime.now(TZ)
            _add_tick_for_candle(token, last_price, now)
            logger.info(f"[{now.strftime('%H:%M:%S')}] {symbol} = {last_price}")

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
                    kite =get_kite(state["username"])
                    positions = kite.positions()["net"]
                    qty_total = 0
                    for p in kite.positions()["net"]:
                        if p["tradingsymbol"] == symbol:
                            qty_total = abs(p["quantity"])
                            break
                    _handle_stoploss(symbol, token, qty_total, close_price, sl, side)
                    order_place(symbol , qty_total , transaction_type="BUY" , reason="STOPLOSS HITTED")
                    _position_status(symbol,state["position_status"]["qty_remaining"],close_price,"STOPLOSS",)
                    state["current_step"] = "STOP_LOSS_TRIGGED"
                    state["engine_status"] = "idle"
                    state["is_running"] = False
                    logger.info("STOP_LOSS_TRIGGRED")
                    return

        # ==================================================
        # 🎯 TARGET LOGIC (SINGLE TARGET ONLY)
        # ==================================================
        if last_price is not None:
            ps = state["position_status"]
            hit = (
                (side == "BUY" and last_price >= targets) or
                (side == "SELL" and last_price <= targets)
            )

            if hit:
                kite =get_kite(state["username"])
                positions = kite.positions()["net"]
                qty_to_book = 0
                for p in kite.positions()["net"]:
                    if p["tradingsymbol"] == symbol:
                        qty_to_book = abs(p["quantity"])
                        break

                _handle_target_hit("T1", symbol, token, qty_to_book, last_price)
                order_place(symbol,qty_to_book,transaction_type="BUY",reason="TARGET_HITTED")
                ps["qty_remaining"] = 0
                state["current_step"] = "TARGET_HITTED"
                state["engine_state"] = "STOPPED"
                state["is_running"] = False

                _position_status(symbol,0, last_price, "TARGET_FILLED")

                logger.info("TARGET HIT — POSITION CLOSED")
                return



        # ==================================================
        # ⏰ EOD SQUAREOFF (UNCHANGED)
        # ==================================================
       
        
        if datetime.now(TZ).time() >= dt_time.fromisoformat(state["SQUAREOFF_TIME"]):
            kite =get_kite(state["username"])
            positions = kite.positions()["net"]
            qty_total = 0
            for p in kite.positions()["net"]:
                if p["tradingsymbol"] == symbol:
                    qty_total = abs(p["quantity"])
                    break
            _position_status(symbol,state["position_status"]["qty_remaining"],last_price,"SQUAREOFF_EOD",)
            order_place(symbol , qty_total,transaction_type="BUY" , reason="AUTO SQUARE OFF")
            state["engine_status"] = "idle"
            state["current_step"] = "AUTO_SQUARE_OFF"
            logger.info("POSITION CLOSE DUE TO AUTO SQUAREOFF_TIME")
            return
        time.sleep(1)

    # Manual stop (UNCHANGED)
    logger.info("🛑 Monitor stopped manually.")
    _position_status(
        symbol,
        state["position_status"]["qty_remaining"],
        last_price,
        "MANUAL_STOP",
    )
    
    state["is_running"] = False
    state["engine_status"] = "idle"
    state["current_step"] = "MANUAL_STOP"




def order_place(symbol, qty ,transaction_type, reason ):

    kite = state.get("kite")
    if transaction_type == 'BUY':
        type = kite.TRANSACTION_TYPE_BUY
    else:
        type = kite.TRANSACTION_TYPE_SELL

    try:

        order_number = kite.place_order(
                                variety=kite.VARIETY_REGULAR,
                                exchange=kite.EXCHANGE_NSE,
                                tradingsymbol=symbol,
                                transaction_type=type,
                                quantity=qty,
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
        logger.exception("Error In Order Place")

    message = format_order_placed_message(symbol, qty, order_number , reason)

    TelegramSender.send_message(
        message,
        parse_mode="Markdown"
    )
    
                
    logger.info(f"Placing order: {symbol} | Qty: {qty} |  | order : {order_number} "   )


def format_order_placed_message(symbol, qty, order_id , reason):
    return (
        f"📤 *`{reason}`*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Symbol*      : `{symbol}`\n"
        f"🔻 *Side*        : `SELL`\n"
        f"📦 *Quantity*   : `{qty}`\n"
        f"🧾 *Order ID*   : `{order_id}`\n"
        "\n"
        "⚡ _Order sent to exchange via Algo Engine_"
    )
