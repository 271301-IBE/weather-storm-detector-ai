"""Database storage module for weather data."""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from models import WeatherData, StormAnalysis, EmailNotification
from config import Config

logger = logging.getLogger(__name__)

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
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    @contextmanager
    def get_connection(self):
        """Get database connection with automatic close."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
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
    
    def get_recent_weather_data(self, hours: int = 24) -> List[WeatherData]:
        """Get recent weather data from database."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM weather_data 
                    WHERE timestamp > ? 
                    ORDER BY timestamp DESC
                """, (cutoff_time.isoformat(),))
                
                rows = cursor.fetchall()
                # Convert rows to WeatherData objects would require reconstruction
                return rows  # Return raw data for now
                
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
        """Remove old data beyond retention period."""
        try:
            cutoff_time = datetime.now() - timedelta(days=days_to_keep)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Keep storm analysis longer (90 days)
                analysis_cutoff = datetime.now() - timedelta(days=90)
                
                cursor.execute("DELETE FROM weather_data WHERE timestamp < ?", 
                             (cutoff_time.isoformat(),))
                cursor.execute("DELETE FROM storm_analysis WHERE timestamp < ?", 
                             (analysis_cutoff.isoformat(),))
                cursor.execute("DELETE FROM email_notifications WHERE timestamp < ?", 
                             (cutoff_time.isoformat(),))
                
                conn.commit()
                logger.info(f"Cleaned up data older than {days_to_keep} days")
                
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