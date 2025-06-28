import pytest
from config import load_config
from data_fetcher import WeatherDataCollector
from ai_analysis import StormDetectionEngine
from models import StormAnalysis, AlertLevel
from datetime import datetime

@pytest.fixture(scope="session")
def config():
    return load_config()

@pytest.fixture(scope="session")
async def weather_data(config):
    collector = WeatherDataCollector(config)
    return await collector.collect_weather_data()

@pytest.fixture(scope="session")
async def analysis(config, weather_data):
    if not weather_data:
        return None
    engine = StormDetectionEngine(config)
    return await engine.analyze_storm_potential(weather_data)

@pytest.fixture(scope="session")
def chmi_warnings(config):
    from chmi_warnings import ChmiWarningMonitor
    monitor = ChmiWarningMonitor(config)
    return monitor.get_all_active_warnings()