import pyotp
from kite_trade import KiteApp, get_enctoken
from state_manager import trading_state as state
import os
from telegram import TelegramSender
import json, pandas as pd


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
        print(f"✓ Created {STOCKS_DATABASE_FILE}")

    print("\n" + "="*60)
    print("🚀 Trading Bot Backend Starting...")
    print("="*60 + "\n")
    
    # Initialize files
    initialize_files()


# =================== KITE CONNECT INITIALIZATION ====================
# 
# =================================================

def kite_connect(username):

    if state["kite"] is not None:
        print("Kite instance already exists. Reusing it.")
        return state["kite"]

    try:
        print(f"🔑 Initializing KiteConnect for user: {username}")
        trading_accounts = load_user_credentials()
        acc = trading_accounts[username]
        zerodha_user_id = acc.get("user_id")
        zerodha_password = acc.get("zerodha_password")
        totp_secret = acc.get("totp_secret")

        if not zerodha_user_id or not zerodha_password or not totp_secret:  
            print("Incomplete trading account details.")          
            return None
        totp_code = pyotp.TOTP(totp_secret).now()
        enctoken = get_enctoken(zerodha_user_id,zerodha_password,totp_code)        
        kite = KiteApp(enctoken=enctoken)
        profile = kite.profile()
        margin = kite.margins()['equity']['available']['cash']
        if margin > state.get("max_margin", 0):
            margin = margin - 500


        state["kite"] = kite
        state["enctoken"] = enctoken
        state["user_id"] = profile.get("user_id", zerodha_user_id)
        state["zerodha_logged_in"] = True
        state["current_user"] = username
        state["margin"] = margin            
        state["user_name"] = profile['user_name']
        state["logged_in"] = True
               


        return kite  

    except Exception as e:
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
        return None




    

    

      