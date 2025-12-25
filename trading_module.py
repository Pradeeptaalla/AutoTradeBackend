# trading_module.py
from flask import Blueprint ,jsonify,request, session
from eligible_stocks import  run_eligibility
from start_trading import start_trading_handler, stop_trading_handler
# from position_manager import start_position_monitor_handler 
from state_manager import trading_state as state
from logger_config import setup_logger

logger = setup_logger("Trading_Module")

trading_bp = Blueprint("trading", __name__)

# ---------------------------
# CHECK ELIGIBILITY
# ---------------------------
@trading_bp.route("/check-eligibility", methods=["POST"])
def check_eligibility():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    force = bool(data.get("force", False))

    logger.info("Eligibility check requested | force=%s", force)

    result = run_eligibility(force=force)
    return jsonify(result), 200


@trading_bp.route("/start-trading", methods=["POST"])
def start_trading():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    if state.get("is_running") or state.get("engine_status") in ("starting", "running"):
        logger.info("⚠️ Trading engine already running")
        return {"success": False, "error": "Trading engine already running"}

    return jsonify(start_trading_handler())


@trading_bp.route("/stop-trading", methods=["POST"])
def stop_trading():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not logged in"}), 401
    return jsonify(stop_trading_handler())




