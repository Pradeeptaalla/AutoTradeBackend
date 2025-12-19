from flask import Blueprint, jsonify, session
from account_details import order_details, position_details, holding_details

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/order-details", methods=["GET"])
def orders():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401
    return order_details()   # ✔ NO jsonify()

@dashboard_bp.route("/position-details", methods=["GET"])
def positions():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401
    return position_details()  # ✔ NO jsonify()

@dashboard_bp.route("/holding-details", methods=["GET"])
def holdings():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401
    return holding_details()   # ✔ NO jsonify()
