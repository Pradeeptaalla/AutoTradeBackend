# service_ws.py
from state_manager import trading_state
from kiteconnect import KiteTicker


class WebSocketManager:
    def __init__(self):
        self.kws = None
        self.running = False
        self.connected = False

    def setup(self, api_key, enctoken, user_id):
        try:
            access_token = enctoken + "&user_id=" + user_id
            print("WS Setup →", access_token)

            self.kws = KiteTicker(api_key, access_token)
            self.kws.on_ticks = self.on_ticks
            self.kws.on_connect = self.on_connect
            self.kws.on_close = self.on_close
            self.kws.on_error = self.on_error
            return True
        except Exception as e:
            print("WS Setup Error:", e)
            return False

    def start(self):
        try:
            self.running = True
            self.kws.connect(threaded=True)
            return True
        except Exception as e:
            print("WS Start Error:", e)
            self.running = False
            return False

    def subscribe(self, tokens):
        try:
            self.kws.subscribe(tokens)
            self.kws.set_mode(self.kws.MODE_QUOTE, tokens)
            trading_state["subscribed_tokens"] = tokens
            return True
        except Exception as e:
            print("WS Subscribe Error:", e)
            return False

    # required STOP METHOD (missing earlier)
    def stop(self):
        """Stop WebSocket safely."""
        try:
            if self.kws and self.running:
                print("🛑 Stopping WebSocket connection...")
                self.running = False
                self.connected = False
                self.kws.close()

                trading_state["websocket_status"] = "Disconnected"
                trading_state["subscribed_tokens"] = []
                trading_state["live_data"] = {}

                return True
            return False
        except Exception as e:
            print("WS Stop Error:", e)
            return False

    # --- callback functions ---
    def on_connect(self, ws, resp):
        print("🟢 WS CONNECTED")
        self.connected = True
        trading_state["websocket_status"] = "Connected"

    def on_close(self, ws, code, reason):
        print("🔴 WS CLOSED", code, reason)
        self.connected = False
        self.running = False
        trading_state["websocket_status"] = "Disconnected"

    def on_error(self, ws, code, reason):
        print("⚠️ WS ERROR:", code, reason)

    def on_ticks(self, ws, ticks):
        """
        Zerodha tick callback.
        Must accept (self, ws, ticks) to stay compatible with kiteconnect.
        
        - Keeps previous tick values if new tick does NOT provide them
        - Deep merges OHLC/depth without breaking structure
        - Prevents losing values when Zerodha sends partial packets
        - Safe for eligibility checking, monitoring, and live feed
        """

        if not ticks:
            return

        for tick in ticks:
            token = tick.get("instrument_token")
            if not token:
                continue

            # Get previous tick if exists
            prev = trading_state["live_data"].get(token, {})

            # New merged tick
            merged = prev.copy()

            # -------------------------
            # LAST PRICE
            # -------------------------
            if tick.get("last_price") is not None:
                merged["last_price"] = tick["last_price"]

            if tick.get("last") is not None:
                merged["last"] = tick["last"]

            # -------------------------
            # OHLC (deep merge)
            # -------------------------
            if "ohlc" in tick and isinstance(tick["ohlc"], dict):
                merged.setdefault("ohlc", {})
                for k, v in tick["ohlc"].items():
                    if v is not None:
                        merged["ohlc"][k] = v

            # -------------------------
            # VOLUME
            # -------------------------
            if tick.get("volume") is not None:
                merged["volume"] = tick["volume"]

            # -------------------------
            # DEPTH (BUY/SELL)
            # -------------------------
            if "depth" in tick and isinstance(tick["depth"], dict):
                merged.setdefault("depth", {})
                for side in ("buy", "sell"):
                    if side in tick["depth"]:
                        merged["depth"][side] = tick["depth"][side]

            # -------------------------
            # TIMESTAMP
            # -------------------------
            if tick.get("timestamp") is not None:
                merged["timestamp"] = tick["timestamp"]

            # SAVE FINAL TICK
            trading_state["live_data"][token] = merged


# Global Instance
ws_manager = WebSocketManager()
