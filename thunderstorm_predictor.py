
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
        """Get database connection."""
        return sqlite3.connect(self.db_path)

    def fetch_weather_data(self):
        """Fetch all weather data from the database."""
        try:
            conn = self.get_db_connection()
            # Fetching all data to find patterns
            query = "SELECT * FROM weather_data ORDER BY timestamp ASC"
            df = pd.read_sql_query(query, conn)
            conn.close()
            logger.info(f"Fetched {len(df)} records from the database.")
            return df
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            return pd.DataFrame()

    def identify_storm_events(self, df):
        """Identify historical storm events from data."""
        # This is a heuristic. A storm is defined by high wind and precipitation.
        # These thresholds can be tuned.
        wind_speed_threshold = self.config.prediction.wind_speed_threshold
        precipitation_threshold = self.config.prediction.precipitation_threshold
        
        df['storm'] = (df['wind_speed'] > wind_speed_threshold) & (df['precipitation'] > precipitation_threshold)
        
        # Identify the start of a storm event
        df['storm_start'] = df['storm'] & ~df['storm'].shift(1).fillna(False)
        
        return df

    def predict_next_storm(self):
        """
        Predict the next thunderstorm based on historical data patterns.
        This is a simplified model and should be improved with more advanced techniques.
        """
        df = self.fetch_weather_data()
        if df.empty:
            logger.warning("No data available to make a prediction.")
            return None, 0.0

        df = self.identify_storm_events(df)
        storm_events = df[df['storm_start']]

        if len(storm_events) < 2:
            logger.info("Not enough historical storm events to make a prediction.")
            return None, 0.0

        # Calculate the average time between storms
        storm_times = pd.to_datetime(storm_events['timestamp'])
        time_deltas = storm_times.diff().dropna()
        
        if time_deltas.empty:
            return None, 0.0

        average_delta = time_deltas.mean()
        last_storm_time = storm_times.iloc[-1]
        
        predicted_time = last_storm_time + average_delta
        
        # Simple confidence score based on the standard deviation of storm frequency
        time_deltas_days = time_deltas.dt.total_seconds() / (24 * 3600)
        confidence = 1.0 - (time_deltas_days.std() / time_deltas_days.mean())
        confidence = max(0.0, min(1.0, confidence)) # Clamp between 0 and 1

        return predicted_time, confidence

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
