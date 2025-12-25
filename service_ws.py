# service_ws.py
from state_manager import trading_state
from kiteconnect import KiteTicker
from logger_config import setup_logger
import threading
import time

logger = setup_logger("Web_Socket_Manager")


class WebSocketManager:
    def __init__(self):
        self.kws = None
        self.running = False
        self.connected = False
        self._lock = threading.Lock()   # 🔒 prevents race conditions

    # ---------------------------------------------------------
    # SETUP
    # ---------------------------------------------------------
    def setup(self, api_key, enctoken, user_id):
        with self._lock:
            try:
                access_token = f"{enctoken}&user_id={user_id}"
                logger.info("WS Setup → %s", access_token)

                self.kws = KiteTicker(api_key, access_token)
                self.kws.on_ticks = self.on_ticks
                self.kws.on_connect = self.on_connect
                self.kws.on_close = self.on_close
                self.kws.on_error = self.on_error

                self.running = False
                self.connected = False
                return True
            except Exception:
                logger.exception("WS Setup Error")
                self.kws = None
                return False

    # ---------------------------------------------------------
    # START
    # ---------------------------------------------------------
    def start(self):
        with self._lock:
            if not self.kws:
                logger.error("WS Start skipped — kws is None")
                return False

            if self.running:
                logger.info("WS already running")
                return True

            try:
                logger.info("▶ Starting WebSocket connection")
                self.running = True
                self.kws.connect(threaded=True)
                return True
            except Exception:
                logger.exception("WS Start Error")
                self.running = False
                return False

    # ---------------------------------------------------------
    # SUBSCRIBE
    # ---------------------------------------------------------
    def subscribe(self, tokens):
        with self._lock:
            if not self.kws or not self.connected:
                logger.warning(
                    "⚠️ WS subscribe skipped — connected=%s kws=%s",
                    self.connected,
                    bool(self.kws),
                )
                return False

            try:
                self.kws.subscribe(tokens)
                self.kws.set_mode(self.kws.MODE_QUOTE, tokens)
                trading_state["subscribed_tokens"] = tokens
                logger.info("📡 Subscribed tokens: %s", tokens)
                return True
            except Exception:
                logger.exception("WS Subscribe Error")
                return False

    # ---------------------------------------------------------
    # STOP (SAFE)
    # ---------------------------------------------------------
    def stop(self):
        with self._lock:
            try:
                if not self.kws:
                    logger.info("WS stop skipped — kws already None")
                    return True

                if self.running:
                    logger.info("🛑 Stopping WebSocket connection...")
                    try:
                        self.kws.close()
                    except Exception:
                        logger.exception("WS close error")

                # reset state safely
                self.running = False
                self.connected = False
                self.kws = None

                trading_state["websocket_status"] = "Disconnected"
                trading_state["subscribed_tokens"] = []

                logger.info("🔴 WebSocket fully stopped")
                return True
            except Exception:
                logger.exception("WS Stop Error")
                return False

    # ---------------------------------------------------------
    # CALLBACKS
    # ---------------------------------------------------------
    def on_connect(self, ws, resp):
        logger.info("🟢 WS CONNECTED")
        self.connected = True
        trading_state["websocket_status"] = "Connected"

    def on_close(self, ws, code, reason):
        logger.info("🔴 WS CLOSED | code=%s reason=%s", code, reason)
        self.connected = False
        self.running = False
        trading_state["websocket_status"] = "Disconnected"

    def on_error(self, ws, code, reason):
        # 🔥 FIXED logging crash
        logger.info("⚠️ WS ERROR | code=%s reason=%s", code, reason)

    # ---------------------------------------------------------
    # TICKS (UNCHANGED BUSINESS LOGIC)
    # ---------------------------------------------------------
    def on_ticks(self, ws, ticks):
        """
        Zerodha tick callback.
        Deep-merge logic preserved EXACTLY as your original.
        """

        if not ticks:
            return

        for tick in ticks:
            token = tick.get("instrument_token")
            if not token:
                continue

            prev = trading_state["live_data"].get(token, {})
            merged = prev.copy()

            if tick.get("last_price") is not None:
                merged["last_price"] = tick["last_price"]

            if tick.get("last") is not None:
                merged["last"] = tick["last"]

            if "ohlc" in tick and isinstance(tick["ohlc"], dict):
                merged.setdefault("ohlc", {})
                for k, v in tick["ohlc"].items():
                    if v is not None:
                        merged["ohlc"][k] = v

            if tick.get("volume") is not None:
                merged["volume"] = tick["volume"]

            if "depth" in tick and isinstance(tick["depth"], dict):
                merged.setdefault("depth", {})
                for side in ("buy", "sell"):
                    if side in tick["depth"]:
                        merged["depth"][side] = tick["depth"][side]

            if tick.get("timestamp") is not None:
                merged["timestamp"] = tick["timestamp"]

            trading_state["live_data"][token] = merged


# ---------------------------------------------------------
# GLOBAL INSTANCE
# ---------------------------------------------------------
ws_manager = WebSocketManager()
