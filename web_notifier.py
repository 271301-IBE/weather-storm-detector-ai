
import logging
from pywebpush import webpush, WebPushException
import json
from config import Config
from models import StormAnalysis
import os

logger = logging.getLogger(__name__)

class WebNotifier:
    def __init__(self, config: Config):
        self.config = config
        self.vapid_private_key = self.config.web_notification.vapid_private_key
        self.vapid_public_key = self.config.web_notification.vapid_public_key
        self.vapid_claims = {"sub": f"mailto:{self.config.email.sender_email}"}

    def send_notification(self, subscription_info, analysis: StormAnalysis):
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps({
                    "title": f"Warning: {analysis.alert_level.value}",
                    "body": f"A storm is expected at {analysis.predicted_arrival.strftime('%H:%M')}."
                }),
                vapid_private_key=self.vapid_private_key,
                vapid_claims=self.vapid_claims
            )
            logger.info("Web push notification sent successfully.")
        except WebPushException as ex:
            logger.error(f"Web push notification failed: {ex}")

