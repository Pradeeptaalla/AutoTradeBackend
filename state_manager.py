# state_manager.py
from datetime import time as dt_time
trading_state = {

    # ==================================================
    # 🔐 AUTH / USER SESSION
    # ==================================================
    "logged_in": False,
    "current_user": None,
    "user_id": None,
    "user_name": "Admin",    
    "zerodha_logged_in": False,
    "max_margin": 550,                 

    # ==================================================
    # 🔌 KITE / API OBJECTS
    # ==================================================
    "kite": None,          # KiteConnect instance
    "kws": None,           # Kite WebSocket instance
    "websocket_status": "Disconnected",
    "enctoken": None,

    # ==================================================
    # 📡 LIVE MARKET DATA
    # ==================================================
    "live_data": {},               # token -> tick data
    "subscribed_tokens": [],       # list of subscribed instrument tokens

    # ==================================================
    # 📊 STOCK SELECTION / ELIGIBILITY
    # ==================================================
    "stock_load_list": {},        
    "eligible_stocks": [],
    "doji_eligible_stocks": [],
    "not_eligible_stocks": [],
    "eligibility_result": None,
    "eligibility_date": None,
    "last_stock_update": None,  
    "last_eligibility_check": None,
    "stocks_count": 0,


    # ==================================================
    # 📈 POSITIONS / ORDERS / ACCOUNT
    # ==================================================
    "positions": None,
    "position_details": [],
    "position_status": {},
    "order_details": [],
    "holding_details": [],
    "margin": None,
    

    # ==================================================
    # ⚙️ TRADING ENGINE STATE
    # ==================================================
    "is_running": False,            # trading engine running or not
    "engine_status": "idle",        # idle | running | stopped | error
    "current_step": "idle",        # human-readable step
    "order_placed": False,
    "run_id": None,
    "session_start_time": None,
    "max_session_seconds": 4 * 60 * 60,  # 4 hours
    "remaining_seconds": None,
    "Monitoring_Background": False,
    "target_1_percent": 0.01,       # 1% target
    "target_2_percent": 0.02,       # 2% target
    "target_1_enabled": True,
    "target_2_enabled": False,
    "SQUAREOFF_TIME" : "15:35",
    "CANDLE_INTERVAL": 15

    
   
    
}
