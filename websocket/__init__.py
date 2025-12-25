# ws/__init__.py

from .ws_engine import WSService
from .logic_price import price_logic
from .logic_status import get_status_payload

from logger_config import setup_logger

logger = setup_logger("Web_SOCKET_INIT")

def init_ws(socketio, app):
    """
    Register all WebSocket namespaces using the WSService engine.
    """
    logger.info("🔧 Initializing WebSocket Services...")

    services = [
        ("/price", price_logic, 1),   # every 1s
        ("/status", get_status_payload, 1), # every 1s
    ]

    for namespace, logic_fn, interval in services:
        socketio.on_namespace(
            WSService(namespace, logic_fn, interval, socketio, app)
        )
        logger.info(f"   🟢 Registered WS namespace {namespace}")

    logger.info("✅ All WebSocket namespaces initialized")
