import types
from datetime import datetime

from models import StormAnalysis, AlertLevel
from email_notifier import EmailNotifier
from config import load_config


class DummySMTP:
    def __init__(self, should_fail_times=0):
        self.should_fail_times = should_fail_times
        self._sent = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def send_message(self, msg):
        if self.should_fail_times > 0:
            self.should_fail_times -= 1
            raise RuntimeError("simulated send failure")
        self._sent = True


def test_storm_alert_retries_and_succeeds(monkeypatch):
    config = load_config()
    notifier = EmailNotifier(config)

    # Create minimal StormAnalysis
    analysis = StormAnalysis(
        timestamp=datetime.now(),
        confidence_score=0.92,
        storm_detected=True,
        alert_level=AlertLevel.HIGH,
        predicted_arrival=None,
        predicted_intensity="moderate",
        analysis_summary="Test alert",
        recommendations=["Stay inside"],
        data_quality_score=0.9,
    )

    dummy = DummySMTP(should_fail_times=2)  # first two attempts fail, third succeeds
    monkeypatch.setattr(notifier, "_create_smtp_connection", lambda timeout=15.0: dummy)

    result = notifier.send_storm_alert(analysis, weather_data=None, pdf_path=None)
    assert result.sent_successfully is True


def test_chmi_email_retries_and_succeeds(monkeypatch):
    config = load_config()
    notifier = EmailNotifier(config)

    # Minimal warning-like object
    class W:
        def __init__(self):
            self.identifier = "id1"
            self.event = "Silné bouřky"
            self.color = "yellow"
            self.time_start_unix = int(datetime.now().timestamp())
            self.time_end_unix = None
            self.time_start_text = "dnes"
            self.time_end_text = None
            self.warning_type = "storm"
            self.in_progress = False
            self.detailed_text = "Test"
            self.instruction = "Stay safe"

    warnings = [W()]

    dummy = DummySMTP(should_fail_times=1)  # first attempt fails, second succeeds
    monkeypatch.setattr(notifier, "_create_smtp_connection", lambda timeout=15.0: dummy)

    import asyncio
    result = asyncio.run(notifier.send_chmi_warning(warnings))
    assert result.sent_successfully is True


