import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

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

    def send_message(self, text: str, chat_id: Optional[str] = None, reply_markup: Optional[Dict[str, Any]] = None, reply_to_message_id: Optional[int] = None) -> bool:
        if not self.config.telegram.enabled:
            logger.info("Telegram disabled; skipping send")
            return False
        if not self.config.telegram.bot_token or not (chat_id or self.config.telegram.chat_id):
            logger.warning("Telegram not configured (token/chat_id missing)")
            return False
        target_chat = chat_id or self.config.telegram.chat_id
        # Anti-spam: rate limit and dedup within small window
        try:
            if self.db.was_recent_telegram_duplicate(target_chat, text, within_seconds=90):
                logger.info("Skipping Telegram message (duplicate within 90s)")
                return False
        except Exception:
            pass
        try:
            logger.debug(f"Telegram sendMessage chat_id={target_chat} text_len={len(text)}")
            # Sanitize potentially unsafe characters for HTML parse_mode
            safe_text = (
                text.replace('<', '&lt;')
                    .replace('>', '&gt;')
            )
            payload: Dict[str, Any] = {
                "chat_id": target_chat,
                "text": safe_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            # Try thread anchor if no explicit reply_to
            if reply_to_message_id is None:
                try:
                    anchor = self.db.get_thread_anchor(target_chat)
                    if anchor:
                        payload["reply_to_message_id"] = anchor
                except Exception:
                    pass
            if reply_markup:
                payload["reply_markup"] = reply_markup
            if reply_to_message_id is not None:
                payload["reply_to_message_id"] = reply_to_message_id
            resp = requests.post(f"{self.base_url}/sendMessage", json=payload, timeout=10)
            ok = resp.ok and (resp.json().get("ok") is True)
            try:
                if ok and reply_to_message_id is None:
                    data = resp.json()
                    msg = data.get("result") or {}
                    mid = msg.get("message_id")
                    if mid is not None:
                        self.db.set_thread_anchor(target_chat, str(mid))
            except Exception:
                pass
            self.db.store_telegram_notification(
                timestamp=datetime.now(),
                chat_id=target_chat,
                text=text,
                sent_successfully=ok,
                error_message=None if ok else resp.text,
            )
            try:
                if ok:
                    self.db.record_telegram_message(target_chat, text)
            except Exception:
                pass
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

    def send_photo(self, image_path: str, caption: Optional[str] = None, chat_id: Optional[str] = None, reply_to_message_id: Optional[int] = None) -> bool:
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
        try:
            if caption and self.db.was_recent_telegram_duplicate(target_chat, f"[photo]{caption}", within_seconds=90):
                logger.info("Skipping Telegram photo (duplicate within 90s)")
                return False
        except Exception:
            pass
        files = {"photo": open(image_path, "rb")}
        data = {"chat_id": target_chat}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        if reply_to_message_id is not None:
            data["reply_to_message_id"] = str(reply_to_message_id)
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

    def send_document(self, file_path: str, caption: Optional[str] = None, chat_id: Optional[str] = None, reply_to_message_id: Optional[int] = None) -> bool:
        if not self.config.telegram.enabled:
            logger.info("Telegram disabled; skipping document send")
            return False
        target_chat = chat_id or self.config.telegram.chat_id
        if not self.config.telegram.bot_token or not target_chat:
            logger.warning("Telegram not configured (token/chat_id missing)")
            return False
        if not os.path.exists(file_path):
            logger.error(f"Document file not found: {file_path}")
            return False
        try:
            with open(file_path, 'rb') as f:
                files = {"document": f}
                data: Dict[str, Any] = {"chat_id": target_chat}
                if caption:
                    data["caption"] = caption
                if reply_to_message_id is not None:
                    data["reply_to_message_id"] = str(reply_to_message_id)
                resp = requests.post(f"{self.base_url}/sendDocument", files=files, data=data, timeout=30)
            ok = resp.ok and (resp.json().get("ok") is True)
            self.db.store_telegram_notification(
                timestamp=datetime.now(),
                chat_id=target_chat,
                text=f"[document] {os.path.basename(file_path)}",
                sent_successfully=ok,
                error_message=None if ok else resp.text,
            )
            if not ok:
                logger.error(f"Telegram document send failed: {resp.text}")
            return ok
        except Exception as e:
            logger.error(f"Telegram document send exception: {e}")
            self.db.store_telegram_notification(
                timestamp=datetime.now(),
                chat_id=target_chat,
                text=f"[document] {os.path.basename(file_path)}",
                sent_successfully=False,
                error_message=str(e),
            )
            return False


