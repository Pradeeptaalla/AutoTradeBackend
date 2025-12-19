# logic_status.py

from state_manager import trading_state as state

def get_status_payload():
    eligible = state.get("eligible_stocks", [])
    return {
        "logged_in": state.get("logged_in", False),
        "user_name": state.get("user_name"),
        


        "is_running": state.get("is_running"),
        "engine_status": state.get("engine_status", "idle"),
        "current_step": state.get("current_step", "idle"),
        "order_placed": state.get("order_placed"),
        "positions": state.get("positions"),
        "run_id": state.get("run_id"),
        "eligible_stocks_count": len(eligible),
        "remaining_seconds": state.get("remaining_seconds", None),
    }
