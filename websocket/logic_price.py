from state_manager import trading_state as state
from datetime import datetime
from logger_config import setup_logger

logger = setup_logger("WEB_SOCKET_LOGIC_PRICE")
# --------------------------------------------------
# SAFE FLOAT CONVERTER (VERY IMPORTANT)
# --------------------------------------------------
def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------
# MAIN PRICE LOGIC
# --------------------------------------------------
def price_logic():

    logger.info("Running price logic...")
    kite = state.get("kite")
    live = state.get("live_data", {})
    eligible = state.get("eligible_stocks", [])
    running = state.get("is_running")

    # # Capital & risk
    # capital = safe_float(state.get("capital", 0))   
    # risk = safe_float(state.get("risk", 0))         

    rows = []

    # --------------------------------------------------
        # FETCH POSITIONS
    # --------------------------------------------------
    positions = state.get("position_details")

    if state["position_details"] is None:
        
        try:
            logger.info("Fetching positions for price logic...")
            positions = kite.positions().get("net", [])
            state["position_details"] = positions
        except Exception:
            positions = []

        
    active_pos = next(
            (p for p in positions if int(p.get("quantity", 0)) != 0),
            None
        )

    # ==================================================
    # ✅ CASE 1: ACTIVE SELL POSITION
    # ==================================================
    logger.info(active_pos)
    
    if active_pos:
        symbol = active_pos.get("tradingsymbol")
        qty = int(active_pos.get("quantity", 0))  # negative for SELL
        avg_price = safe_float(active_pos.get("average_price"))
        last_price = safe_float(active_pos.get("last_price"))
        

        # SELL targets → percentage fall required
        target_1_price = avg_price * 0.99   # -1%
        target_2_price = avg_price * 0.98   # -2%

        target_1_percent = round(((last_price - target_1_price) / last_price) * 100, 2)
        target_2_percent = round(((last_price - target_2_price) / last_price) * 100, 2)

        rows.append({
            "symbol": symbol,
            "quantity": qty,
            "average_price": round(avg_price, 2),
            "last_price": round(last_price, 2),
            "pnl": round((avg_price - last_price)* abs(qty),2),
            "pnl_percent": round(((avg_price - last_price) / avg_price) * 100, 2),
            "target_1_percent": target_1_percent,
            "target_2_percent": target_2_percent,
            "time": datetime.now().strftime("%H:%M:%S"),
        })

        return {
            "feed": rows,
            "is_running": running,
            "current_step": state.get("current_step"),
            "engine_status": state.get("engine_status"),
        }

    # ==================================================
    # ✅ CASE 2: NO ACTIVE POSITION → ELIGIBLE STOCK FEED
    # ==================================================
    for stock in eligible:
        try:
            token = int(stock.get("instrument_token"))
            symbol = stock.get("symbol")

            high = safe_float(stock.get("high"))
            low = safe_float(stock.get("low"))

            tick = live.get(token)
            if not tick:
                continue

            last = safe_float(tick.get("last_price") or tick.get("last"))
            ohlc = tick.get("ohlc", {})
            open_price = safe_float(ohlc.get("open"))
            prev_close = safe_float(ohlc.get("close"))

            # Skip invalid market data
            if last <= 0 or high <= 0:
                continue

            # % Change from previous close
            chg = round(((last - prev_close) / prev_close) * 100, 2) if prev_close else 0

            # SELL trigger logic (from HIGH)
            to_trigger_points = round(high - last, 2)
            to_trigger_percent = round((to_trigger_points / high) * 100, 2)

            # Quantity calculation
            margin = state.get("margin", 0)
            quantity = int(margin / (last/5))           
           

            rows.append({
                "symbol": symbol,
                "last": round(last, 2),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "change": chg,
                "quantity": quantity,
                "to_trigger_points": to_trigger_points,
                "to_trigger_percent": to_trigger_percent,
                "time": datetime.now().strftime("%H:%M:%S"),
            })

        except Exception as e:
            logger.exception(f"❌ Error in feed loop for /price:")
            continue

    return {
        "feed": rows,
        "is_running": running,
        "current_step": state.get("current_step"),
        "engine_status": state.get("engine_status"),
    }


