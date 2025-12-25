import json
from flask import Blueprint, jsonify, request, session
from state_manager import trading_state as state
from util import get_kite

dashboard_bp = Blueprint("dashboard", __name__)


EXCLUDED_KEYS = {
    "kite",
    "kws",
    "enctoken",
    "run_id",
}

def make_json_safe(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, OverflowError):
        return str(value)


@dashboard_bp.route("/account-details", methods=["GET"])
def account_details():

    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    kite =get_kite(state["username"])

    # -------- ORDERS --------
    orders = kite.orders()
    order_details = [
        {
            "order_timestamp": o.get("order_timestamp"),
            "transaction_type": o.get("transaction_type"),
            "tradingsymbol": o.get("tradingsymbol"),
            "product": o.get("product"),
            "quantity": o.get("quantity"),
            "average_price": o.get("average_price"),
            "status": o.get("status"),
        }
        for o in orders
    ]

    # -------- POSITIONS --------
    positions = kite.positions().get("net", [])
    position_details = [
        {
            "product": p.get("product"),
            "tradingsymbol": p.get("tradingsymbol"),
            "quantity": p.get("quantity"),
            "average_price": round(p.get("average_price", 0), 2),
            "last_price": round(p.get("last_price", 0), 2),
            "pnl": round(p.get("pnl", 0), 2),
        }
        for p in positions
    ]

    # -------- HOLDINGS --------
    holdings = kite.holdings()
    holding_details = [
        {
            "tradingsymbol": h.get("tradingsymbol"),
            "quantity": h.get("quantity"),
            "average_price": h.get("average_price"),
            "last_price": h.get("last_price"),
            "pnl": round(h.get("pnl", 0), 2),
            "day_change": round(h.get("day_change", 0), 2),
            "day_change_percentage": round(h.get("day_change_percentage", 0), 2),
        }
        for h in holdings
    ]

    # -------- UPDATE STATE --------
    state["order_details"] = order_details
    state["position_details"] = position_details
    state["holding_details"] = holding_details

    return jsonify({
        "success": True,
        "order_details": order_details,
        "position_details": position_details,
        "holding_details": holding_details,
    })


@dashboard_bp.route("/state", methods=["GET"])
def debug_state():
    safe_state = {
        key: make_json_safe(value)
        for key, value in state.items()
        if key not in EXCLUDED_KEYS
    }
    print(state["SQUAREOFF_TIME"])
    return jsonify(safe_state)



@dashboard_bp.route("/trading-config-update", methods=["POST"])
def trading_settings():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    data = request.json or {}

    state["target_1_enabled"] = data.get("target_1_enabled", True)
    state["target_1_percent"] = float(data.get("target_1_percent", 0.01))
    state["target_2_enabled"] = data.get("target_2_enabled", False)
    state["target_2_percent"] = float(data.get("target_2_percent", 0.02))
    state["max_margin"] = data.get("max_margin",50000)
    state["CANDLE_INTERVAL"] = data.get("CANDLE_INTERVAL",15)
    state["SQUAREOFF_TIME"] = data.get("SQUAREOFF_TIME","15:01")

    return jsonify({"success": True, "success": "Successfully Updated"}), 200

@dashboard_bp.route("/trading-config", methods=["GET"])
def get_trading_config():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    return jsonify({
        "success": True,
        "max_margin": state.get("max_margin", 0.01),
        "target_1_enabled": state.get("target_1_enabled", True),
        "target_1_percent": state.get("target_1_percent", 0.01),
        "target_2_enabled": state.get("target_2_enabled", False),
        "target_2_percent": state.get("target_2_percent", 0.02),
        "CANDLE_INTERVAL": state.get("CANDLE_INTERVAL", 15),
        "SQUAREOFF_TIME": state.get("SQUAREOFF_TIME", "14:05"),
    })


@dashboard_bp.route("/get-state-details", methods=["GET"])
def get_state_details():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    return jsonify({
        "success": True,
        "is_running": state.get("is_running"),
        "engine_status": state.get("engine_status"),
        "current_step": state.get("current_step"),
        "order_placed": state.get("order_placed"),
        "run_id": state.get("run_id"),
    })


@dashboard_bp.route("/reset-state", methods=["POST"])
def reset_state():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    data = request.json or {}
    if data.get("reset"):
        state["is_running"] = False
        state["engine_status"] = "idle"
        state["current_step"] = "idle"
        state["order_placed"] = False
        state["run_id"] = None       

    return jsonify({"success": True, "success": "All State are reset Successfully"}), 200





 