import json, os, time
from flask import jsonify, session
from state_manager import trading_state as state

# ---------------------------
# 1️⃣ ORDER DETAILS
# ---------------------------
def order_details():
    

    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    kite = state.get("kite")
    if not kite:
        return jsonify({"success": False, "error": "Missing kite session"}), 400

    # FIXED ✔
    orders = kite.orders()

    

    order_list = []
    for order in orders:
        order_list.append({
            "order_timestamp": order.get('order_timestamp'),
            "transaction_type": order.get('transaction_type'),
            "tradingsymbol": order.get('tradingsymbol'),
            "product": order.get('product'),
            "quantity": order.get('quantity'),
            "average_price": order.get('average_price'),
            "status": order.get('status'),
        })

    state["order_details"] = order_list     
    return jsonify({"success": True, "order_details": order_list})


# ---------------------------
# 2️⃣ POSITION DETAILS
# ---------------------------
def position_details():

    

    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    kite = state.get("kite")
    if not kite:
        return jsonify({"success": False, "error": "Missing kite session"}), 400

    # FIXED ✔
    positions = kite.positions()

    pos_list = []
    for p in positions.get('net', []):
        pos_list.append({
            "product": p.get('product'),
            "tradingsymbol": p.get('tradingsymbol'),
            "quantity": p.get('quantity'),
            "average_price": round(p.get('average_price'),2),
            "last_price": round(p.get('last_price'),2),
            "pnl": round(p.get('pnl'),2),
        })

    state["position_details"] = pos_list    
    return jsonify({"success": True, "position_details": pos_list})


# ---------------------------
# 3️⃣ HOLDINGS DETAILS
# ---------------------------
def holding_details():
    

    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    kite = state.get("kite")
    if not kite:
        return jsonify({"success": False, "error": "Missing kite session"}), 400

    holdings = kite.holdings()

    list_holdings = []
    for h in holdings:
        list_holdings.append({
            "tradingsymbol": h.get('tradingsymbol'),
            "quantity": h.get('quantity'),
            "average_price": h.get('average_price'),
            "last_price": h.get('last_price'),
            "pnl": round(h.get('pnl'),2),
            "day_change": round(h.get('day_change'),2),
            "day_change_percentage": round(h.get('day_change_percentage'),2),
        })

    state["holding_details"] = list_holdings
    return jsonify({"success": True, "holding_details": list_holdings})
