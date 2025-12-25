import logging
import os
import platform
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
import pytz

LOG_DIR = "logs"
IST = pytz.timezone("Asia/Kolkata")


class ISTFormatter(logging.Formatter):
    """Logging formatter that always uses IST (Asia/Kolkata)"""

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=pytz.utc)
        ist_time = dt.astimezone(IST)

        if datefmt:
            return ist_time.strftime(datefmt)

        return ist_time.strftime("%Y-%m-%d %H:%M:%S")


def setup_logger(name="app_logger"):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 🚨 Prevent duplicate handlers
    if logger.handlers:
        return logger

    log_file = os.path.join(LOG_DIR, "app.log")

    # ---------------------------
    # File Handler
    # ---------------------------
    if platform.system() == "Windows":
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
    else:
        file_handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
            delay=True,
            utc=True  # IMPORTANT: prevents OS timezone bleed
        )
        file_handler.suffix = "%Y-%m-%d"

    formatter = ISTFormatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # ---------------------------
    # Console Handler
    # ---------------------------
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.propagate = False  # prevent double logging

    return logger
