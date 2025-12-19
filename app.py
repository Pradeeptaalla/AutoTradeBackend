from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
from dotenv import load_dotenv


# REST API blueprints
from authentication_module import authentication_bp
from trading_module import trading_bp
from stock_module import stock_bp
from dashboard import dashboard_bp
import os

# WebSocket initializer
from websocket import init_ws


load_dotenv()

port = int(os.environ.get("PORT", 5000))

def create_app():
    app = Flask(__name__)
    import os
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
    frontend_origins = os.environ.get("FRONTEND_ORIGINS", "").split(",")
    CORS(app,supports_credentials=True,origins=frontend_origins)
    return app


app = create_app()

socketio = SocketIO(
    app,
    cors_allowed_origins=os.environ.get("FRONTEND_ORIGINS", "").split(","),
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

# Register REST API routes
app.register_blueprint(authentication_bp, url_prefix="/api/auth")
app.register_blueprint(trading_bp, url_prefix="/api/trading")
app.register_blueprint(stock_bp, url_prefix="/api/stocks")
app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")

# Register WebSocket namespaces
init_ws(socketio, app)


if __name__ == "__main__":
    print("🚀 Starting WebSocket + API server...")
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )
