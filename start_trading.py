# start_trading.py (REST-ONLY, SAFE ENGINE VERSION)

from datetime import datetime
from state_manager import trading_state as state
from service_ws import ws_manager
import time
import uuid
from threading import Thread
from position_manager import order_place, start_position_monitor_handler
from eligible_stocks import  format_eligible_stocks_message, run_eligibility
from telegram.sender import TelegramSender
# from trading_module import start_position_monitor


def start_trading_handler():
  

    kite = state.get("kite")
    if not kite:
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "Kite session not active"}
    
    positions = kite.positions()["net"]
    active_pos = next((p for p in positions if int(p.get("quantity", 0)) != 0), None)
    if active_pos:
        state["order_placed"] = True
        state["is_running"] = True
        state["engine_status"] = "running"
        state["current_step"] = "Position Monitoring Started"
        print("⚠️ Existing positions detected, cannot start trading.")
        return start_position_monitor_handler()


    run_eligibility()  

    
    # --- 1. Block if engine already running/starting ---
    if state.get("is_running") or state.get("engine_status") in ("starting", "running"):
        print("⚠️ Trading engine already running/starting.")
        return {"success": False, "error": "Trading engine is already running."}

    
    # --- 3. Eligible stocks check ---
    eligible = state.get("eligible_stocks", [])
    if not eligible:
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "No eligible stocks found"} 
    
    message = format_eligible_stocks_message(eligible)

    TelegramSender.send_message(
        message,
        parse_mode="Markdown"
    )
     
   


    try:
        ws_manager.stop()
    except Exception as e:
        print("WS stop error (start):", e)
    time.sleep(1)

    user_id = state.get("user_id")
    enctoken = state.get("enctoken")

    # --- 6. Setup WebSocket ---
    if not ws_manager.setup("PradeepApi", enctoken, user_id):
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "Failed to setup WebSocket"}

    if not ws_manager.start():
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "Failed to start WebSocket"}

    # --- 7. Wait for connection with timeout ---
    for _ in range(10):
        if ws_manager.connected:
            print("🟢 WS Connected")
            break
        time.sleep(0.5)
    else:
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        return {"success": False, "error": "WebSocket connection failed"}

    # --- 8. Subscribe tokens ---
    tokens = [int(s["instrument_token"]) for s in eligible]
    if tokens:
        print("🔔 Subscribing tokens:", tokens)
        ws_manager.subscribe(tokens)
        time.sleep(1)

    # --- 9. Start monitoring loop in background thread ---
    run_id = uuid.uuid4().hex
    state["run_id"] = run_id
    state["is_running"] = True
    state["engine_status"] = "running"
    state["current_step"] = "monitoring_started"
    state["session_start_time"] = time.time()
    # ensure max_session_seconds set (default 4h)
    if not state.get("max_session_seconds"):
        state["max_session_seconds"] = 4 * 60 * 60
    state["remaining_seconds"] = state["max_session_seconds"]

    # IMPORTANT: reset order_placed for this new session
    state["order_placed"] = False

    Thread(target=_monitor_trades, args=(run_id,), daemon=True).start()

    return {
        "success": True,
        "message": "Trading started (DEMO). Monitoring in background...",
        "eligible_count": len(eligible),
        "session_max_seconds": state["max_session_seconds"]
    }


def stop_trading_handler():
    """Manual stop of trading session (REST-only)."""
    print("🛑 stop_trading_handler called - manual stop")

    state["is_running"] = False
    state["engine_status"] = "stopping"
    state["current_step"] = "stopped"

    try:
        ws_manager.stop()
    except Exception as e:
        print("WS stop error (manual stop):", e)

    # Reset session-specific fields but DO NOT reset order_placed here
    state["run_id"] = None
    state["session_start_time"] = None
    state["remaining_seconds"] = None

    state["engine_status"] = "idle"
    state["current_step"] = "stopped"

    return {"success": True, "message": "Trading stopped manually"}


# ============================================================
#  BACKGROUND MONITORING LOOP (NO WEBSOCKETS)
# ============================================================

def _monitor_trades(run_id: str):
    """
    run_id: unique ID for this session. If state["run_id"] changes, this thread exits.
    Enforces:
      - 4 hour max runtime
      - single-thread behavior (only current run_id is valid)
      - auto-stop after first order placed
    """
    print("\n===== MONITOR STARTED =====")

    try:
        kite = state.get("kite")
        eligible_list = state.get("eligible_stocks", []).copy()
        state["current_step"] = "monitoring_prices"

        # Safety subscribe (again, in case)
        tokens = [int(s["instrument_token"]) for s in eligible_list]
        if tokens:
            print("Subscribing tokens (monitor):", tokens)
            try:
                ws_manager.subscribe(tokens)
            except Exception as e:
                print("WS subscribe error (monitor):", e)
            time.sleep(1)

        max_seconds = state.get("max_session_seconds", 4 * 60 * 60)
        start_ts = state.get("session_start_time") or time.time()

        

        # MAIN LOOP
        while True:
            # --- 0. Check if this run_id is still current (avoid ghost threads) ---
            if state.get("run_id") != run_id:
                print("🔁 run_id changed, exiting old monitor thread")
                break

            # --- 1. Check running flag ---
            if not state.get("is_running"):
                print("ℹ️ is_running=False, exiting monitor loop")
                break

            state["monitoring_background"] = True
            # --- 2. Check for max session timeout (4 hours) ---
            now_ts = time.time()
            elapsed = now_ts - start_ts
            remaining = max_seconds - elapsed
            if remaining <= 0:
                print("⏰ Session max duration reached. Stopping monitoring.")
                state["current_step"] = "session_timeout"
                state["engine_status"] = "timeout"
                break

            # update remaining time in state
            state["remaining_seconds"] = int(remaining)

            # --- 3. If order was already placed by some other logic, stop ---
            if state.get("order_placed"):
                print("✅ order_placed flag is True – stopping monitor.")
                break

            # --- 4. Normal monitoring work ---
            print("\n---------------- LIVE FEED ----------------")

            live_data = state.get("live_data", {})

            for stock in eligible_list[:]:
                symbol = stock["symbol"]
                token = int(stock["instrument_token"])
                high = float(stock["high"])
                low = float(stock["low"])

                price_data = live_data.get(token)

                if not price_data:
                    print(f"{symbol} → No tick data yet")
                    time.sleep(0.2)
                    continue

                # Extract values
                last = price_data.get("last_price") or price_data.get("last") or 0
                ohlc = price_data.get("ohlc", {})
                open_price = ohlc.get("open", 0)
                prev_close = ohlc.get("close", 0)

                chg = 0
                if prev_close:
                    chg = round(((last - prev_close) / prev_close) * 100, 2)

                timestamp = datetime.now().strftime("%H:%M:%S")

                print(
                    f"{symbol:<10} | last={last:<8} | open={open_price:<8} | "
                    f"high={high:<8} | low={low:<8} | chg={chg:+5.2f}% | {timestamp}"
                )

                # ENTRY RULE
                try:
                    if float(last) >= float(high):
                        print(f"\n🔥 ENTRY SIGNAL DETECTED for {symbol}")

                        qty = _calculate_quantity(kite, last)

                        state["positions"] = {
                            "symbol": symbol,
                            "quantity": qty,
                            "entry_price": last,
                            "time": timestamp
                        }

                        order_place(symbol, qty )
                        
                                           



                        state["current_step"] = "order_placed"
                        state["order_placed"] = True

                        # stop engine after first demo trade
                        state["is_running"] = True
                        state["engine_status"] = "running"
                        
                        print("\n🛑 Monitoring stopped after first trade.")
                        print("===== MONITOR ENDED =====\n")
                        start_position_monitor_handler()
                        return

                except Exception as e:
                    print("Entry rule error:", e)

            time.sleep(1)

    except Exception as e:
        print("💥 Monitor crashed with error:", e)

    finally:
        # Ensure we stop WS and clean state even if exception happens
        try:
            ws_manager.stop()
        except Exception as e:
            print("WS stop error (finally):", e)

        # Only clear run-related state if this thread still owns the run_id
        if state.get("run_id") == run_id:
            state["is_running"] = False
            if not state.get("order_placed") and state.get("engine_status") not in ("timeout", "completed"):
                state["engine_status"] = "idle"
            state["current_step"] = state.get("current_step", "idle")
            state["run_id"] = None
            state["session_start_time"] = None
            state["remaining_seconds"] = None

        print("No entries triggered or session ended. Monitoring ended.")


# ============================================================
# QUANTITY CALCULATION
# ============================================================

def _calculate_quantity(kite, last_price):
    """Calculate quantity using your margin rules (DEMO)."""
    try:
        margins = kite.margins()
        net = margins["equity"]["net"]
    except Exception:
        net = 50000  

    if net <= state['max_margin']:
        capital = net - 299
    else:
        capital = state['max_margin'] - 499

    try:
        qty = round(capital * 5 / float(last_price))
    except Exception:
        qty = 1

    if qty % 2 == 0:
        qty -= 1

    return max(qty, 1)
