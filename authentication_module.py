# Authentication_Module.py
from flask import Blueprint, session, request, jsonify
import json
from state_manager import trading_state as state
from service_ws import ws_manager
from telegram import TelegramSender
from util import  get_kite, load_user_credentials
from logger_config import setup_logger


logger = setup_logger("authentication_module")

authentication_bp = Blueprint("authentication", __name__)


# ============================================================
# LOGIN API — Username + Password → Auto Zerodha Login
# ============================================================


@authentication_bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json(silent=True)        
        if not data:
            return jsonify(success=False, error="Request body is required"), 400

        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify(success=False,error="Username and password are required"), 400        

        # Validate credentials 
        trading_accounts = load_user_credentials()
        user = trading_accounts.get(username)
        if not user or user.get("password") != password:
           return jsonify(success=False,error="Invalid username or password"), 401

        # --------------------------------------
        # 2) Load Zerodha trading credentials
        # --------------------------------------
        
        if username not in trading_accounts:
            logger.info(f"❌ No trading account found for {username}")
            return jsonify({"success": False,"error": "Zerodha trading account not configured"}), 400
        
        session["logged_in"] = True
        session["username"] = username
        state["username"] = username
        print(state["username"])
        kite =get_kite(state["username"])
        TelegramSender.send_message((
                                    "✅ *ZERODHA LOGIN SUCCESS*\n"
                                    "━━━━━━━━━━━━━━━━━━\n"
                                    f"*User:* `{username}`\n"
                                    f"*Account Name:* {state['user_name']}\n"
                                    "*Status:* Logged in successfully\n"
                                    "━━━━━━━━━━━━━━━━━━\n"
                                    "🟢 _Session initialized and ready_"
                                ),parse_mode="Markdown")
        return jsonify({"success": True,"message": "Login successful","zerodha_profile": state["user_name"]}), 200

    except Exception as e:
        print(e)
        TelegramSender.send_message(
                            (
                                "🚨 *LOGIN STATE SAVE ERROR*\n"
                                "━━━━━━━━━━━━━━━━━━\n"
                                "*Status:* FAILED\n"
                                "*Reason:* Unable to persist user login state\n"
                                "━━━━━━━━━━━━━━━━━━\n"
                                "⚠️ _Check storage permissions or disk space_"
                            ),
                            parse_mode="Markdown"
                        )
       
        return jsonify({"success": False,"error": f"Internal server error: {str(e)}"}), 500


@authentication_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()

    try:
        # Case: user logs out but trading is still running
        if state.get("is_running"):
            TelegramSender.send_message(
                (
                    "🚪 *USER LOGOUT*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "*Status:* Logged out successfully\n"
                    "*Trading:* Still running in background\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "⚠️ _Trading engine will be stopped now_"
                ),
                parse_mode="Markdown"
            )

            if ws_manager and hasattr(ws_manager, "stop"):
                ws_manager.stop()

        # Normal logout
        TelegramSender.send_message(
            (
                "🚪 *USER LOGOUT*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "*Status:* Logged out successfully\n"
                "*Trading:* Stopped\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🟢 _Session closed safely_"
            ),
            parse_mode="Markdown"
        )

        return jsonify({"success": True,"message": "Logged out successfully"})

    except Exception as e:
        TelegramSender.send_message(
            (
                "🚨 *LOGOUT ERROR*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "*Status:* FAILED\n"
                "*Reason:* Unexpected exception during logout\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _Check server logs for details_"
            ),
            parse_mode="Markdown"
        )

        return jsonify({"success": False,"error": str(e)}), 500


# ============================================================
# CHECK SESSION API — Used by frontend to restore login
# ============================================================
@authentication_bp.route("/check-session", methods=["GET"])
def check_session():
    try:
        logged_in = session.get("logged_in", False)
        username = session.get("username")
        logger.info(f'get logged_in details {session.get("logged_in", False)} ')
        logger.info(f'get username  details {session.get("username")} ')

        if not logged_in:
            return jsonify({
                "success": True,
                "logged_in": False,
                "username": None,
                "zerodha_status": "Disconnected"
            })

        kite = state.get("kite")
        zerodha_status = "Disconnected"

       

        if kite:
            try:
                kite.profile()
                zerodha_status = "Connected"
            except Exception:
                zerodha_status = "Expired"
                state["zerodha_logged_in"] = False

        return jsonify({
            "success": True,
            "logged_in": logged_in,
            "username": username,
            "zerodha_status": zerodha_status
        })

    except Exception as e:
        print("check-session error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


@authentication_bp.route("/test-alert")
def test_alert():
    # Send text message

    logger.info("🚨 Sending test alert via Telegram... ")
    TelegramSender.send_message(
        "🚨 TEST ALERT\nSending test files",
        parse_mode="Markdown"
    )

    # Send Excel file
    TelegramSender.send_document(
        "stocks_database.xlsx",
        caption="📊 Stocks Database (Excel)"
    )

    # Send JSON file
    TelegramSender.send_document(
        "eligibility_state.json",
        caption="🧠 Eligibility State (JSON)"
    )

    TelegramSender.send_message(
                (
                    "✅ *Daily EOD Report*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "*Status:* File successfully Generated\n"
                    "━━━━━━━━━━━━━━━━━━\n"                
                ),
                parse_mode="Markdown"
            )

    

    return jsonify({"status": "sent"})



