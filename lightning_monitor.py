#!/usr/bin/env python3
"""
Lightning Strike Monitor for Weather Storm Detection System
Integrates with Blitzortung.org for real-time lightning data focused on Czech Republic/Brno area
"""

import asyncio
import websockets
import json
import re
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass

from config import Config
from storage import WeatherDatabase

# Enhanced logging for integration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class LightningStrike:
    """Lightning strike data model."""
    timestamp: datetime
    timestamp_ns: int  # Original nanosecond timestamp
    latitude: float
    longitude: float
    distance_from_brno: float  # Distance in kilometers
    is_in_czech_region: bool  # Within Czech Republic or close vicinity
    raw_data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'timestamp_ns': self.timestamp_ns,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'distance_from_brno': self.distance_from_brno,
            'is_in_czech_region': self.is_in_czech_region,
            'raw_data': json.dumps(self.raw_data)
        }

class LightningMonitor:
    """Enhanced Lightning Monitor with database integration and Czech Republic focus."""
    
    def __init__(self, config: Config, database: WeatherDatabase, 
                 on_lightning_callback: Optional[Callable[[LightningStrike], None]] = None):
        self.config = config
        self.database = database
        self.on_lightning_callback = on_lightning_callback
        
        # Blitzortung.org WebSocket configuration
        self.ws_url = "wss://ws1.blitzortung.org/"
        self.subscription_message = json.dumps({"a": 111})
        
        # Czech Republic focus coordinates (Brno)
        self.brno_lat = config.weather.latitude
        self.brno_lon = config.weather.longitude
        
        # Regional thresholds
        self.czech_region_radius_km = 150  # Consider strikes within 150km of Brno as Czech region
        self.alert_radius_km = 50  # Alert when lightning is within 50km of Brno
        
        # Statistics
        self.total_strikes = 0
        self.czech_strikes = 0
        self.nearby_strikes = 0
        
        # Initialize database tables
        self._init_lightning_tables()
        
        # Connection management
        self.is_running = False
        self.reconnect_delay = 5  # seconds

    def _init_lightning_tables(self):
        """Initialize lightning-specific database tables."""
        try:
            with self.database.get_connection() as conn:
                cursor = conn.cursor()
                
                # Lightning strikes table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS lightning_strikes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        timestamp_ns INTEGER NOT NULL,
                        latitude REAL NOT NULL,
                        longitude REAL NOT NULL,
                        distance_from_brno REAL NOT NULL,
                        is_in_czech_region BOOLEAN NOT NULL,
                        raw_data TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Lightning activity summary table (for quick queries)
                cursor.execute("""
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
                """)
                
                # Index for performance
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_lightning_timestamp 
                    ON lightning_strikes(timestamp)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_lightning_czech_region 
                    ON lightning_strikes(is_in_czech_region, timestamp)
                """)
                
                conn.commit()
                logger.info("Lightning database tables initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing lightning database tables: {e}")

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula."""
        R = 6371  # Earth's radius in kilometers
        
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c

    def is_in_czech_vicinity(self, latitude: float, longitude: float) -> bool:
        """Check if coordinates are in Czech Republic vicinity."""
        # Czech Republic approximate bounds with buffer
        czech_bounds = {
            'min_lat': 48.5,    # Southern border
            'max_lat': 51.1,    # Northern border  
            'min_lon': 12.0,    # Western border
            'max_lon': 18.9     # Eastern border
        }
        
        return (czech_bounds['min_lat'] <= latitude <= czech_bounds['max_lat'] and
                czech_bounds['min_lon'] <= longitude <= czech_bounds['max_lon'])

    def lzw_decompress(self, compressed_data: bytes) -> str:
        """LZW decompression algorithm"""
        try:
            if isinstance(compressed_data, str):
                codes = [ord(c) for c in compressed_data]
            else:
                codes = list(compressed_data)
            
            if not codes:
                return ""
            
            dict_size = 256
            dictionary = {i: chr(i) for i in range(dict_size)}
            
            result = []
            prev_code = codes[0]
            result.append(dictionary[prev_code])
            
            for i in range(1, len(codes)):
                code = codes[i]
                
                if code < len(dictionary):
                    entry = dictionary[code]
                elif code == dict_size:
                    entry = dictionary[prev_code] + dictionary[prev_code][0]
                else:
                    break
                
                result.append(entry)
                
                if dict_size < 4096:
                    dictionary[dict_size] = dictionary[prev_code] + entry[0]
                    dict_size += 1
                
                prev_code = code
            
            return ''.join(result)
            
        except Exception:
            return ""

    def extract_lightning_data(self, data: str) -> Optional[LightningStrike]:
        """Extract lightning strike data from Blitzortung message and create LightningStrike object."""
        try:
            # Try LZW decompression if data looks compressed
            if any(ord(c) > 127 for c in data[:100]):
                data_bytes = data.encode('latin1', errors='ignore')
                decompressed = self.lzw_decompress(data_bytes)
                if decompressed and ('{' in decompressed or '"' in decompressed):
                    data = decompressed
            
            # Extract timestamp
            time_match = re.search(r'"time"\s*:\s*(\d+[^\d,\s]*\d*)', data)
            if not time_match:
                return None
            
            timestamp_str = re.sub(r'[^\d]', '', time_match.group(1))
            if len(timestamp_str) < 10:
                return None
            
            timestamp_ns = int(timestamp_str)
            
            # Find lat and lon positions
            lat_pos = data.find('lat')
            lon_pos = data.find('lon')
            
            if lat_pos == -1 or lon_pos == -1:
                return None
            
            # Extract latitude
            lat_text = data[lat_pos:]
            lat_match = re.search(r'(\d+\.\d+)', lat_text)
            if not lat_match:
                return None
            latitude = float(lat_match.group(1))
            
            # Extract longitude
            lon_text = data[lon_pos:]
            lon_match = re.search(r'(-?\d+\.\d+)', lon_text)
            if not lon_match:
                return None
            longitude = float(lon_match.group(1))
            
            # Validate coordinates
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return None
            
            # Use system time instead of web timestamp due to unreliable web timestamps
            # Keep original timestamp for debugging but use current system time for all operations
            dt_object = datetime.now()
            
            # Validate that we have basic timestamp data (even if we don't use it)
            original_timestamp = None
            current_time = datetime.now()
            
            for divisor in [1000000000, 1000000, 1000]:  # ns, μs, ms
                try:
                    original_timestamp = datetime.fromtimestamp(timestamp_ns / divisor)
                    # Check if timestamp is reasonable (just for validation, not for use)
                    if (2020 <= original_timestamp.year <= current_time.year + 1):
                        break
                    else:
                        original_timestamp = None
                except (ValueError, OSError):
                    continue
            
            # Always use system time - don't reject strikes based on bad web timestamps
            # The strike detection itself is valid even if timestamp is wrong
            if original_timestamp:
                time_diff = abs((dt_object - original_timestamp).total_seconds())
                if time_diff > 300:  # More than 5 minutes difference
                    logger.debug(f"Using system time due to unreliable web timestamp. Web: {original_timestamp}, System: {dt_object}")
            else:
                logger.debug(f"Using system time due to invalid web timestamp data")
            
            # Calculate distance from Brno
            distance_from_brno = self.calculate_distance(
                self.brno_lat, self.brno_lon, latitude, longitude
            )
            
            # Check if in Czech Republic vicinity  
            is_in_czech_region = (
                self.is_in_czech_vicinity(latitude, longitude) or 
                distance_from_brno <= self.czech_region_radius_km
            )
            
            # Create lightning strike object
            lightning_strike = LightningStrike(
                timestamp=dt_object,  # System time (current time)
                timestamp_ns=timestamp_ns,  # Original timestamp data for reference
                latitude=latitude,
                longitude=longitude,
                distance_from_brno=distance_from_brno,
                is_in_czech_region=is_in_czech_region,
                raw_data={
                    'original_data': data[:200],  # Store first 200 chars for debugging
                    'original_timestamp': original_timestamp.isoformat() if original_timestamp else None,
                    'system_time_used': True  # Flag to indicate we used system time
                }
            )
            
            return lightning_strike
            
        except Exception as e:
            logger.debug(f"Error extracting lightning data: {e}")
            return None

    def store_lightning_strike(self, strike: LightningStrike) -> bool:
        """Store lightning strike in database with retry logic."""
        max_retries = 3
        base_delay = 0.1  # Start with 100ms delay
        
        for attempt in range(max_retries):
            try:
                # Use a separate connection with timeout
                import sqlite3
                conn = sqlite3.connect(self.database.db_path, timeout=5.0)
                conn.execute("PRAGMA journal_mode=WAL")  # Use WAL mode for better concurrency
                cursor = conn.cursor()
                
                data = strike.to_dict()
                
                cursor.execute("""
                    INSERT INTO lightning_strikes 
                    (timestamp, timestamp_ns, latitude, longitude, distance_from_brno, 
                     is_in_czech_region, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    data['timestamp'], data['timestamp_ns'], data['latitude'],
                    data['longitude'], data['distance_from_brno'], 
                    data['is_in_czech_region'], data['raw_data']
                ))
                
                conn.commit()
                conn.close()
                return True
                
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.debug(f"Database locked, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                    import time
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Error storing lightning strike after {attempt + 1} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Error storing lightning strike: {e}")
                return False
                
        return False

    def update_hourly_summary(self, strike: LightningStrike):
        """Update hourly lightning activity summary with retry logic."""
        max_retries = 3
        base_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                hour_timestamp = strike.timestamp.replace(minute=0, second=0, microsecond=0)
                
                # Use a separate connection with timeout
                import sqlite3
                conn = sqlite3.connect(self.database.db_path, timeout=5.0)
                conn.execute("PRAGMA journal_mode=WAL")
                cursor = conn.cursor()
                
                # Update or insert hourly summary
                cursor.execute("""
                    INSERT OR IGNORE INTO lightning_activity_summary 
                    (hour_timestamp, total_strikes, czech_region_strikes, nearby_strikes, 
                     closest_strike_distance, average_distance)
                    VALUES (?, 0, 0, 0, 999999, 0)
                """, (hour_timestamp.isoformat(),))
                
                # Update statistics
                is_nearby = strike.distance_from_brno <= self.alert_radius_km
                is_czech = strike.is_in_czech_region
                
                cursor.execute("""
                    UPDATE lightning_activity_summary 
                    SET total_strikes = total_strikes + 1,
                        czech_region_strikes = czech_region_strikes + ?,
                        nearby_strikes = nearby_strikes + ?,
                        closest_strike_distance = MIN(closest_strike_distance, ?),
                        average_distance = (
                            SELECT AVG(distance_from_brno) FROM lightning_strikes 
                            WHERE timestamp BETWEEN ? AND ?
                        )
                    WHERE hour_timestamp = ?
                """, (
                    1 if is_czech else 0,
                    1 if is_nearby else 0,
                    strike.distance_from_brno,
                    hour_timestamp.isoformat(),
                    (hour_timestamp + timedelta(hours=1)).isoformat(),
                    hour_timestamp.isoformat()
                ))
                
                conn.commit()
                conn.close()
                return  # Success, exit retry loop
                
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.debug(f"Database locked during summary update, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                    import time
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Error updating hourly summary after {attempt + 1} attempts: {e}")
                    return
            except Exception as e:
                logger.error(f"Error updating hourly summary: {e}")
                return

    async def monitor_lightning(self):
        """Monitor lightning strikes from Blitzortung WebSocket with database integration."""
        self.is_running = True
        consecutive_failures = 0
        max_failures = 5
        
        logger.info("🌩️ Starting Lightning Strike Monitor for Czech Republic")
        logger.info(f"Focused on Brno area: {self.brno_lat:.4f}°N, {self.brno_lon:.4f}°E")
        logger.info(f"Czech region radius: {self.czech_region_radius_km}km, Alert radius: {self.alert_radius_km}km")
        
        while self.is_running:
            try:
                logger.info("Connecting to Blitzortung.org lightning network...")
                
                async with websockets.connect(self.ws_url) as websocket:
                    await websocket.send(self.subscription_message)
                    logger.info("✅ Connected! Monitoring for lightning strikes...")
                    consecutive_failures = 0  # Reset failure counter on successful connection
                    
                    async for message in websocket:
                        if not self.is_running:
                            break
                            
                        lightning_strike = self.extract_lightning_data(message)
                        
                        if lightning_strike:
                            self.total_strikes += 1
                            
                            # Update statistics
                            if lightning_strike.is_in_czech_region:
                                self.czech_strikes += 1
                            
                            if lightning_strike.distance_from_brno <= self.alert_radius_km:
                                self.nearby_strikes += 1
                                logger.warning(f"⚡ NEARBY LIGHTNING: {lightning_strike.distance_from_brno:.1f}km from Brno at {lightning_strike.latitude:.4f}°N, {lightning_strike.longitude:.4f}°E")
                            
                            # Store in database
                            if self.store_lightning_strike(lightning_strike):
                                self.update_hourly_summary(lightning_strike)
                            
                            # Call callback if provided
                            if self.on_lightning_callback:
                                try:
                                    self.on_lightning_callback(lightning_strike)
                                except Exception as e:
                                    logger.error(f"Error in lightning callback: {e}")
                            
                            # Log Czech region strikes
                            if lightning_strike.is_in_czech_region:
                                logger.info(f"⚡ Czech strike #{self.czech_strikes}: {lightning_strike.distance_from_brno:.1f}km from Brno")
                        
            except websockets.exceptions.ConnectionClosed:
                consecutive_failures += 1
                logger.warning(f"Connection lost (failure {consecutive_failures}/{max_failures})")
                
                if consecutive_failures >= max_failures:
                    logger.error("Max connection failures reached. Stopping lightning monitor.")
                    break
                    
                if self.is_running:
                    logger.info(f"Reconnecting in {self.reconnect_delay} seconds...")
                    await asyncio.sleep(self.reconnect_delay)
                    
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Lightning monitor error (failure {consecutive_failures}/{max_failures}): {e}")
                
                if consecutive_failures >= max_failures:
                    logger.error("Max errors reached. Stopping lightning monitor.")
                    break
                    
                if self.is_running:
                    await asyncio.sleep(self.reconnect_delay)
        
        logger.info(f"Lightning monitor stopped. Total: {self.total_strikes}, Czech: {self.czech_strikes}, Nearby: {self.nearby_strikes}")

    def stop(self):
        """Stop the lightning monitor."""
        self.is_running = False
        logger.info("Lightning monitor stop requested")

    def get_recent_lightning_activity(self, hours: int = 24) -> Dict[str, Any]:
        """Get recent lightning activity summary with database timeout handling."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            # Use a separate connection with timeout
            import sqlite3
            conn = sqlite3.connect(self.database.db_path, timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()
            
            # Get strike counts
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_strikes,
                    COUNT(CASE WHEN is_in_czech_region = 1 THEN 1 END) as czech_strikes,
                    COUNT(CASE WHEN distance_from_brno <= ? THEN 1 END) as nearby_strikes,
                    MIN(distance_from_brno) as closest_distance,
                    AVG(distance_from_brno) as average_distance
                FROM lightning_strikes 
                WHERE timestamp > ?
            """, (self.alert_radius_km, cutoff_time.isoformat()))
            
            row = cursor.fetchone()
            conn.close()
            
            return {
                'period_hours': hours,
                'total_strikes': row[0] or 0,
                'czech_strikes': row[1] or 0,
                'nearby_strikes': row[2] or 0,
                'closest_distance_km': row[3],
                'average_distance_km': row[4],
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting lightning activity: {e}")
            return {
                'period_hours': hours,
                'total_strikes': 0,
                'czech_strikes': 0,
                'nearby_strikes': 0,
                'closest_distance_km': None,
                'average_distance_km': None,
                'last_updated': datetime.now().isoformat(),
                'error': str(e)
            }

async def create_standalone_monitor() -> LightningMonitor:
    """Create a standalone lightning monitor for testing."""
    from config import load_config
    
    config = load_config()
    database = WeatherDatabase(config)
    
    def on_lightning_strike(strike: LightningStrike):
        """Callback for lightning strikes."""
        if strike.distance_from_brno <= 50:  # Alert threshold
            print(f"🚨 ALERT: Lightning {strike.distance_from_brno:.1f}km from Brno!")
        elif strike.is_in_czech_region:
            print(f"⚡ Czech Republic strike: {strike.distance_from_brno:.1f}km away")
    
    return LightningMonitor(config, database, on_lightning_strike)

def main():
    """Main function for standalone operation."""
    async def run_monitor():
        monitor = await create_standalone_monitor()
        try:
            await monitor.monitor_lightning()
        except KeyboardInterrupt:
            monitor.stop()
            print(f"\n✋ Lightning monitor stopped.")
            print(f"Statistics: {monitor.total_strikes} total, {monitor.czech_strikes} Czech, {monitor.nearby_strikes} nearby")
    
    try:
        asyncio.run(run_monitor())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")

if __name__ == "__main__":
    main()