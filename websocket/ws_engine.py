# ws/ws_engine.py

import time
from threading import Thread, Lock
from flask_socketio import Namespace
from logger_config import setup_logger

logger = setup_logger("WEB_SOCKET_ENGINE")

class WSService(Namespace):
    """
    Universal WebSocket service.

    - Each instance is bound to a namespace (e.g. /price, /status)
    - logic_fn: function that returns the payload to send
    - interval: seconds between messages
    - socketio & app are injected so we can emit + use app_context safely
    """

    def __init__(self, namespace: str, logic_fn, interval: float, socketio, app):
        super().__init__(namespace)
        self.namespace = namespace
        self.logic_fn = logic_fn
        self.interval = interval
        self.socketio = socketio
        self.app = app

        self._running = False
        self._lock = Lock()
        self._thread: Thread | None = None

    # ------------------------------
    # Socket.IO event handlers
    # ------------------------------
    def on_connect(self):
        logger.info(f"🟢 Client connected → {self.namespace}")
        self.socketio.emit(
            "server_message",
            {"msg": f"Connected to {self.namespace}"},
            namespace=self.namespace,
        )

    def on_disconnect(self):
        logger.info(f"🔴 Client disconnected → {self.namespace}")
        self.stop_feed()

    def on_start_feed(self, data=None):
        """Client requests to start the feed loop."""
        logger.info(f"▶️ start_feed requested → {self.namespace}")
        self.start_feed()

    def on_stop_feed(self, data=None):
        """Client requests to stop the feed loop."""
        logger.info(f"⏸ stop_feed requested → {self.namespace}")
        self.stop_feed()

    # ------------------------------
    # Feed lifecycle
    # ------------------------------
    def start_feed(self):
        with self._lock:
            if self._running:
                logger.info(f"⚠️ Feed already running → {self.namespace}")
                return

            self._running = True
            self._thread = Thread(target=self._loop, daemon=True)
            self._thread.start()
            logger.info(f"🌀 Feed loop started → {self.namespace}")

    def stop_feed(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
        logger.info(f"⛔ Feed stop signalled → {self.namespace}")

    # ------------------------------
    # Internal loop
    # ------------------------------
    def _loop(self):
        with self.app.app_context():
            logger.info(f"🌀 Feed loop started → {self.namespace}")

            while self._running:  # FIXED: Changed from self.running to self._running
                try:
                    payload = self.logic_fn()

                    self.socketio.emit(
                        "feed_update",
                        payload,
                        namespace=self.namespace
                    )

                except Exception as e:
                    logger.exception(f"❌ Error in feed loop for {self.namespace}:")

                time.sleep(self.interval)

            logger.info(f"⛔ Feed loop stopped → {self.namespace}")