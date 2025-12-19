import os
import requests
from dotenv import load_dotenv
from io import BytesIO

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


class TelegramSender:
    @staticmethod
    def _check_credentials():
        if not BOT_TOKEN or not CHANNEL_ID:
            raise ValueError("Telegram credentials not set")

    # =========================================================
    # SEND TEXT MESSAGE
    # =========================================================
    @staticmethod
    def send_message(text, parse_mode=None):
        TelegramSender._check_credentials()

        payload = {
            "chat_id": CHANNEL_ID,
            "text": text,
        }

        if parse_mode:
            payload["parse_mode"] = parse_mode

        response = requests.post(
            f"{BASE_URL}/sendMessage",
            json=payload,
            timeout=10,
        )
        return response.json()

    # =========================================================
    # SEND DOCUMENT (PDF, EXCEL, JSON, CSV, ZIP, ETC.)
    # =========================================================
    @staticmethod
    def send_document(file, filename=None, caption=None):
        TelegramSender._check_credentials()

        data = {"chat_id": CHANNEL_ID}
        files = {}

        if caption:
            data["caption"] = caption

        if isinstance(file, str):
            files["document"] = open(file, "rb")
        else:
            if isinstance(file, bytes):
                file = BytesIO(file)
            file.name = filename or "document"
            files["document"] = file

        response = requests.post(
            f"{BASE_URL}/sendDocument",
            data=data,
            files=files,
            timeout=20,
        )
        return response.json()

    # =========================================================
    # SEND IMAGE
    # =========================================================
    @staticmethod
    def send_image(image, filename=None, caption=None):
        TelegramSender._check_credentials()

        data = {"chat_id": CHANNEL_ID}
        files = {}

        if caption:
            data["caption"] = caption

        if isinstance(image, str):
            files["photo"] = open(image, "rb")
        else:
            if isinstance(image, bytes):
                image = BytesIO(image)
            image.name = filename or "image.png"
            files["photo"] = image

        response = requests.post(
            f"{BASE_URL}/sendPhoto",
            data=data,
            files=files,
            timeout=20,
        )
        return response.json()
