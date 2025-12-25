import pyotp
from kite_trade import KiteApp, get_enctoken
from state_manager import trading_state as state
import os
from telegram import TelegramSender
import json, pandas as pd
from logger_config import setup_logger

logger = setup_logger("Util")

USER_CREDENTIALS_FILE =  os.getenv("USER_CREDENTIALS_FILE")
STOCKS_DATABASE_FILE = os.getenv("STOCKS_DATABASE_FILE")


# ==================== USER CREDENTIALS LOADING ====================
# =================================================

def load_user_credentials():
    """Load username/password JSON"""
    

    if not USER_CREDENTIALS_FILE or not os.path.exists(USER_CREDENTIALS_FILE):
        TelegramSender.send_message(
            (
                "🚨 *AUTHENTICATION ERROR*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "*Status:* FAILED\n"
                "*Reason:* User credentials file not found\n"
                "*File:* `user_credentials.json`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _Immediate action required_"
            ),
            parse_mode="Markdown"
        )
        return {}

    with open(USER_CREDENTIALS_FILE, "r") as f:
        
        return json.load(f)


def load_stocks_database():
    """Load stocks from Excel database"""
    if os.path.exists(STOCKS_DATABASE_FILE):
        df = pd.read_excel(STOCKS_DATABASE_FILE)
        return df
    return pd.DataFrame(columns=['symbol', 'instrument_token', 'high', 'low', 'date'])

def save_stocks_database(df):
    """Save stocks to Excel database"""
    df.to_excel(STOCKS_DATABASE_FILE, index=False)

def initialize_files():
    """Initialize JSON and Excel files if they don't exist"""

    
    # Initialize stocks database
    if not os.path.exists(STOCKS_DATABASE_FILE):
        df = pd.DataFrame(columns=['symbol', 'instrument_token', 'high', 'low', 'date'])
        save_stocks_database(df)
        logger.info(f"✓ Created {STOCKS_DATABASE_FILE}")

    logger.info("\n" + "="*60)
    logger.info("🚀 Trading Bot Backend Starting...")
    logger.info("="*60 + "\n")
    
    # Initialize files
    initialize_files()


# =================== KITE CONNECT INITIALIZATION ====================
# 
# =================================================

class KiteSessionError(Exception):
    """Raised when Kite session is unavailable"""
    pass


def kite_connect(username: str) -> bool:
    """Ensure Kite session exists and is valid"""

    def _is_valid(kite):
        try:
            kite.profile()
            return True
        except Exception:
            return False
        
   

    kite = state.get("kite")
    if kite and _is_valid(kite):
        return True
    
    acc = load_user_credentials().get(username, {})
    
    
    user_id = acc.get("user_id")
    password = acc.get("zerodha_password")
    totp_secret = acc.get("totp_secret")

    if not all([user_id, password, totp_secret]):
        logger.error("Incomplete Zerodha credentials for %s", username)
        return False

    try:
        totp = pyotp.TOTP(totp_secret).now()
        enctoken = get_enctoken(user_id, password, totp)

        kite = KiteApp(enctoken=enctoken)
        profile = kite.profile()

        margin = kite.margins()["equity"]["available"]["cash"]
        if margin > state.get("max_margin", 0):
            margin -= 500

        state["kite"] = kite
        state["enctoken"] = enctoken
        state["user_id"] = profile.get("user_id", user_id)
        state["user_name"] = profile.get("user_name")
        state["current_user"] = username
        state["margin"] = margin
        state["logged_in"] = True
        state["zerodha_logged_in"] = True

        logger.info("Zerodha login successful | user=%s", username)
        return True

    except Exception:
        logger.exception("Zerodha login failed")

        TelegramSender.send_message(
                                            (
                                                "🚨 *ZERODHA LOGIN ERROR*\n"
                                                "━━━━━━━━━━━━━━━━━━\n"
                                                "*Status:* FAILED\n"
                                                "*Stage:* Session Initialization\n"
                                                "*Reason:* TOTP / authentication failure\n"
                                                "━━━━━━━━━━━━━━━━━━\n"
                                                "⚠️ _Check credentials, TOTP secret, or Zerodha availability_"
                                            ),
                                            parse_mode="Markdown"
                                        )
        return False


def get_kite(username: str):
    """Public accessor used everywhere"""
    if not kite_connect(username):
        raise KiteSessionError("Zerodha session unavailable")
    return state["kite"]
      