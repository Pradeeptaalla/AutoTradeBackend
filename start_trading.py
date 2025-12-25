# start_trading.py (REST-ONLY, PRODUCTION SAFE ENGINE VERSION)

from datetime import datetime

from flask import session
from state_manager import trading_state as state
from service_ws import ws_manager
import time
import uuid
from threading import Thread
from position_manager import order_place, start_position_monitor_handler
from eligible_stocks import format_eligible_stocks_message, run_eligibility
from telegram.sender import TelegramSender
from logger_config import setup_logger
from util import get_kite

logger = setup_logger("state_trading")


# ============================================================
# START TRADING HANDLER
# ============================================================

def start_trading_handler():
    logger.info("🚀 start_trading_handler called")
    state['engine_status'] = "starting"
    state['current_step'] = "Pre Checking Started"

    kite =get_kite(state["username"])
   
    if not kite:
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "Kite session not active"}

    # ------------------------------------------------------------
    # 1️⃣ Existing position check (UNCHANGED)
    # ------------------------------------------------------------
    positions = kite.positions()["net"]
    active_pos = next((p for p in positions if int(p.get("quantity", 0)) != 0), None)

    if active_pos:
        logger.info("⚠️ Existing positions detected, switching to monitoring")
        state["order_placed"] = True
        state["is_running"] = True
        state["engine_status"] = "running"
        state["current_step"] = "Position Monitoring Started"
        return start_position_monitor_handler()

    # ------------------------------------------------------------
    # 2️⃣ Run eligibility (UNCHANGED)
    # ------------------------------------------------------------
    logger.info("🧪 Running eligibility (force=True)")
    run_eligibility(force=True)

    eligible = state.get("eligible_stocks", [])
    logger.info("🧪 Eligibility completed | eligible=%s", len(eligible))

    
    # ------------------------------------------------------------
    # 4️⃣ Eligible stocks check (UNCHANGED)
    # ------------------------------------------------------------
    if not eligible:
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "No eligible stocks found"}

    

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

    # ------------------------------------------------------------
    # 7️⃣ Subscribe tokens (UNCHANGED)
    # ------------------------------------------------------------
    tokens = [int(s["instrument_token"]) for s in eligible]
    if tokens:
        ws_manager.subscribe(tokens)
        time.sleep(1)

    # ------------------------------------------------------------
    # 8️⃣ Start trading monitor thread (UNCHANGED)
    # ------------------------------------------------------------
    run_id = uuid.uuid4().hex

    state.update({
        "run_id": run_id,
        "is_running": True,          # 🔑 OWNED by trading monitor
        "engine_status": "running",
        "current_step": "Order Monitoring Started",
        "session_start_time": time.time(),
        "order_placed": False,
        "remaining_seconds": state.get("max_session_seconds", 4 * 60 * 60),
    })

    Thread(target=_monitor_trades, args=(run_id,), daemon=True).start()

    return {
        "success": True,
        "message": "Trading Monitoring started",
        "eligible_count": len(eligible),
    }


# ============================================================
# STOP TRADING HANDLER (UNCHANGED)
# ============================================================

def stop_trading_handler():
    logger.info("🛑 stop_trading_handler called")

    state["is_running"] = False
    state["engine_status"] = "stopped"
    state["current_step"] = "stopped"

    try:
        ws_manager.stop()
    except Exception:
        logger.exception("WS stop error")

    state.update({
        "run_id": None,
        "session_start_time": None,
        "remaining_seconds": None,
    })

    return {"success": True, "message": "Trading stopped"}


# ============================================================
# BACKGROUND MONITOR LOOP (FIXED – NO LOGIC CHANGE)
# ============================================================

def _monitor_trades(run_id: str):
    logger.info("===== MONITOR STARTED =====")

    try:
        kite =get_kite(state["username"])
        eligible_list = state.get("eligible_stocks", []).copy()
        eligible = state.get("eligible_stocks", [])
        TelegramSender.send_message(
                                    format_eligible_stocks_message(eligible),
                                    parse_mode="Markdown"
                                    )

        # Safety subscribe (UNCHANGED)
        tokens = [int(s["instrument_token"]) for s in eligible_list]
        if tokens:
            ws_manager.subscribe(tokens)

        while state.get("run_id") == run_id and state.get("is_running"): 
            live_data = state.get("live_data", {})

            for stock in eligible_list:
                token = int(stock["instrument_token"])
                high = float(stock["high"])
                price = (live_data.get(token) or {}).get("last_price")

                if price and price >= high:
                    logger.info("🔥 ENTRY SIGNAL for %s", stock["symbol"])
                    qty = _calculate_quantity(price)
                    order_place(stock["symbol"], qty,transaction_type="SELL" ,reason= "ORDER PLACE SUCCESSFULLY")
                    state["order_placed"] = True
                    state["current_step"] = "Order Placed"
                    start_position_monitor_handler()
                    return
                logger.info("SYMBOL:- %s | Last Price:- %s", stock["symbol"],price)
            time.sleep(1)

    except Exception:
        logger.exception(f"Monitor crashed is runinng execption block {state["is_running"] }  and {state.get("is_running")}")
        
        
# ============================================================
# QUANTITY CALCULATION (UNCHANGED)
# ============================================================

def _calculate_quantity(last_price):
    kite =get_kite(state["username"])
    net = kite.margins()["equity"]["net"]
    capital = min(net, state["max_margin"]) - 500
    qty = max(int((capital * 5) / last_price), 1)
    return qty | 1
