import logging
import os
import platform
import time
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
import pytz

LOG_DIR = "logs"
IST = pytz.timezone("Asia/Kolkata")


class ISTFormatter(logging.Formatter):
    """Logging formatter that uses IST timezone"""

    def converter(self, timestamp):
        dt = datetime.fromtimestamp(timestamp, tz=pytz.utc)
        return dt.astimezone(IST).timetuple()


def setup_logger(name="app_logger"):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 🚨 Prevent duplicate handlers
    if logger.handlers:
        return logger

    log_file = os.path.join(LOG_DIR, "app.log")

    # 🔑 Windows-safe handler
    if platform.system() == "Windows":
        handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
            encoding="utf-8"
        )
    else:
        handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
            delay=True
        )
        handler.suffix = "%Y-%m-%d"

    formatter = ISTFormatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Console logging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
