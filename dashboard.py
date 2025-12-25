import json
from flask import Blueprint, jsonify, session
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



