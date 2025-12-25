import time
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from dotenv import load_dotenv
import os

# REST API blueprints
from authentication_module import authentication_bp
from trading_module import trading_bp
from stock_module import stock_bp
from dashboard import dashboard_bp
from logger_module import logger_bp

# WebSocket initializer
from util import KiteSessionError
from websocket import init_ws

# Logger
from logger_config import setup_logger

load_dotenv()

logger = setup_logger("APP")
port = int(os.environ.get("PORT", 5000))


def create_app():
    app = Flask(__name__)

    # 🔐 FIXED SECRET KEY (NO RANDOM)
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

    # 🍪 COOKIE SETTINGS FOR HTTPS (NETLIFY → EC2)
    app.config.update(
        SESSION_COOKIE_SECURE=True,      # REQUIRED for SameSite=None
        SESSION_COOKIE_SAMESITE="None",  # REQUIRED for cross-site cookies
        SESSION_PERMANENT=True
    )

    frontend_origins = os.environ.get(
        "FRONTEND_ORIGINS",
        "http://localhost:3000"
    ).split(",")

    logger.info(f"CORS allowed origins: {frontend_origins}")

    CORS(
        app,
        supports_credentials=True,
        origins=frontend_origins
    )

    return app


app = create_app()

socketio = SocketIO(
    app,
    cors_allowed_origins=os.environ.get(
        "FRONTEND_ORIGINS",
        "http://localhost:3000"
    ).split(","),
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)






@app.before_request
def log_request():
    if request.path.startswith("/logs"):
        return

    request._start_time = time.time()
    logger.info(
        "REQ %s %s | ip=%s | endpoint=%s",
        request.method,
        request.path,
        request.remote_addr,
        request.endpoint
    )


@app.after_request
def log_response(response):
    if request.path.startswith("/logs"):
        return response

    duration = round(time.time() - getattr(request, "_start_time", time.time()), 4)

    logger.info(
        "RES %s %s | status=%s | time=%ss",
        request.method,
        request.path,
        response.status_code,
        duration
    )
    return response



@app.errorhandler(KiteSessionError)
def handle_kite_error(e):
    return (jsonify({"success": False,"error": "Error in Zerodha Setup. Please check logs"}),400)

# Register REST API routes
app.register_blueprint(logger_bp, url_prefix="/logs")
app.register_blueprint(authentication_bp, url_prefix="/auth")
app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
app.register_blueprint(stock_bp, url_prefix="/stocks")
app.register_blueprint(trading_bp, url_prefix="/trading")





init_ws(socketio, app)


if __name__ == "__main__":
    logger.info("🚀 Starting WebSocket + API server...")
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )
