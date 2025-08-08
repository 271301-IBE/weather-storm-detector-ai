import sqlite3
from datetime import datetime, timedelta
import logging
from typing import Dict, Any, Tuple
import math
import pandas as pd
from config import load_config
from storage import WeatherDatabase
from chmi_warnings import ChmiWarningMonitor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ThunderstormPredictor:
    def __init__(self, config):
        self.config = config
        self.db_path = self.config.system.database_path

    def fetch_recent_weather_data(self) -> pd.DataFrame:
        """Fetch essential weather columns from the last 2 hours (ordered)."""
        try:
            with WeatherDatabase(self.config).get_connection(read_only=True) as conn:
                two_hours_ago = (datetime.now() - timedelta(hours=2)).isoformat()
                query = (
                    "SELECT timestamp, temperature, humidity, pressure, wind_speed, precipitation, "
                    "precipitation_probability, description FROM weather_data "
                    "WHERE timestamp >= ? ORDER BY timestamp ASC"
                )
                df = pd.read_sql_query(query, conn, params=(two_hours_ago,))
                logger.info(f"Fetched {len(df)} records from the last 2 hours.")
                return df
        except Exception as e:
            logger.error(f"Error fetching recent weather data: {e}")
            return pd.DataFrame()

    def _get_recent_lightning_activity(self) -> Dict[str, Any]:
        """Get last-hour lightning activity using summary table (fast) with fallback."""
        try:
            with WeatherDatabase(self.config).get_connection(read_only=True) as conn:
                cursor = conn.cursor()
                one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
                try:
                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(total_strikes),0),
                               COALESCE(SUM(czech_region_strikes),0),
                               COALESCE(SUM(nearby_strikes),0),
                               MIN(closest_strike_distance)
                        FROM lightning_activity_summary
                        WHERE hour_timestamp > ?
                        """,
                        (one_hour_ago,),
                    )
                    row = cursor.fetchone()
                except Exception:
                    cursor.execute(
                        """
                        SELECT COUNT(*) as total_strikes,
                               COUNT(CASE WHEN is_in_czech_region = 1 THEN 1 END) as czech_strikes,
                               COUNT(CASE WHEN distance_from_brno <= 50 THEN 1 END) as nearby_strikes,
                               MIN(distance_from_brno) as closest_distance
                        FROM lightning_strikes 
                        WHERE timestamp > ?
                        """,
                        (one_hour_ago,),
                    )
                    row = cursor.fetchone()
                return {
                    'total_strikes': row[0] or 0,
                    'czech_strikes': row[1] or 0,
                    'nearby_strikes': row[2] or 0,
                    'closest_distance_km': row[3],
                }
        except Exception as e:
            logger.warning(f"Lightning activity fetch failed: {e}")
            return {'total_strikes': 0, 'czech_strikes': 0, 'nearby_strikes': 0, 'closest_distance_km': None}

    @staticmethod
    def _calculate_dew_point_celsius(temperature_c: float, relative_humidity_percent: float) -> float:
        """Approximate dew point using Magnus formula."""
        try:
            rh = max(1e-6, min(100.0, float(relative_humidity_percent)))
            temp = float(temperature_c)
            a = 17.62
            b = 243.12
            gamma = (a * temp) / (b + temp) + math.log(rh / 100.0)
            dew_point = (b * gamma) / (a - gamma)
            return float(dew_point)
        except Exception:
            return temperature_c  # fallback: no spread

    @staticmethod
    def _slope_per_hour(series: pd.Series) -> float:
        """Compute simple slope per hour using first/last values over time span of the series index."""
        try:
            if series.empty:
                return 0.0
            t0 = series.index[0]
            t1 = series.index[-1]
            hours = max(1e-6, (t1 - t0).total_seconds() / 3600.0)
            return float((series.iloc[-1] - series.iloc[0]) / hours)
        except Exception:
            return 0.0

    def predict_next_storm(self) -> Tuple[datetime | None, float]:
        """
        Predict a thunderstorm window using multi-signal heuristics:
        - Pressure drop slope, humidity rise, wind increase
        - Dew point spread, precipitation signal
        - Lightning activity in last hour (dominant factor)
        - ČHMÚ storm warnings (weighted by severity)
        Returns (predicted_time, confidence in 0..1).
        """
        df = self.fetch_recent_weather_data()
        if df.empty or len(df) < 4:
            logger.info("Not enough recent data to make a prediction.")
            return None, 0.0

        # Prep index, drop NaNs conservatively
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp').sort_index()
        # Work only with numeric columns for resampling
        numeric_cols = ['temperature', 'humidity', 'pressure', 'wind_speed', 'precipitation', 'precipitation_probability']
        df = df[numeric_cols].copy()
        df = df.ffill().bfill()

        # Resample to 10-minute cadence for smoother slope estimation (numeric only)
        df_10 = df.resample('10T').mean().ffill()

        # Last 60 and 30 minutes windows
        last_60 = df_10.last('60T')
        last_30 = df_10.last('30T')
        if last_30.empty or last_60.empty or len(last_30) < 2 or len(last_60) < 2:
            return None, 0.0

        # Compute slopes and deltas
        pressure_slope = self._slope_per_hour(last_60['pressure'])  # hPa/hour
        humidity_slope = self._slope_per_hour(last_60['humidity'])  # %/hour
        wind_slope = self._slope_per_hour(last_60['wind_speed'])    # m/s per hour

        pressure_delta_30 = float(last_30['pressure'].iloc[-1] - last_30['pressure'].iloc[0])
        humidity_delta_30 = float(last_30['humidity'].iloc[-1] - last_30['humidity'].iloc[0])
        wind_delta_30 = float(last_30['wind_speed'].iloc[-1] - last_30['wind_speed'].iloc[0])

        # Dew point spread
        latest_temp = float(df_10['temperature'].iloc[-1])
        latest_rh = float(df_10['humidity'].iloc[-1])
        dew_point = self._calculate_dew_point_celsius(latest_temp, latest_rh)
        dewpoint_spread = latest_temp - dew_point

        # Precipitation signals (recent intensity and probability)
        recent_precip = float(last_30['precipitation'].mean()) if 'precipitation' in last_30 else 0.0
        precip_prob = float(df_10['precipitation_probability'].iloc[-1] or 0.0)

        # External signals
        lightning = self._get_recent_lightning_activity()
        chmi_monitor = ChmiWarningMonitor(self.config)
        warnings = []
        try:
            warnings = chmi_monitor.get_storm_warnings()
        except Exception as e:
            logger.debug(f"ČHMÚ warnings unavailable: {e}")

        # Weighted confidence components
        confidence = 0.0
        reasons = []

        if pressure_slope <= -1.0 or pressure_delta_30 <= -2.0:
            confidence += 0.22
            reasons.append(f"pressure_drop({pressure_slope:.2f} hPa/h)")

        if humidity_slope >= 10.0 or humidity_delta_30 >= 8.0:
            confidence += 0.18
            reasons.append(f"humidity_rise(+{humidity_delta_30:.1f}%)")

        if wind_slope >= 3.0 or wind_delta_30 >= 3.0 or float(df_10['wind_speed'].iloc[-1]) >= 8.0:
            confidence += 0.15
            reasons.append("wind_increase")

        if dewpoint_spread <= 2.0:
            confidence += 0.10
            reasons.append(f"dewpoint_spread({dewpoint_spread:.1f}°C)")

        if recent_precip >= 0.5 or precip_prob >= 80.0:
            confidence += 0.12
            reasons.append("precip_signal")

        # Lightning increases confidence heavily
        if lightning.get('nearby_strikes', 0) > 0:
            confidence += 0.35
            reasons.append("nearby_lightning")
        elif lightning.get('czech_strikes', 0) > 0:
            confidence += 0.20
            reasons.append("regional_lightning")

        # ČHMÚ warnings weight by severity
        if warnings:
            colors = {getattr(w, 'color', '').lower() for w in warnings}
            if 'red' in colors:
                confidence += 0.35
                reasons.append("chmi_red")
            elif 'orange' in colors:
                confidence += 0.25
                reasons.append("chmi_orange")
            elif 'yellow' in colors:
                confidence += 0.12
                reasons.append("chmi_yellow")

        # Cap confidence between 0 and 1
        confidence = max(0.0, min(1.0, confidence))

        if confidence >= 0.55:
            # Tighter ETA if lightning is close, otherwise wider window
            if lightning.get('nearby_strikes', 0) > 0:
                eta_minutes = 20 if (lightning.get('closest_distance_km') or 999) <= 20 else 35
            else:
                eta_minutes = 45 if confidence < 0.75 else 30
            predicted_time = datetime.now() + timedelta(minutes=eta_minutes)
            logger.info(
                f"Potential storm detected (conf={confidence:.2f}) ETA {eta_minutes}m; reasons: {', '.join(reasons)}"
            )
            return predicted_time, float(confidence)

        logger.info("No significant storm indicators found in recent data.")
        return None, 0.0

    def store_prediction(self, predicted_time, confidence):
        """Store the prediction in the database with simple deduplication."""
        if predicted_time is None:
            return

        try:
            with WeatherDatabase(self.config).get_connection() as conn:
                cursor = conn.cursor()

                # Create table if it doesn't exist
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS thunderstorm_predictions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        prediction_timestamp TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )

                # Skip if we already stored a similar prediction in last 30 minutes unless confidence improved
                thirty_min_ago = (datetime.now() - timedelta(minutes=30)).isoformat()
                cursor.execute(
                    """
                    SELECT prediction_timestamp, confidence FROM thunderstorm_predictions
                    WHERE created_at > ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (thirty_min_ago,),
                )
                row = cursor.fetchone()
                if row:
                    last_ts, last_conf = row
                    try:
                        # If predicted time is within 20 minutes and confidence not significantly better, skip
                        prev_eta = datetime.fromisoformat(last_ts)
                        if abs((prev_eta - predicted_time).total_seconds()) < 20 * 60 and confidence <= (last_conf + 0.05):
                            logger.info("Skipping prediction insert (recent similar prediction exists)")
                            return
                    except Exception:
                        pass

                # Insert new prediction
                cursor.execute(
                    """
                    INSERT INTO thunderstorm_predictions (prediction_timestamp, confidence, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (predicted_time.isoformat(), float(confidence), datetime.now().isoformat()),
                )

                conn.commit()
                logger.info(
                    f"Stored prediction: {predicted_time} with confidence {confidence:.2f}"
                )
        except Exception as e:
            logger.error(f"Error storing prediction: {e}")

def main():
    config = load_config()
    predictor = ThunderstormPredictor(config)
    predicted_time, confidence = predictor.predict_next_storm()
    predictor.store_prediction(predicted_time, confidence)

if __name__ == "__main__":
    main()