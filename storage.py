"""Database storage module for weather data."""

import sqlite3
import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from models import WeatherData, StormAnalysis, EmailNotification, WeatherCondition, WeatherForecast, PredictedWeatherData
from config import Config

logger = logging.getLogger(__name__)


class StdevFunc:
    def __init__(self):
        self.M = 0.0
        self.S = 0.0
        self.k = 0

    def step(self, value):
        if value is None:
            return
        t = value - self.M
        self.k += 1
        self.M += t / self.k
        self.S += t * (value - self.M)

    def finalize(self):
        if self.k < 2:
            return None
        return (self.S / (self.k - 1)) ** 0.5


class WeatherDatabase:
    """SQLite database for weather data storage."""
    
    def __init__(self, config: Config):
        """Initialize database connection."""
        self.db_path = config.system.database_path
        self.init_database()
    
    def init_database(self):
        """Create database tables if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Weather data table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS weather_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    temperature REAL,
                    humidity REAL,
                    pressure REAL,
                    wind_speed REAL,
                    wind_direction REAL,
                    precipitation REAL,
                    precipitation_probability REAL,
                    condition TEXT,
                    visibility REAL,
                    cloud_cover REAL,
                    uv_index REAL,
                    description TEXT,
                    raw_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Storm analysis table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS storm_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    storm_detected BOOLEAN NOT NULL,
                    alert_level TEXT,
                    predicted_arrival TEXT,
                    predicted_intensity TEXT,
                    analysis_summary TEXT,
                    recommendations TEXT,
                    data_quality_score REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Email notifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS email_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT,
                    message_type TEXT NOT NULL,
                    sent_successfully BOOLEAN NOT NULL,
                    error_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # System status table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    component TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Weather condition cache table for AI analysis triggers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS weather_condition_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT UNIQUE NOT NULL,
                    analyzed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Storm patterns table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS storm_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    triggering_event TEXT NOT NULL,
                    weather_data_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Weather forecasts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS weather_forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    forecast_data_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Enhanced forecasts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS enhanced_forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    method TEXT NOT NULL,
                    forecast_data_json TEXT NOT NULL,
                    confidence_data TEXT,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            logger.info("Database initialized successfully")
            try:
                # Create lightning summary tables/indexes if lightning monitor is used
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lightning_activity_summary (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        hour_timestamp TEXT NOT NULL,
                        total_strikes INTEGER DEFAULT 0,
                        czech_region_strikes INTEGER DEFAULT 0,
                        nearby_strikes INTEGER DEFAULT 0,
                        closest_strike_distance REAL,
                        average_distance REAL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(hour_timestamp)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_lightning_summary_hour
                    ON lightning_activity_summary(hour_timestamp)
                    """
                )
                conn.commit()
            except Exception:
                # Optional in environments without lightning ingestion
                pass
    
    @contextmanager
    def get_connection(self, read_only=False):
        """
        Get a database connection with WAL mode and appropriate locking.
        :param read_only: If True, opens the connection in read-only mode.
        """
        db_uri = f"file:{self.db_path}{'?mode=ro' if read_only else ''}"
        try:
            conn = sqlite3.connect(db_uri, uri=True, timeout=10)
            conn.row_factory = sqlite3.Row
            if not read_only:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout = 5000")  # 5 seconds
            conn.create_aggregate("STDDEV", 1, StdevFunc)
            yield conn
        except sqlite3.OperationalError as e:
            logger.error(f"Database connection error to {self.db_path}: {e}")
            raise
        finally:
            if 'conn' in locals() and conn:
                conn.close()
    
    def store_weather_data(self, weather_data: WeatherData) -> bool:
        """Store weather data in database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                data = weather_data.to_dict()
                data['raw_data'] = json.dumps(data['raw_data'])
                
                cursor.execute("""
                    INSERT INTO weather_data 
                    (timestamp, source, temperature, humidity, pressure, wind_speed, 
                     wind_direction, precipitation, precipitation_probability, condition,
                     visibility, cloud_cover, uv_index, description, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data['timestamp'], data['source'], data['temperature'],
                    data['humidity'], data['pressure'], data['wind_speed'],
                    data['wind_direction'], data['precipitation'], 
                    data['precipitation_probability'], data['condition'],
                    data['visibility'], data['cloud_cover'], data['uv_index'],
                    data['description'], data['raw_data']
                ))
                
                conn.commit()
                logger.debug(f"Stored weather data from {weather_data.source}")
                return True
                
        except Exception as e:
            logger.error(f"Error storing weather data: {e}")
            return False
    
    def store_storm_analysis(self, analysis: StormAnalysis) -> bool:
        """Store storm analysis in database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                data = analysis.to_dict()
                
                cursor.execute("""
                    INSERT INTO storm_analysis 
                    (timestamp, confidence_score, storm_detected, alert_level,
                     predicted_arrival, predicted_intensity, analysis_summary,
                     recommendations, data_quality_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data['timestamp'], data['confidence_score'], data['storm_detected'],
                    data['alert_level'], data.get('predicted_arrival'),
                    data.get('predicted_intensity'), data['analysis_summary'],
                    json.dumps(data['recommendations']), data['data_quality_score']
                ))
                
                conn.commit()
                logger.debug(f"Stored storm analysis with confidence {analysis.confidence_score}")
                return True
                
        except Exception as e:
            logger.error(f"Error storing storm analysis: {e}")
            return False
    
    def get_last_storm_analysis(self) -> Optional[StormAnalysis]:
        """Get the most recent storm analysis."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT timestamp, confidence_score, storm_detected, alert_level,
                           predicted_arrival, predicted_intensity, analysis_summary,
                           recommendations, data_quality_score
                    FROM storm_analysis 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                """)
                
                row = cursor.fetchone()
                if row:
                    from models import StormAnalysis, AlertLevel
                    
                    # Parse alert level
                    alert_level_map = {
                        'LOW': AlertLevel.LOW,
                        'MEDIUM': AlertLevel.MEDIUM,
                        'HIGH': AlertLevel.HIGH,
                        'CRITICAL': AlertLevel.CRITICAL
                    }
                    alert_level = alert_level_map.get(row[3], AlertLevel.LOW)
                    
                    # Parse predicted arrival
                    predicted_arrival = None
                    if row[4]:
                        try:
                            predicted_arrival = datetime.fromisoformat(row[4])
                        except:
                            pass
                    
                    # Parse recommendations
                    recommendations = []
                    if row[7]:
                        try:
                            recommendations = json.loads(row[7])
                        except:
                            pass
                    
                    return StormAnalysis(
                        timestamp=datetime.fromisoformat(row[0]),
                        confidence_score=float(row[1]),
                        storm_detected=bool(row[2]),
                        alert_level=alert_level,
                        predicted_arrival=predicted_arrival,
                        predicted_intensity=row[5],
                        analysis_summary=row[6] or "",
                        recommendations=recommendations,
                        data_quality_score=float(row[8]) if row[8] else 0.0
                    )
                return None
                
        except Exception as e:
            logger.error(f"Error getting last storm analysis: {e}")
            return None
    
    def store_email_notification(self, notification: EmailNotification) -> bool:
        """Store email notification record."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                data = notification.to_dict()
                
                cursor.execute("""
                    INSERT INTO email_notifications 
                    (timestamp, recipient, subject, message_type, sent_successfully, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    data['timestamp'], data['recipient'], data.get('subject'),
                    data['message_type'], data['sent_successfully'], data.get('error_message')
                ))
                
                conn.commit()
                logger.debug(f"Stored email notification: {notification.message_type}")
                return True
                
        except Exception as e:
            logger.error(f"Error storing email notification: {e}")
            return False
    
    def get_recent_weather_data(self, hours: int = 72) -> List[WeatherData]:
        """Get recent weather data from database."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # More efficient query - only essential columns, limit results
                cursor.execute("""
                    SELECT timestamp, source, temperature, humidity, pressure, wind_speed, 
                           wind_direction, precipitation, precipitation_probability, condition,
                           visibility, cloud_cover, uv_index, description
                    FROM weather_data 
                    WHERE timestamp > ? 
                    ORDER BY timestamp DESC
                    LIMIT 200
                """, (cutoff_time.isoformat(),))
                
                rows = cursor.fetchall()
                
                weather_data_list = []
                for row in rows:
                    # Direct construction without dict comprehension
                    wd = WeatherData(
                        timestamp=datetime.fromisoformat(row[0]),
                        source=row[1],
                        temperature=row[2] or 0.0,
                        humidity=row[3] or 0.0,
                        pressure=row[4] or 0.0,
                        wind_speed=row[5] or 0.0,
                        wind_direction=row[6] or 0.0,
                        precipitation=row[7] or 0.0,
                        precipitation_probability=row[8],
                        condition=WeatherCondition(row[9]) if row[9] else WeatherCondition.CLEAR,
                        visibility=row[10],
                        cloud_cover=row[11] or 0.0,
                        uv_index=row[12],
                        description=row[13] or "",
                        raw_data={}  # Skip raw_data for performance
                    )
                    weather_data_list.append(wd)
                
                return weather_data_list
                
        except Exception as e:
            logger.error(f"Error retrieving weather data: {e}")
            return []
    
    def get_last_storm_alert(self) -> Optional[datetime]:
        """Get timestamp of last storm alert email."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT timestamp FROM email_notifications 
                    WHERE message_type = 'storm_alert' AND sent_successfully = 1
                    ORDER BY timestamp DESC 
                    LIMIT 1
                """)
                
                row = cursor.fetchone()
                if row:
                    return datetime.fromisoformat(row[0])
                return None
                
        except Exception as e:
            logger.error(f"Error getting last storm alert: {e}")
            return None
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Remove old data beyond retention period and vacuum the database."""
        try:
            cutoff_time = datetime.now() - timedelta(days=days_to_keep)
            analysis_cutoff = datetime.now() - timedelta(days=90)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Clean up weather data
                cursor.execute("DELETE FROM weather_data WHERE timestamp < ?", (cutoff_time.isoformat(),))
                weather_deleted = cursor.rowcount
                
                # Clean up email notifications
                cursor.execute("DELETE FROM email_notifications WHERE timestamp < ?", (cutoff_time.isoformat(),))
                email_deleted = cursor.rowcount
                
                # Clean up storm analysis
                cursor.execute("DELETE FROM storm_analysis WHERE timestamp < ?", (analysis_cutoff.isoformat(),))
                analysis_deleted = cursor.rowcount
                
                # Clean up old forecast data
                cursor.execute("DELETE FROM enhanced_forecasts WHERE timestamp < ?", (cutoff_time.isoformat(),))
                forecast_deleted = cursor.rowcount
                
                conn.commit()
                logger.info(f"Cleaned up old data: {weather_deleted} weather, {email_deleted} emails, {analysis_deleted} analyses, {forecast_deleted} forecasts")

            # Vacuum database to reclaim space (run outside of a transaction)
            with self.get_connection() as conn:
                conn.execute("VACUUM")
                logger.info("Database vacuumed successfully.")
                
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
    
    def is_weather_condition_recently_analyzed(self, cache_key: str) -> bool:
        """Check if a weather condition has been analyzed recently."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if cache entry exists and hasn't expired
                cursor.execute("""
                    SELECT COUNT(*) FROM weather_condition_cache 
                    WHERE cache_key = ? AND expires_at > datetime('now')
                """, (cache_key,))
                
                count = cursor.fetchone()[0]
                return count > 0
                
        except Exception as e:
            logger.error(f"Error checking weather condition cache: {e}")
            return False
    
    def mark_weather_condition_analyzed(self, cache_key: str, expires_hours: int = 1):
        """Mark a weather condition as analyzed with expiration time."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now()
                expires_at = now + timedelta(hours=expires_hours)
                
                # Insert or replace cache entry
                cursor.execute("""
                    INSERT OR REPLACE INTO weather_condition_cache 
                    (cache_key, analyzed_at, expires_at)
                    VALUES (?, ?, ?)
                """, (cache_key, now.isoformat(), expires_at.isoformat()))
                
                conn.commit()
                logger.debug(f"Marked weather condition as analyzed: {cache_key} (expires in {expires_hours}h)")
                
        except Exception as e:
            logger.error(f"Error marking weather condition as analyzed: {e}")
    
    def cleanup_weather_condition_cache(self):
        """Clean up expired weather condition cache entries."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Remove expired entries
                cursor.execute("""
                    DELETE FROM weather_condition_cache 
                    WHERE expires_at < datetime('now')
                """)
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.debug(f"Cleaned up {deleted_count} expired weather condition cache entries")
                    
        except Exception as e:
            logger.error(f"Error cleaning up weather condition cache: {e}")

    def store_storm_pattern(self, event: str, weather_data: List[WeatherData]):
        """Store a sequence of weather data as a storm pattern."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                weather_data_json = json.dumps([wd.to_dict() for wd in weather_data])
                
                cursor.execute("""
                    INSERT INTO storm_patterns (recorded_at, triggering_event, weather_data_json)
                    VALUES (?, ?, ?)
                """, (datetime.now().isoformat(), event, weather_data_json))
                
                conn.commit()
                logger.info(f"Stored new storm pattern triggered by: {event}")

        except Exception as e:
            logger.error(f"Error storing storm pattern: {e}")

    def get_storm_patterns(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent storm patterns from the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT weather_data_json FROM storm_patterns
                    ORDER BY recorded_at DESC
                    LIMIT ?
                """, (limit,))
                
                rows = cursor.fetchall()
                patterns = []
                for row in rows:
                    patterns.append(json.loads(row[0]))
                
                return patterns

        except Exception as e:
            logger.error(f"Error retrieving storm patterns: {e}")
            return []

    def store_weather_forecast(self, forecast: WeatherForecast) -> bool:
        """Store a weather forecast in the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                forecast_json = json.dumps(forecast.to_dict())
                cursor.execute("""
                    INSERT INTO weather_forecasts (timestamp, forecast_data_json)
                    VALUES (?, ?)
                """, (forecast.timestamp.isoformat(), forecast_json))
                conn.commit()
                logger.info(f"Stored new weather forecast at {forecast.timestamp}")
                return True
        except Exception as e:
            logger.error(f"Error storing weather forecast: {e}")
            return False

    def get_latest_weather_forecast(self) -> Optional[WeatherForecast]:
        """Get the most recent weather forecast from the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, forecast_data_json FROM weather_forecasts
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    timestamp = datetime.fromisoformat(row[0])
                    forecast_data_json = json.loads(row[1])
                    forecast_data = []
                    for item in forecast_data_json['forecast_data']:
                        forecast_data.append(PredictedWeatherData(
                            timestamp=datetime.fromisoformat(item['timestamp']),
                            temperature=item['temperature'],
                            humidity=item['humidity'],
                            pressure=item['pressure'],
                            wind_speed=item['wind_speed'],
                            wind_direction=item['wind_direction'],
                            precipitation=item['precipitation'],
                            precipitation_probability=item['precipitation_probability'],
                            condition=WeatherCondition(item['condition']),
                            cloud_cover=item['cloud_cover'],
                            visibility=item['visibility'],
                            description=item['description']
                        ))
                    return WeatherForecast(timestamp=timestamp, forecast_data=forecast_data)
                return None
        except Exception as e:
            logger.error(f"Error retrieving latest weather forecast: {e}")
            return None
    
    def get_recent_weather_data_for_forecast(self, hours: int = 48) -> List[WeatherData]:
        """Get recent weather data for forecasting - optimized version."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
                
                # Optimized query with limit and essential columns only
                cursor.execute("""
                    SELECT timestamp, source, temperature, humidity, pressure,
                           wind_speed, wind_direction, precipitation, precipitation_probability,
                           condition, visibility, cloud_cover, description
                    FROM weather_data
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
                    LIMIT 100
                """, (cutoff_time,))
                
                weather_data = []
                for row in cursor.fetchall():
                    weather_data.append(WeatherData(
                        timestamp=datetime.fromisoformat(row[0]),
                        source=row[1],
                        temperature=row[2] or 0.0,
                        humidity=row[3] or 0.0,
                        pressure=row[4] or 0.0,
                        wind_speed=row[5] or 0.0,
                        wind_direction=row[6] or 0.0,
                        precipitation=row[7] or 0.0,
                        precipitation_probability=row[8],
                        condition=WeatherCondition(row[9]) if row[9] else WeatherCondition.CLEAR,
                        visibility=row[10],
                        cloud_cover=row[11] or 0.0,
                        uv_index=None,
                        description=row[12] or "",
                        raw_data={}  # Skip raw_data for performance
                    ))
                
                return weather_data
                
        except Exception as e:
            logger.error(f"Error retrieving recent weather data: {e}")
            return []
    
    def store_enhanced_forecast(self, forecast, method: str) -> bool:
        """Store enhanced forecast with method tracking."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
            
                forecast_dict = forecast.to_dict()
            
                cursor.execute("""
                    INSERT INTO enhanced_forecasts 
                    (timestamp, method, forecast_data_json, confidence_data, metadata)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    forecast.timestamp.isoformat(),
                    method,
                    json.dumps(forecast_dict),
                    json.dumps(forecast.method_confidences) if hasattr(forecast, 'method_confidences') else None,
                    json.dumps({
                        'primary_method': forecast.primary_method.value if hasattr(forecast, 'primary_method') else method,
                        'data_sources': forecast.data_sources if hasattr(forecast, 'data_sources') else [],
                        'ensemble_weight': forecast.ensemble_weight if hasattr(forecast, 'ensemble_weight') else None
                    })
                ))
            
                conn.commit()
                logger.debug(f"Stored enhanced forecast using method: {method}")
                return True
        except sqlite3.OperationalError as e:
            logger.error(f"SQLite operational error while storing enhanced forecast: {e}")
        except Exception as e:
            logger.error(f"Error storing enhanced forecast: {e}")
        
        return False
    
    def get_latest_forecast_by_method(self, method: str):
        """Get latest forecast by specific method."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT timestamp, forecast_data_json, confidence_data, metadata
                    FROM enhanced_forecasts
                    WHERE method = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (method,))
                
                row = cursor.fetchone()
                if row:
                    try:
                        forecast_data = json.loads(row[1])
                        confidence_data = json.loads(row[2]) if row[2] else {}
                        metadata = json.loads(row[3]) if row[3] else {}
                        
                        # Convert back to enhanced forecast object
                        try:
                            from advanced_forecast import EnhancedWeatherForecast, EnhancedPredictedWeatherData, ForecastMethod, ForecastMetadata, ConfidenceLevel
                        except ImportError as e:
                            logger.error(f"Failed to import forecast classes: {e}")
                            return None
                        
                        # Reconstruct forecast data items
                        forecast_items = []
                        for item_data in forecast_data.get('forecast_data', []):
                            if 'metadata' in item_data:
                                meta = item_data['metadata']
                                forecast_meta = ForecastMetadata(
                                    method=ForecastMethod(meta.get('method', 'local_physics')),
                                    confidence=meta.get('confidence', 0.5),
                                    confidence_level=ConfidenceLevel(meta.get('confidence_level', 'medium')),
                                    generated_at=datetime.fromisoformat(meta.get('generated_at', datetime.now().isoformat())),
                                    data_quality=meta.get('data_quality', 0.5),
                                    model_version=meta.get('model_version', 'unknown'),
                                    uncertainty_range=meta.get('uncertainty_range')
                                )
                                
                                forecast_items.append(EnhancedPredictedWeatherData(
                                    timestamp=datetime.fromisoformat(item_data['timestamp']),
                                    temperature=item_data['temperature'],
                                    humidity=item_data['humidity'],
                                    pressure=item_data['pressure'],
                                    wind_speed=item_data['wind_speed'],
                                    wind_direction=item_data['wind_direction'],
                                    precipitation=item_data['precipitation'],
                                    precipitation_probability=item_data['precipitation_probability'],
                                    condition=WeatherCondition(item_data['condition']),
                                    cloud_cover=item_data['cloud_cover'],
                                    visibility=item_data['visibility'],
                                    description=item_data['description'],
                                    metadata=forecast_meta,
                                    alternative_predictions=item_data.get('alternative_predictions')
                                ))
                        
                        return EnhancedWeatherForecast(
                            timestamp=datetime.fromisoformat(forecast_data['timestamp']),
                            forecast_data=forecast_items,
                            primary_method=ForecastMethod(metadata.get('primary_method', method)),
                            method_confidences=confidence_data,
                            data_sources=metadata.get('data_sources', []),
                            ensemble_weight=metadata.get('ensemble_weight')
                        )
                        
                    except Exception as e:
                        logger.error(f"Error reconstructing enhanced forecast: {e}")
                        return None
                
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving latest forecast by method {method}: {e}")
            return None
    
    def store_forecast_accuracy(self, method: str, prediction_time: datetime, 
                               actual_time: datetime, parameter: str, 
                               predicted_value: float, actual_value: float) -> bool:
        """Store forecast accuracy metrics for evaluation."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create accuracy table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS forecast_accuracy (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        forecast_method TEXT NOT NULL,
                        prediction_time TEXT NOT NULL,
                        actual_time TEXT NOT NULL,
                        parameter TEXT NOT NULL,
                        predicted_value REAL NOT NULL,
                        actual_value REAL NOT NULL,
                        error_abs REAL NOT NULL,
                        error_relative REAL NOT NULL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                error_abs = abs(predicted_value - actual_value)
                error_relative = error_abs / abs(actual_value) if actual_value != 0 else 1.0
                
                cursor.execute("""
                    INSERT INTO forecast_accuracy 
                    (forecast_method, prediction_time, actual_time, parameter,
                     predicted_value, actual_value, error_abs, error_relative)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    method,
                    prediction_time.isoformat(),
                    actual_time.isoformat(),
                    parameter,
                    predicted_value,
                    actual_value,
                    error_abs,
                    error_relative
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error storing forecast accuracy: {e}")
            return False