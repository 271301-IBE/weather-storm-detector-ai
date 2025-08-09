import logging
import os
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

    def send_message(self, text: str, chat_id: Optional[str] = None) -> bool:
        if not self.config.telegram.enabled:
            logger.info("Telegram disabled; skipping send")
            return False
        if not self.config.telegram.bot_token or not (chat_id or self.config.telegram.chat_id):
            logger.warning("Telegram not configured (token/chat_id missing)")
            return False
        target_chat = chat_id or self.config.telegram.chat_id
        try:
            logger.debug(f"Telegram sendMessage chat_id={target_chat} text_len={len(text)}")
            # Sanitize potentially unsafe characters for HTML parse_mode
            safe_text = (
                text.replace('<', '&lt;')
                    .replace('>', '&gt;')
            )
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": target_chat,
                    "text": safe_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            ok = resp.ok and (resp.json().get("ok") is True)
            self.db.store_telegram_notification(
                timestamp=datetime.now(),
                chat_id=target_chat,
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
                chat_id=target_chat,
                text=text,
                sent_successfully=False,
                error_message=str(e),
            )
            return False

    def send_photo(self, image_path: str, caption: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
        if not self.config.telegram.enabled:
            logger.info("Telegram disabled; skipping photo send")
            return False
        if not self.config.telegram.bot_token or not (chat_id or self.config.telegram.chat_id):
            logger.warning("Telegram not configured (token/chat_id missing)")
            return False
        if not image_path or not os.path.exists(image_path):
            logger.warning(f"Image not found for Telegram photo send: {image_path}")
            return False
        target_chat = chat_id or self.config.telegram.chat_id
        logger.debug(f"Telegram sendPhoto chat_id={target_chat} file={os.path.basename(image_path)} caption_len={len(caption) if caption else 0}")
        files = {"photo": open(image_path, "rb")}
        data = {"chat_id": target_chat}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        try:
            resp = requests.post(f"{self.base_url}/sendPhoto", files=files, data=data, timeout=20)
            ok = resp.ok and (resp.json().get("ok") is True)
            self.db.store_telegram_notification(
                timestamp=datetime.now(),
                chat_id=target_chat,
                text=f"[photo] {os.path.basename(image_path)}" + (f" caption: {caption}" if caption else ""),
                sent_successfully=ok,
                error_message=None if ok else resp.text,
            )
            if not ok:
                logger.error(f"Telegram photo send failed: {resp.text}")
            return ok
        except Exception as e:
            logger.error(f"Telegram photo send exception: {e}")
            self.db.store_telegram_notification(
                timestamp=datetime.now(),
                chat_id=target_chat,
                text=f"[photo] {os.path.basename(image_path)}",
                sent_successfully=False,
                error_message=str(e),
            )
            return False


