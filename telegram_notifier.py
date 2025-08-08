import logging
from datetime import datetime
from typing import Optional

import requests

from config import Config
from storage import WeatherDatabase

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Minimal Telegram Bot API wrapper for sending alerts and recording results."""

    def __init__(self, config: Config):
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{self.config.telegram.bot_token}"
        self.db = WeatherDatabase(config)

    def send_message(self, text: str) -> bool:
        if not self.config.telegram.enabled:
            logger.info("Telegram disabled; skipping send")
            return False
        if not self.config.telegram.bot_token or not self.config.telegram.chat_id:
            logger.warning("Telegram not configured (token/chat_id missing)")
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.config.telegram.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            ok = resp.ok and (resp.json().get("ok") is True)
            self.db.store_telegram_notification(
                timestamp=datetime.now(),
                chat_id=self.config.telegram.chat_id,
                text=text,
                sent_successfully=ok,
                error_message=None if ok else resp.text,
            )
            if not ok:
                logger.error(f"Telegram send failed: {resp.text}")
            return ok
        except Exception as e:
            logger.error(f"Telegram send exception: {e}")
            self.db.store_telegram_notification(
                timestamp=datetime.now(),
                chat_id=self.config.telegram.chat_id,
                text=text,
                sent_successfully=False,
                error_message=str(e),
            )
            return False


