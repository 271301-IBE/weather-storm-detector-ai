import sqlite3
from datetime import datetime, timedelta
import logging
import pandas as pd
from config import load_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ThunderstormPredictor:
    def __init__(self, config):
        self.config = config
        self.db_path = self.config.system.database_path

    def get_db_connection(self):
        """Get database connection with timeout and WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=MEMORY")  # Reduce SD-card writes
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA mmap_size=300000000")
        conn.execute("PRAGMA cache_size=20000")
        return conn

    def fetch_recent_weather_data(self):
        """Fetch weather data from the last 2 hours."""
        try:
            conn = self.get_db_connection()
            two_hours_ago = datetime.now() - timedelta(hours=2)
            query = f"SELECT * FROM weather_data WHERE timestamp >= '{two_hours_ago.isoformat()}' ORDER BY timestamp ASC"
            df = pd.read_sql_query(query, conn)
            conn.close()
            logger.info(f"Fetched {len(df)} records from the last 2 hours.")
            return df
        except Exception as e:
            logger.error(f"Error fetching recent weather data: {e}")
            return pd.DataFrame()

    def predict_next_storm(self):
        """
        Predicts a thunderstorm based on recent weather data trends.
        A simple heuristic model looking for sharp drops in pressure and rises in humidity.
        """
        df = self.fetch_recent_weather_data()
        if df.empty or len(df) < 4: # Need at least 4 data points (30 mins of data)
            logger.info("Not enough recent data to make a prediction.")
            return None, 0.0

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp')

        # Calculate changes (deltas)
        df['pressure_delta'] = df['pressure'].diff()
        df['humidity_delta'] = df['humidity'].diff()
        df['wind_speed_delta'] = df['wind_speed'].diff()

        # Look for storm conditions in the last 30 minutes
        last_30_min = df.last('30T')
        if last_30_min.empty:
            return None, 0.0

        # Conditions for a potential storm
        pressure_drop = last_30_min['pressure_delta'].sum() < -2 # More than 2 hPa drop
        humidity_increase = last_30_min['humidity_delta'].sum() > 10 # More than 10% increase
        wind_increase = last_30_min['wind_speed_delta'].sum() > 3 # More than 3 m/s increase

        confidence = 0.0
        if pressure_drop:
            confidence += 0.4
        if humidity_increase:
            confidence += 0.3
        if wind_increase:
            confidence += 0.3

        if confidence > 0.5:
            # Predict storm in the next 30-60 minutes
            predicted_time = datetime.now() + timedelta(minutes=45)
            logger.info(f"Potential storm detected with confidence {confidence:.2f}. Predicted time: {predicted_time}")
            return predicted_time, confidence
        else:
            logger.info("No significant storm indicators found in recent data.")
            return None, 0.0

    def store_prediction(self, predicted_time, confidence):
        """Stores the prediction in the database."""
        if predicted_time is None:
            return

        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            # Create table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS thunderstorm_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_timestamp TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Insert new prediction
            cursor.execute("""
                INSERT INTO thunderstorm_predictions (prediction_timestamp, confidence, created_at)
                VALUES (?, ?, ?)
            """, (predicted_time.isoformat(), confidence, datetime.now().isoformat()))

            conn.commit()
            conn.close()
            logger.info(f"Stored prediction: {predicted_time} with confidence {confidence:.2f}")
        except Exception as e:
            logger.error(f"Error storing prediction: {e}")

def main():
    config = load_config()
    predictor = ThunderstormPredictor(config)
    predicted_time, confidence = predictor.predict_next_storm()
    predictor.store_prediction(predicted_time, confidence)

if __name__ == "__main__":
    main()