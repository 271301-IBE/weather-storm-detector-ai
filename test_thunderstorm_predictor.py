import pytest
import pandas as pd
from datetime import datetime, timedelta

from config import load_config
from thunderstorm_predictor import ThunderstormPredictor
from storage import WeatherDatabase


def _make_df(now: datetime, temps, hums, press, wind, precip=None, pprob=None):
    # Construct DataFrame with monotonic timestamps every 10 minutes
    timestamps = [now - timedelta(minutes=10 * (len(temps) - 1 - i)) for i in range(len(temps))]
    data = {
        'timestamp': [t.isoformat() for t in timestamps],
        'temperature': temps,
        'humidity': hums,
        'pressure': press,
        'wind_speed': wind,
        'precipitation': precip or [0]*len(temps),
        'precipitation_probability': pprob or [0]*len(temps),
    }
    return pd.DataFrame(data)


@pytest.mark.asyncio
async def test_predictor_detects_pressure_drop_and_humidity_rise(monkeypatch):
    config = load_config()
    predictor = ThunderstormPredictor(config)

    now = datetime.now()
    df = _make_df(
        now,
        temps=[20, 20, 19.8, 19.6, 19.5, 19.5],
        hums=[70, 72, 75, 78, 82, 85],
        press=[1012, 1011.5, 1010.8, 1009.9, 1008.9, 1008.0],
        wind=[3, 3.5, 4, 4.5, 5, 6],
        precip=[0, 0, 0, 0.2, 0.5, 0.6],
        pprob=[10, 20, 30, 40, 60, 80],
    )

    def fake_get_conn(read_only=False):
        class DummyConn:
            def cursor(self):
                class C:
                    def execute(self, *args, **kwargs):
                        return self
                    def fetchone(self):
                        return (0, 0, 0, None)
                return C()
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                pass
        return DummyConn()

    # Monkeypatch DB connection used inside lightning fetch
    monkeypatch.setattr(WeatherDatabase, 'get_connection', lambda *args, **kwargs: fake_get_conn())
    # Patch predictor to return our DataFrame (avoid DB read)
    monkeypatch.setattr(ThunderstormPredictor, 'fetch_recent_weather_data', lambda self: df)

    predicted_time, confidence = predictor.predict_next_storm()
    assert predicted_time is not None
    assert confidence >= 0.55


def test_predictor_suppresses_when_signals_are_weak(monkeypatch):
    config = load_config()
    predictor = ThunderstormPredictor(config)

    now = datetime.now()
    df = _make_df(
        now,
        temps=[20]*6,
        hums=[60]*6,
        press=[1015]*6,
        wind=[2]*6,
        precip=[0]*6,
        pprob=[0]*6,
    )

    monkeypatch.setattr(ThunderstormPredictor, 'fetch_recent_weather_data', lambda self: df)
    # No lightning summary available -> ensure predictor returns no storm
    monkeypatch.setattr(ThunderstormPredictor, '_get_recent_lightning_activity', lambda self: {
        'total_strikes': 0,
        'czech_strikes': 0,
        'nearby_strikes': 0,
        'closest_distance_km': None,
    })

    predicted_time, confidence = predictor.predict_next_storm()
    assert predicted_time is None
    assert confidence == 0.0


