# trading_module.py
from flask import Blueprint ,jsonify,request, session
from eligible_stocks import  run_eligibility
from start_trading import start_trading_handler, stop_trading_handler
# from position_manager import start_position_monitor_handler 
from state_manager import trading_state as state


trading_bp = Blueprint("trading", __name__)

# ---------------------------
# CHECK ELIGIBILITY
# ---------------------------
@trading_bp.route("/check-eligibility", methods=["POST"])
def check_eligibility():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401
    
    result = run_eligibility()
    return jsonify(result), 200

@trading_bp.route("/start-trading", methods=["POST"])
def start_trading():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401
    return jsonify(start_trading_handler())

@trading_bp.route("/stop-trading", methods=["POST"])
def stop_trading():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401
    return jsonify(stop_trading_handler())

@trading_bp.route("/trading-config-update", methods=["POST"])
def trading_settings():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    data = request.json or {}

    state["target_1_enabled"] = data.get("target_1_enabled", True)
    state["target_1_percent"] = float(data.get("target_1_percent", 0.01))
    state["target_2_enabled"] = data.get("target_2_enabled", False)
    state["target_2_percent"] = float(data.get("target_2_percent", 0.02))
    state["max_margin"] = data.get("max_margin",50000)

    return jsonify({"success": True, "success": "Successfully Updated"}), 200

@trading_bp.route("/trading-config", methods=["GET"])
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
    })







