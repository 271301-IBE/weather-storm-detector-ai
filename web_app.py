#!/usr/bin/env python3
"""
Weather Storm Detection System - Web Interface
Simple web dashboard for monitoring weather data, AI analysis, and system status.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, send_from_directory
from functools import wraps
import logging
from pathlib import Path
import os
import time
import psutil

from config import load_config
from models import WeatherForecast
from system_monitor import get_system_monitor, start_system_monitoring
from log_rotation import get_log_rotator
from telegram_poller import start_telegram_polling
from database_optimizer import get_database_optimizer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_url_path='/static')

# Load configuration
config = load_config()
app.secret_key = config.webapp.secret_key

# Lightweight security headers suitable for local network
@app.after_request
def add_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp

# Initialize database first
from storage import WeatherDatabase
from pdf_generator import WeatherReportGenerator
db = WeatherDatabase(config)
pdf_generator = WeatherReportGenerator(config)
try:
    from telegram_notifier import TelegramNotifier
except Exception:
    TelegramNotifier = None

# Simple asset cache-busting helper using file mtime
def asset_url(filename: str) -> str:
    """
    Build a static file URL with a cache-busting query param based on file mtime.
    Usage in templates: {{ asset_url('enhanced_forecast.js') }}
    """
    try:
        static_folder = Path(app.root_path) / "static"
        file_path = static_folder / filename
        if file_path.exists():
            v = int(file_path.stat().st_mtime)
            return url_for('static', filename=filename) + f'?v={v}'
    except Exception:
        pass
    return url_for('static', filename=filename)

# Expose helper to Jinja templates
app.jinja_env.globals['asset_url'] = asset_url

# Simple authentication
USERNAME = config.webapp.username
PASSWORD = config.webapp.password
SUBSCRIPTIONS_FILE = 'subscriptions.json'

# Very lightweight in-memory TTL cache for expensive API responses
class SimpleTTLCache:
    def __init__(self, max_items: int = 256):
        self._data = {}
        self._max_items = max_items

    def get(self, key: str):
        item = self._data.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            # Expired
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value, ttl_seconds: int):
        # Simple size control
        if len(self._data) >= self._max_items:
            # Drop an arbitrary item (LRU not necessary for our size)
            self._data.pop(next(iter(self._data)))
        self._data[key] = (time.time() + ttl_seconds, value)

    def invalidate_prefix(self, prefix: str):
        for k in list(self._data.keys()):
            if k.startswith(prefix):
                self._data.pop(k, None)

api_cache = SimpleTTLCache(max_items=256)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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



def save_subscription(subscription):
    """Save a push notification subscription."""
    try:
        subscriptions = []
        if os.path.exists(SUBSCRIPTIONS_FILE):
            with open(SUBSCRIPTIONS_FILE, 'r') as f:
                subscriptions = json.load(f)
        
        subscriptions.append(subscription)
        
        with open(SUBSCRIPTIONS_FILE, 'w') as f:
            json.dump(subscriptions, f)
            
        logger.info("Saved new push notification subscription.")
    except Exception as e:
        logger.error(f"Error saving subscription: {e}")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == USERNAME and password == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    """API login endpoint."""
    if not request.is_json:
        return jsonify({"error": "Missing JSON in request"}), 400

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if username == USERNAME and password == PASSWORD:
        session['logged_in'] = True
        return jsonify({'status': 'success', 'message': 'Logged in successfully.'})
    else:
        return jsonify({'status': 'error', 'message': 'Invalid credentials.'}), 401

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    """Main dashboard page."""
    
    # Fetch the latest forecasts for each method
    latest_ensemble = db.get_latest_forecast_by_method('ensemble')
    latest_physics = db.get_latest_forecast_by_method('physics')
    latest_ai = db.get_latest_forecast_by_method('ai')

    # Function to format forecast data for the template
    def format_forecast_data(forecast):
        if not forecast or not forecast.forecast_data:
            return None
        
        formatted_data = []
        for item in forecast.forecast_data:
            formatted_data.append({
                'timestamp': item.timestamp.strftime('%H:%M'),
                'temperature': round(item.temperature, 1),
                'humidity': round(item.humidity, 1),
                'pressure': round(item.pressure, 1),
                'wind_speed': round(item.wind_speed, 1),
                'precipitation': round(item.precipitation, 1),
                'precipitation_probability': round(item.precipitation_probability * 100, 0) if item.precipitation_probability is not None else None,
                'condition': item.condition.value,
                'cloud_cover': round(item.cloud_cover, 1) if item.cloud_cover is not None else None,
                'visibility': round(item.visibility, 1) if item.visibility is not None else None,
                'description': item.description,
                'confidence': round(item.metadata.confidence * 100, 0) if item.metadata and item.metadata.confidence is not None else 0,
                'confidence_level': item.metadata.confidence_level.value if item.metadata and item.metadata.confidence_level else 'unknown'
            })
            
        return {
            'forecast': formatted_data,
            'method': forecast.primary_method.value if forecast.primary_method else 'N/A',
            'confidence': round(forecast.method_confidences.get(forecast.primary_method.value, 0) * 100, 0) if forecast.method_confidences and forecast.primary_method else 0,
            'generated_at': forecast.timestamp.isoformat() if forecast.timestamp else None
        }

    # Prepare data for rendering
    forecast_data = {
        'ensemble': format_forecast_data(latest_ensemble) or {},
        'physics': format_forecast_data(latest_physics) or {},
        'ai': format_forecast_data(latest_ai) or {}
    }

    return render_template('dashboard.html', forecast_data=forecast_data)

@app.route('/map')
@login_required
def lightning_map():
    """Lightning map page."""
    return render_template('lightning_map.html', 
                         brno_lat=config.weather.latitude, 
                         brno_lon=config.weather.longitude,
                         city_name=config.weather.city_name)

@app.route('/history')
@login_required
def history():
    """History page."""
    return render_template('history.html')

@app.route('/system_info')
@login_required
def system_info():
    """System information page."""
    return render_template('system_info.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/api/system_metrics')
@login_required
def api_system_metrics():
    """Get system metrics like CPU temperature, usage, and RAM usage."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        ram_info = psutil.virtual_memory()
        
        # Attempt to get CPU temperature (Linux specific)
        cpu_temp = 'N/A'
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if "cpu_thermal" in temps:
                cpu_temp = temps["cpu_thermal"][0].current
            elif "coretemp" in temps:
                cpu_temp = temps["coretemp"][0].current
        
        return jsonify({
            'cpu_percent': cpu_percent,
            'ram_total': round(ram_info.total / (1024 ** 3), 2), # GB
            'ram_used': round(ram_info.used / (1024 ** 3), 2),   # GB
            'ram_percent': ram_info.percent,
            'cpu_temp': cpu_temp
        })
    except Exception as e:
        logger.error(f"Error fetching system metrics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/database_size')
@login_required
def api_database_size():
    """Get the size of the weather_data.db file."""
    try:
        db_path = config.system.database_path
        if os.path.exists(db_path):
            size_bytes = os.path.getsize(db_path)
            size_mb = round(size_bytes / (1024 ** 2), 2)
            return jsonify({'database_size_mb': size_mb})
        else:
            return jsonify({'database_size_mb': 0, 'error': 'Database file not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching database size: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js')

@app.route('/api/vapid_public_key')
@login_required
def vapid_public_key():
    """Provide the VAPID public key to the client."""
    return jsonify({'public_key': config.web_notification.vapid_public_key})

@app.route('/api/subscribe', methods=['POST'])
@login_required
def subscribe():
    """Subscribe a user for push notifications."""
    subscription_info = request.json
    save_subscription(subscription_info)
    return jsonify({'success': True})

@app.route('/api/current_weather')
@login_required
def api_current_weather():
    """Get current weather data."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get latest weather data from all three sources
            cursor.execute("""
                SELECT * FROM weather_data 
                ORDER BY created_at DESC 
                LIMIT 3
            """ )
            
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            weather_data = []
            for row in rows:
                data = dict(zip(columns, row))
                weather_data.append(data)
            
            return jsonify(weather_data)
        
    except Exception as e:
        logger.error(f"Error fetching current weather: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recent_analysis')
@login_required
def api_recent_analysis():
    """Get recent AI analysis results."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM storm_analysis 
                ORDER BY timestamp DESC 
                LIMIT 10
            """ )
            
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            analysis_data = []
            for row in rows:
                data = dict(zip(columns, row))
                # Parse JSON fields
                if data.get('recommendations'):
                    try:
                        data['recommendations'] = json.loads(data['recommendations'])
                    except:
                        data['recommendations'] = []
                analysis_data.append(data)
            
            return jsonify(analysis_data)
        
    except Exception as e:
        logger.error(f"Error fetching analysis data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/weather_history')
@login_required
def api_weather_history():
    """Get weather history for charts with CHMI alerts."""
    try:
        hours = request.args.get('hours', 72, type=int)
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get weather data
            cursor.execute("""
                SELECT timestamp, temperature, humidity, pressure, wind_speed, precipitation, source
                FROM weather_data 
                WHERE datetime(timestamp) > datetime('now', '-{} hours')
                ORDER BY timestamp
            """.format(hours))
            
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            history_data = []
            for row in rows:
                data = dict(zip(columns, row))
                data['timestamp'] = datetime.fromisoformat(data['timestamp']).timestamp() * 1000
                history_data.append(data)
            
            # Get CHMI warnings/alerts for the same period
            try:
                from chmi_warnings import ChmiWarningMonitor
                chmi_monitor = ChmiWarningMonitor(config)
                warnings = chmi_monitor.get_all_warnings_for_period(hours=hours)
                
                chmi_alerts = []
                for warning in warnings:
                    # Ensure description_text exists
                    description = getattr(warning, 'description_text', None) or getattr(warning, 'detailed_text', '')
                    
                    alert_data = {
                        'id': warning.identifier,
                        'event': warning.event,
                        'color': warning.color,
                        'start_time': warning.time_start_iso,
                        'end_time': warning.time_end_iso,
                        'description': description,
                        'urgency': warning.urgency
                    }
                    if warning.time_start_iso:
                        try:
                            start_dt = datetime.fromisoformat(warning.time_start_iso.replace('Z', '+00:00'))
                            alert_data['start_timestamp'] = start_dt.timestamp() * 1000
                        except:
                            pass
                    if warning.time_end_iso:
                        try:
                            end_dt = datetime.fromisoformat(warning.time_end_iso.replace('Z', '+00:00'))
                            alert_data['end_timestamp'] = end_dt.timestamp() * 1000
                        except:
                            pass
                    chmi_alerts.append(alert_data)
                    
            except Exception as e:
                logger.warning(f"Could not fetch CHMI alerts: {e}")
                chmi_alerts = []
            
            return jsonify({
                'weather_data': history_data,
                'chmi_alerts': chmi_alerts
            })
        
    except Exception as e:
        logger.error(f"Error fetching weather history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/storm_event', methods=['POST'])
@login_required
def api_storm_event():
    """Log a user-reported storm event for machine learning."""
    try:
        data = request.json
        event_type = data.get('type', 'storm_now')  # 'storm_now', 'rain_now', 'no_storm'
        user_timestamp = datetime.now().isoformat()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_storm_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    weather_data_json TEXT,
                    chmi_warnings_json TEXT,
                    ai_confidence REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Get current weather data
            cursor.execute("""
                SELECT temperature, humidity, pressure, wind_speed, precipitation, 
                       precipitation_probability, condition, description
                FROM weather_data 
                ORDER BY timestamp DESC 
                LIMIT 3
            """)
            
            weather_rows = cursor.fetchall()
            weather_data = []
            for row in weather_rows:
                weather_data.append({
                    'temperature': row[0],
                    'humidity': row[1], 
                    'pressure': row[2],
                    'wind_speed': row[3],
                    'precipitation': row[4],
                    'precipitation_probability': row[5],
                    'condition': row[6],
                    'description': row[7]
                })
            
            # Get current AI analysis confidence
            cursor.execute("""
                SELECT confidence_score FROM storm_analysis 
                ORDER BY timestamp DESC 
                LIMIT 1
            """)
            ai_row = cursor.fetchone()
            ai_confidence = ai_row[0] if ai_row else None
            
            # Get current CHMI warnings
            try:
                from chmi_warnings import ChmiWarningMonitor
                chmi_monitor = ChmiWarningMonitor(config)
                warnings = chmi_monitor.get_storm_warnings()
                chmi_data = [{
                    'event': w.event,
                    'color': w.color,
                    'description': w.description_text
                } for w in warnings]
            except:
                chmi_data = []
            
            # Store the event
            cursor.execute("""
                INSERT INTO user_storm_events 
                (timestamp, event_type, weather_data_json, chmi_warnings_json, ai_confidence)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_timestamp,
                event_type,
                json.dumps(weather_data),
                json.dumps(chmi_data),
                ai_confidence
            ))
            
            conn.commit()
            
        logger.info(f"User reported storm event: {event_type} at {user_timestamp}")
        return jsonify({'success': True, 'timestamp': user_timestamp})
        
    except Exception as e:
        logger.error(f"Error logging storm event: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/storm_learning_data')
@login_required
def api_storm_learning_data():
    """Get historical storm events for machine learning analysis."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT timestamp, event_type, weather_data_json, chmi_warnings_json, ai_confidence
                FROM user_storm_events 
                ORDER BY timestamp DESC 
                LIMIT 100
            """)
            
            rows = cursor.fetchall()
            events = []
            
            for row in rows:
                try:
                    weather_data = json.loads(row[2]) if row[2] else []
                    chmi_data = json.loads(row[3]) if row[3] else []
                except:
                    weather_data = []
                    chmi_data = []
                    
                events.append({
                    'timestamp': row[0],
                    'event_type': row[1],
                    'weather_data': weather_data,
                    'chmi_warnings': chmi_data,
                    'ai_confidence': row[4]
                })
            
            return jsonify(events)
        
    except Exception as e:
        logger.error(f"Error fetching learning data: {e}")
        return jsonify({'error': str(e)}), 500

# Lightning Data APIs
@app.route('/api/lightning_current')
@login_required
def api_lightning_current():
    """Get current lightning activity data."""
    try:
        cache_key = "lightning_current:v1"
        cached = api_cache.get(cache_key)
        if cached:
            return jsonify(cached)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Prefer fast pre-aggregated hourly summary; fallback to raw scan
            one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
            try:
                cursor.execute(
                    """
                    SELECT 
                        COALESCE(SUM(total_strikes),0),
                        COALESCE(SUM(czech_region_strikes),0),
                        COALESCE(SUM(nearby_strikes),0),
                        MIN(closest_strike_distance),
                        AVG(average_distance)
                    FROM lightning_activity_summary
                    WHERE hour_timestamp > ?
                    """,
                    (one_hour_ago,)
                )
                row = cursor.fetchone()
                use_summary = True
            except Exception:
                use_summary = False
                cursor.execute(
                    """
                    SELECT COUNT(*) as total_strikes,
                           COUNT(CASE WHEN is_in_czech_region = 1 THEN 1 END) as czech_strikes,
                           COUNT(CASE WHEN distance_from_brno <= 50 THEN 1 END) as nearby_strikes,
                           MIN(distance_from_brno) as closest_distance,
                           AVG(distance_from_brno) as average_distance
                    FROM lightning_strikes 
                    WHERE timestamp > ?
                    """,
                    (one_hour_ago,)
                )
                row = cursor.fetchone()
            
            activity = {
                'period_hours': 1,
                'total_strikes': row[0] or 0,
                'czech_strikes': row[1] or 0,
                'nearby_strikes': row[2] or 0,
                'closest_distance_km': row[3],
                'average_distance_km': row[4],
                'last_updated': datetime.now().isoformat(),
                'threat_level': 'NONE'
            }
            
            # Assess threat level
            if activity['closest_distance_km']:
                if activity['closest_distance_km'] <= 20:
                    activity['threat_level'] = 'HIGH'
                elif activity['closest_distance_km'] <= 50 or activity['czech_strikes'] >= 3:
                    activity['threat_level'] = 'MEDIUM'
                elif activity['czech_strikes'] > 0:
                    activity['threat_level'] = 'LOW'
            
            # Cache briefly; currents change fast but avoid repeated heavy scans
            api_cache.set(cache_key, activity, ttl_seconds=30)
            return jsonify(activity)
        
    except Exception as e:
        logger.error(f"Error fetching current lightning activity: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/lightning_strikes')
@login_required
def api_lightning_strikes():
    """Get recent lightning strikes for map visualization."""
    try:
        hours = int(request.args.get('hours', 3))  # Default to last 3 hours
        limit = int(request.args.get('limit', 500))  # Limit for performance
        cache_key = f"lightning_strikes:v1:h{hours}:l{limit}"
        cached = api_cache.get(cache_key)
        if cached:
            return jsonify(cached)
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            # Approximate bounding box for Europe
            # Latitude: 35°N to 72°N
            # Longitude: -10°W to 35°E
            min_lat, max_lat = 35.0, 72.0
            min_lon, max_lon = -10.0, 35.0

            cursor.execute("""
                SELECT timestamp, latitude, longitude, distance_from_brno, is_in_czech_region
                FROM lightning_strikes 
                WHERE timestamp > ?
                AND latitude BETWEEN ? AND ?
                AND longitude BETWEEN ? AND ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (cutoff_time, min_lat, max_lat, min_lon, max_lon, limit))
            
            strikes = []
            for row in cursor.fetchall():
                strikes.append({
                    'timestamp': row[0],
                    'latitude': row[1],
                    'longitude': row[2],
                    'distance_from_brno': row[3],
                    'is_in_czech_region': row[4],
                    'age_minutes': max(0, (datetime.now() - datetime.fromisoformat(row[0])).total_seconds() / 60)
                })
            
            payload = {
                'strikes': strikes,
                'total_count': len(strikes),
                'hours_requested': hours,
                'brno_coordinates': {
                    'latitude': config.weather.latitude,
                    'longitude': config.weather.longitude
                }
            }
            api_cache.set(cache_key, payload, ttl_seconds=15)
            return jsonify(payload)
        
    except Exception as e:
        logger.error(f"Error fetching lightning strikes: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/lightning_dashboard_stats')
@login_required
def api_lightning_dashboard_stats():
    """Get lightning detection statistics for the dashboard."""
    try:
        cache_key = "lightning_dashboard_stats:v1"
        cached = api_cache.get(cache_key)
        if cached:
            return jsonify(cached)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Prefer pre-aggregated totals from summary table (fast), fallback to raw counts
            stats = {}
            try:
                cursor.execute(
                    """
                    SELECT 
                        COALESCE(SUM(total_strikes),0),
                        COALESCE(SUM(czech_region_strikes),0),
                        COALESCE(SUM(nearby_strikes),0)
                    FROM lightning_activity_summary
                    """
                )
                t, c, n = cursor.fetchone()
                stats['total_strikes'] = t or 0
                stats['czech_strikes'] = c or 0
                stats['nearby_strikes'] = n or 0
            except Exception:
                cursor.execute("SELECT COUNT(*) as total FROM lightning_strikes")
                stats['total_strikes'] = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) as czech FROM lightning_strikes WHERE is_in_czech_region = 1")
                stats['czech_strikes'] = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) as nearby FROM lightning_strikes WHERE distance_from_brno <= 50")
                stats['nearby_strikes'] = cursor.fetchone()[0] or 0
            
            api_cache.set(cache_key, stats, ttl_seconds=300)
            return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error fetching lightning statistics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/lightning_stats')
@login_required
def api_lightning_stats():
    """Get lightning detection statistics."""
    try:
        cache_key = "lightning_stats:v2"
        cached = api_cache.get(cache_key)
        if cached:
            return jsonify(cached)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get statistics for different time periods
            stats = {}
            
            for period, hours in [('1h', 1), ('6h', 6), ('24h', 24), ('7d', 168)]:
                cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
                # Prefer summary table aggregation
                try:
                    cursor.execute(
                        """
                        SELECT 
                            COALESCE(SUM(total_strikes),0),
                            COALESCE(SUM(czech_region_strikes),0),
                            COALESCE(SUM(nearby_strikes),0),
                            MIN(closest_strike_distance)
                        FROM lightning_activity_summary
                        WHERE hour_timestamp > ?
                        """,
                        (cutoff_time,)
                    )
                    row = cursor.fetchone()
                except Exception:
                    cursor.execute(
                        """
                        SELECT COUNT(*) as total,
                               COUNT(CASE WHEN is_in_czech_region = 1 THEN 1 END) as czech,
                               COUNT(CASE WHEN distance_from_brno <= 50 THEN 1 END) as nearby,
                               MIN(distance_from_brno) as closest
                        FROM lightning_strikes 
                        WHERE timestamp > ?
                        """,
                        (cutoff_time,)
                    )
                    row = cursor.fetchone()

                stats[period] = {
                    'total_strikes': row[0] or 0,
                    'czech_strikes': row[1] or 0,
                    'nearby_strikes': row[2] or 0,
                    'closest_distance_km': row[3]
                }
            
            # Get hourly distribution for the last 24 hours
            cursor.execute("""
                SELECT hour_timestamp, total_strikes, czech_region_strikes, nearby_strikes
                FROM lightning_activity_summary 
                WHERE hour_timestamp > ?
                ORDER BY hour_timestamp DESC
            """, ((datetime.now() - timedelta(hours=24)).isoformat(),))
            
            hourly_data = []
            for row in cursor.fetchall():
                hourly_data.append({
                    'hour': row[0],
                    'total': row[1],
                    'czech': row[2],
                    'nearby': row[3]
                })
            
            payload = {
                'periods': stats,
                'hourly_distribution': hourly_data,
                'system_status': 'active',
                'last_updated': datetime.now().isoformat()
            }
            api_cache.set(cache_key, payload, ttl_seconds=120)
            return jsonify(payload)
        
    except Exception as e:
        logger.error(f"Error fetching lightning statistics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/system_stats')
@login_required
def api_system_stats():
    """Get system statistics."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Weather data count (last 24h)
            cursor.execute("""
                SELECT COUNT(*) FROM weather_data 
                WHERE datetime(timestamp) > datetime('now', '-24 hours')
            """ )
            stats['weather_data_24h'] = cursor.fetchone()[0]
            
            # AI analysis count (last 24h)
            cursor.execute("""
                SELECT COUNT(*) FROM storm_analysis 
                WHERE datetime(timestamp) > datetime('now', '-24 hours')
            """ )
            stats['ai_analysis_24h'] = cursor.fetchone()[0]
            
            # Email notifications count (last 24h)
            cursor.execute("""
                SELECT COUNT(*) FROM email_notifications 
                WHERE datetime(timestamp) > datetime('now', '-24 hours')
            """ )
            stats['emails_24h'] = cursor.fetchone()[0]
            
            # Storm detections (last 7 days)
            cursor.execute("""
                SELECT COUNT(*) FROM storm_analysis 
                WHERE datetime(timestamp) > datetime('now', '-7 days')
                AND storm_detected = 1
            """ )
            stats['storms_detected_7d'] = cursor.fetchone()[0]
            
            # High confidence predictions (last 7 days)
            cursor.execute("""
                SELECT COUNT(*) FROM storm_analysis 
                WHERE datetime(timestamp) > datetime('now', '-7 days')
                AND confidence_score > 0.8
            """ )
            stats['high_confidence_7d'] = cursor.fetchone()[0]
            
            # Average confidence score (last 7 days)
            cursor.execute("""
                SELECT AVG(confidence_score) FROM storm_analysis 
                WHERE datetime(timestamp) > datetime('now', '-7 days')
            """ )
            avg_confidence = cursor.fetchone()[0]
            stats['avg_confidence_7d'] = round(avg_confidence * 100, 1) if avg_confidence else 0
            
            # Cache efficiency
            cursor.execute("""
                SELECT COUNT(*) FROM weather_condition_cache 
                WHERE expires_at > datetime('now')
            """ )
            stats['active_cache_entries'] = cursor.fetchone()[0]
            
            # Database size estimation
            cursor.execute("SELECT COUNT(*) FROM weather_data")
            stats['total_weather_records'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM storm_analysis")
            stats['total_analysis_records'] = cursor.fetchone()[0]
            
            # Estimate API costs (rough calculation)
            # DeepSeek: ~$0.001 per analysis
            # Weather APIs: free tier usage
            stats['estimated_ai_cost_24h'] = round(stats['ai_analysis_24h'] * 0.001, 3)
            stats['estimated_ai_cost_7d'] = round(stats['ai_analysis_24h'] * 7 * 0.001, 2)
            
            return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error fetching system stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/system_status')
@login_required
def api_system_status():
    """Get system status including CPU temp, usage, RAM, and DB size."""
    try:
        # Local lightweight stats without external cpu_monitor dependency
        cpu_percent = psutil.cpu_percent(interval=0.5)
        ram_info = psutil.virtual_memory()
        ram_percent = ram_info.percent

        # Try to get temperature (Linux specific, may not exist)
        cpu_temp = None
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if "cpu_thermal" in temps and temps["cpu_thermal"]:
                    cpu_temp = temps["cpu_thermal"][0].current
                elif "coretemp" in temps and temps["coretemp"]:
                    cpu_temp = temps["coretemp"][0].current
        except Exception:
            cpu_temp = None

        db_path = config.system.database_path
        db_size = 0
        if os.path.exists(db_path):
            db_size = round(os.path.getsize(db_path) / (1024 * 1024), 2)
            
        return jsonify({
            'cpu_temp': cpu_temp if cpu_temp is not None else 'N/A',
            'cpu_percent': cpu_percent,
            'ram_percent': ram_percent,
            'database_size_mb': db_size
        })
    except Exception as e:
        logger.error(f"Error in api_system_status: {e}")
        return jsonify({'error': 'Could not retrieve system status.'}), 500

@app.route('/api/email_history')
@login_required
def api_email_history():
    """Get email notification history."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT timestamp, recipient, subject, message_type, sent_successfully, error_message
                FROM email_notifications 
                ORDER BY timestamp DESC 
                LIMIT 20
            """ )
            
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            email_data = []
            for row in rows:
                data = dict(zip(columns, row))
                email_data.append(data)
            
            return jsonify(email_data)
        
    except Exception as e:
        logger.error(f"Error fetching email history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/notification_history')
@login_required
def api_notification_history():
    """Unified recent notification history (email + telegram)."""
    try:
        items = []
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Emails
            cursor.execute(
                """
                SELECT timestamp, subject, message_type, sent_successfully, error_message
                FROM email_notifications ORDER BY timestamp DESC LIMIT 20
                """
            )
            for row in cursor.fetchall():
                items.append({
                    'timestamp': row[0],
                    'channel': 'email',
                    'title': row[1],
                    'type': row[2],
                    'ok': bool(row[3]),
                    'error': row[4]
                })
            # Telegram
            cursor.execute(
                """
                SELECT timestamp, text, sent_successfully, error_message
                FROM telegram_notifications ORDER BY timestamp DESC LIMIT 20
                """
            )
            for row in cursor.fetchall():
                items.append({
                    'timestamp': row[0],
                    'channel': 'telegram',
                    'title': row[1],
                    'type': 'telegram_alert',
                    'ok': bool(row[2]),
                    'error': row[3]
                })
        # Sort all by timestamp desc
        try:
            items.sort(key=lambda x: x['timestamp'], reverse=True)
        except Exception:
            pass
        return jsonify(items[:20])
    except Exception as e:
        logger.error(f"Error fetching notification history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/telegram_test_alert', methods=['POST'])
@login_required
def api_telegram_test_alert():
    """Send a test alert via Telegram to verify delivery."""
    try:
        if not getattr(config, 'telegram', None):
            return jsonify({'success': False, 'error': 'Telegram config missing'}), 400
        if not config.telegram.enabled:
            return jsonify({'success': False, 'error': 'Telegram not enabled (set TELEGRAM_ENABLED=true)'}), 400
        if not TelegramNotifier:
            return jsonify({'success': False, 'error': 'Telegram notifier unavailable'}), 400
        if not config.telegram.bot_token or not config.telegram.chat_id:
            return jsonify({'success': False, 'error': 'Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID'}), 400
        notifier = TelegramNotifier(config)
        text = f"\ud83d\udce2 Test alert from Clipron AI Weather at {datetime.now().strftime('%H:%M:%S')}"
        ok = notifier.send_message(text)
        if ok:
            return jsonify({'success': True}), 200
        return jsonify({'success': False, 'error': 'Telegram API send failed. Check bot token/chat id and network.'}), 502
    except Exception as e:
        logger.error(f"Error sending Telegram test alert: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/telegram_webhook/<token>', methods=['POST'])
def telegram_webhook(token: str):
    """Telegram webhook for simple learning commands and /weather summary request.

    Security: We use the bot token as the path secret. Telegram will POST updates here if configured.
    """
    try:
        logger.info("Telegram webhook hit")
        if token != (config.telegram.bot_token or ''):
            return jsonify({'error': 'unauthorized'}), 403
        data = request.get_json(force=True, silent=True) or {}
        message_obj = (data.get('message') or {})
        message = message_obj.get('text', '')
        chat = (message_obj.get('chat') or {})
        chat_id = str(chat.get('id')) if chat.get('id') is not None else None
        logger.info(f"Telegram update: chat_id={chat_id} text={message!r}")
        if not message:
            return jsonify({'ok': True})
        cmd = message.strip().lower()
        # Handle /weather rich summary
        if cmd.startswith('/weather'):
            try:
                # Build comprehensive summary
                from telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier(config)
                logger.info(f"Handling /weather for chat_id={chat_id}")

                # Current conditions (latest)
                with db.get_connection(read_only=True) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT timestamp, temperature, humidity, pressure, wind_speed, precipitation, description
                        FROM weather_data ORDER BY timestamp DESC LIMIT 1
                        """
                    )
                    row = cur.fetchone()
                    current_text = "N/A"
                    if row:
                        current_text = (
                            f"Now: {row[5] or ''} | Temp {row[1]:.1f}°C, Hum {row[2]:.0f}%, "
                            f"Press {row[3]:.0f} hPa, Wind {row[4]:.1f} m/s, Precip {row[5]:.1f} mm"
                            if row[1] is not None else f"Now: {row[6] or ''}"
                        )
                        logger.debug(f"/weather current row: ts={row[0]} temp={row[1]} hum={row[2]} press={row[3]} wind={row[4]} precip={row[5]}")

                # Next predicted storm
                try:
                    with db.get_connection(read_only=True) as conn:
                        cur = conn.cursor()
                        cur.execute(
                            """
                            SELECT prediction_timestamp, confidence, created_at
                            FROM thunderstorm_predictions ORDER BY created_at DESC LIMIT 1
                            """
                        )
                        p = cur.fetchone()
                        storm_line = "No storm predicted"
                        if p:
                            try:
                                predicted_dt = datetime.fromisoformat(p[0])
                                if predicted_dt > datetime.now():
                                    storm_line = f"Storm ▶ {predicted_dt.strftime('%d.%m %H:%M')} (conf {float(p[1])*100:.0f}%)"
                                logger.debug(f"/weather prediction row: predicted={p[0]} conf={p[1]} created={p[2]}")
                            except Exception:
                                pass
                except Exception:
                    storm_line = ""

                # CHMI warnings (filtered to region)
                try:
                    from chmi_warnings import ChmiWarningMonitor
                    chmi_monitor = ChmiWarningMonitor(config)
                    warnings = chmi_monitor.get_all_active_warnings()
                    region_hits = []
                    for w in warnings:
                        desc = getattr(w, 'area_description', '') or ''
                        if 'jihomorav' in desc.lower() or 'brno' in desc.lower():
                            region_hits.append(w)
                    logger.debug(f"/weather CHMI region warnings count={len(region_hits)} total={len(warnings)}")
                    if region_hits:
                        chmi_line = "CHMI: " + ", ".join([f"{w.event} ({w.color})" for w in region_hits[:5]])
                    else:
                        chmi_line = "CHMI: none for region"
                except Exception:
                    chmi_line = "CHMI: unavailable"

                # Lightning snapshot (last hour)
                try:
                    with db.get_connection(read_only=True) as conn:
                        cur = conn.cursor()
                        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
                        try:
                            cur.execute(
                                """
                                SELECT COALESCE(SUM(total_strikes),0), COALESCE(SUM(nearby_strikes),0), MIN(closest_strike_distance)
                                FROM lightning_activity_summary WHERE hour_timestamp > ?
                                """,
                                (one_hour_ago,)
                            )
                            row = cur.fetchone()
                            lt_line = f"Lightning: total {row[0] or 0}, nearby {row[1] or 0}, closest {row[2]:.1f} km" if row and row[2] is not None else f"Lightning: total {row[0] or 0}, nearby {row[1] or 0}"
                            logger.debug(f"/weather lightning summary: total={row[0]} nearby={row[1]} closest={row[2]}")
                        except Exception:
                            # fallback raw
                            cur.execute(
                                """
                                SELECT COUNT(*), COUNT(CASE WHEN distance_from_brno <= 50 THEN 1 END), MIN(distance_from_brno)
                                FROM lightning_strikes WHERE timestamp > ?
                                """,
                                (one_hour_ago,)
                            )
                            row = cur.fetchone()
                            lt_line = f"Lightning: total {row[0] or 0}, nearby {row[1] or 0}, closest {row[2]:.1f} km" if row and row[2] is not None else f"Lightning: total {row[0] or 0}, nearby {row[1] or 0}"
                            logger.debug(f"/weather lightning raw: total={row[0]} nearby={row[1]} closest={row[2]}")
                except Exception:
                    lt_line = "Lightning: unavailable"

                summary_text = (
                    f"<b>{config.weather.city_name}</b> • {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                    f"{current_text}\n{storm_line}\n{chmi_line}\n{lt_line}"
                )

                # Send text summary
                if chat_id:
                    sent = notifier.send_message(summary_text, chat_id=chat_id)
                    logger.info(f"/weather text sent chat_id={chat_id} ok={sent}")

                # Optional: send a chart image from last 24h
                try:
                    from pdf_generator import WeatherReportGenerator
                    from models import WeatherData
                    weather_rows = db.get_recent_weather_data(hours=24)
                    # Downsample to avoid huge charts
                    series = list(reversed(weather_rows))[:120]
                    gen = WeatherReportGenerator(config)
                    img_path = gen.create_chart_image(series, datetime.now()) if series else None
                    logger.debug(f"/weather chart path={img_path} points={len(series) if series else 0}")
                    if img_path and chat_id:
                        photo_ok = TelegramNotifier(config).send_photo(img_path, caption="24h weather chart", chat_id=chat_id)
                        logger.info(f"/weather photo sent chat_id={chat_id} ok={photo_ok}")
                except Exception:
                    logger.exception("/weather chart send failed")

                return jsonify({'ok': True})
            except Exception as e:
                logger.error(f"/weather handler error: {e}")
                # Try to inform user
                try:
                    if chat_id and TelegramNotifier:
                        TelegramNotifier(config).send_message("⚠️ Sorry, failed to build weather summary.", chat_id=chat_id)
                except Exception:
                    pass
                return jsonify({'ok': True})
        mapping = {
            'rain': 'rain_now',
            'storm': 'storm_now',
            'thunderstorm': 'storm_now',
            'hail': 'hail_now',
            'no_storm': 'no_storm',
            'clear': 'no_storm'
        }
        event_type = mapping.get(cmd)
        if not event_type:
            # Ignore non-learning messages
            logger.info(f"Telegram message ignored (no command match): chat_id={chat_id} text={cmd!r}")
            return jsonify({'ok': True})
        # Record the event similar to api_storm_event
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_storm_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    weather_data_json TEXT,
                    chmi_warnings_json TEXT,
                    ai_confidence REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Basic snapshot: latest weather rows
            cursor.execute(
                """
                SELECT temperature, humidity, pressure, wind_speed, precipitation,
                       precipitation_probability, condition, description
                FROM weather_data ORDER BY timestamp DESC LIMIT 3
                """
            )
            weather_rows = cursor.fetchall()
            weather_data = []
            for row in weather_rows:
                weather_data.append({
                    'temperature': row[0], 'humidity': row[1], 'pressure': row[2],
                    'wind_speed': row[3], 'precipitation': row[4],
                    'precipitation_probability': row[5], 'condition': row[6],
                    'description': row[7]
                })
            # Insert
            cursor.execute(
                """
                INSERT INTO user_storm_events (timestamp, event_type, weather_data_json, chmi_warnings_json, ai_confidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (datetime.now().isoformat(), event_type, json.dumps(weather_data), json.dumps([]), None)
            )
            conn.commit()
        logger.info(f"Recorded user event from Telegram: chat_id={chat_id} type={event_type}")
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return jsonify({'error': 'internal error'}), 500

@app.route('/api/api_usage_stats')
@login_required
def api_api_usage_stats():
    """Get API usage statistics for all weather sources."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # API call counts by source (last 24 hours)
            cursor.execute("""
                SELECT source, COUNT(*) as call_count
                FROM weather_data 
                WHERE datetime(timestamp) > datetime('now', '-24 hours')
                GROUP BY source
                ORDER BY call_count DESC
            """ )
            
            api_usage_24h = {}
            rows = cursor.fetchall()
            for source, count in rows:
                api_usage_24h[source] = count
            
            # API call counts by source (last 7 days)
            cursor.execute("""
                SELECT source, COUNT(*) as call_count
                FROM weather_data 
                WHERE datetime(timestamp) > datetime('now', '-7 days')
                GROUP BY source
                ORDER BY call_count DESC
            """ )
            
            api_usage_7d = {}
            rows = cursor.fetchall()
            for source, count in rows:
                api_usage_7d[source] = count
            
            # Total API calls by source (all time)
            cursor.execute("""
                SELECT source, COUNT(*) as call_count
                FROM weather_data 
                GROUP BY source
                ORDER BY call_count DESC
            """ )
            
            api_usage_total = {}
            rows = cursor.fetchall()
            for source, count in rows:
                api_usage_total[source] = count
            
            # Latest data timestamp for each API
            cursor.execute("""
                SELECT source, MAX(timestamp) as last_update
                FROM weather_data 
                GROUP BY source
            """ )
            
            api_last_update = {}
            rows = cursor.fetchall()
            for source, timestamp in rows:
                api_last_update[source] = timestamp
                
            return jsonify({
                'usage_24h': api_usage_24h,
                'usage_7d': api_usage_7d, 
                'usage_total': api_usage_total,
                'last_updates': api_last_update
            })
        
    except Exception as e:
        logger.error(f"Error fetching API usage stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/weather_averages')
@login_required
def api_weather_averages():
    """Get average weather data from all API sources."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get latest data from each source
            cursor.execute("""
                SELECT 
                    AVG(temperature) as avg_temp,
                    AVG(humidity) as avg_humidity,
                    AVG(pressure) as avg_pressure,
                    AVG(wind_speed) as avg_wind_speed,
                    AVG(precipitation_probability) as avg_precip_prob,
                    AVG(precipitation) as avg_precipitation,
                    COUNT(DISTINCT source) as source_count
                FROM weather_data w1
                WHERE w1.timestamp = (
                    SELECT MAX(timestamp) 
                    FROM weather_data w2 
                    WHERE w2.source = w1.source
                )
            """ )
            
            result = cursor.fetchone()
            if result:
                avg_temp, avg_humidity, avg_pressure, avg_wind_speed, avg_precip_prob, avg_precipitation, source_count = result
                
                averages = {
                    'temperature': round(avg_temp, 1) if avg_temp is not None else None,
                    'humidity': round(avg_humidity, 1) if avg_humidity is not None else None,
                    'pressure': round(avg_pressure, 1) if avg_pressure is not None else None,
                    'wind_speed': round(avg_wind_speed, 1) if avg_wind_speed is not None else None,
                    'precipitation_probability': round(avg_precip_prob, 1) if avg_precip_prob is not None else None,
                    'precipitation': round(avg_precipitation, 1) if avg_precipitation is not None else None,
                    'source_count': source_count or 0
                }
            else:
                averages = {}
                
            return jsonify(averages)
        
    except Exception as e:
        logger.error(f"Error fetching weather averages: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chmi_warnings')
@login_required
def api_chmi_warnings():
    """Get current ČHMÚ weather warnings for Brno."""
    try:
        from config import load_config
        from chmi_warnings import ChmiWarningMonitor
        
        config = load_config()
        chmi_monitor = ChmiWarningMonitor(config)
        
        # Get all current warnings and filter only for Brno/Jihomoravský kraj
        all_warnings = chmi_monitor.get_all_active_warnings()
        
        # Filter out warnings that have expired and keep only Jihomoravský kraj/Brno warnings
        current_time = datetime.now()
        warnings = []
        for w in all_warnings:
            # Check if area description contains Jihomoravský kraj or Brno
            area_desc = getattr(w, 'area_description', '')
            if area_desc and ('jihomoravský' in area_desc.lower() or 'brno' in area_desc.lower()):
                # Check if warning is still valid (not expired)
                if hasattr(w, 'time_end_unix') and w.time_end_unix:
                    # Convert unix timestamp to datetime for comparison
                    end_time = datetime.fromtimestamp(w.time_end_unix)
                    if end_time > current_time:
                        warnings.append(w)
                elif hasattr(w, 'time_end_iso') and w.time_end_iso:
                    # Parse ISO time string
                    end_time = datetime.fromisoformat(w.time_end_iso.replace('Z', '+00:00')).replace(tzinfo=None)
                    if end_time > current_time:
                        warnings.append(w)
                else:
                    # No end time specified, assume it's active
                    warnings.append(w)
        
        warning_data = []
        for warning in warnings:
            warning_info = {
                'event': warning.event,
                'color': warning.color,
                'severity': getattr(warning, 'severity', None),
                'description': getattr(warning, 'area_description', None),
                'time_start': warning.time_start_iso,
                'time_end': warning.time_end_iso,
                'identifier': getattr(warning, 'identifier', None)
            }
            warning_data.append(warning_info)
        
        # Get storm-specific warnings from filtered warnings
        storm_warnings = [w for w in warnings if any(keyword in w.event.lower() for keyword in ['bouř', 'déšť', 'vichr', 'povodeň', 'vítr'])]
        storm_count = len(storm_warnings)
        
        return jsonify({
            'warnings': warning_data,
            'total_warnings': len(warning_data),
            'storm_warnings': storm_count,
            'last_updated': None  # Parser doesn't track fetch time
        })
        
    except Exception as e:
        logger.error(f"Error fetching ČHMÚ warnings: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/next_storm_prediction')
@login_required
def api_next_storm_prediction():
    """Get the latest thunderstorm prediction."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS thunderstorm_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_timestamp TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                SELECT prediction_timestamp, confidence, created_at 
                FROM thunderstorm_predictions 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            
            if row:
                try:
                    predicted_dt = datetime.fromisoformat(row[0])
                except Exception:
                    # If parsing fails, treat as invalid
                    return jsonify({'error': 'No valid prediction available'}), 404

                # Do not show stale predictions in the past
                now_dt = datetime.now()
                if predicted_dt <= now_dt:
                    return jsonify({'error': 'No prediction available'}), 404

                # Optional freshness guard: hide very old records (e.g., > 12 hours old)
                try:
                    created_dt = datetime.fromisoformat(row[2]) if len(row) > 2 and row[2] else None
                    if created_dt and (now_dt - created_dt).total_seconds() > 12 * 3600:
                        return jsonify({'error': 'No prediction available'}), 404
                except Exception:
                    # If created_at is malformed, ignore freshness check
                    pass

                prediction = {
                    'prediction_timestamp': row[0],
                    'confidence': row[1]
                }
                return jsonify(prediction)
            else:
                return jsonify({'error': 'No prediction available'}), 404
            
    except Exception as e:
        # This can happen if the table doesn't exist yet
        if "no such table" in str(e):
            return jsonify({'error': 'No prediction available, table not found'}), 404
        logger.error(f"Error fetching next storm prediction: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/test_forecast')
def api_test_forecast():
    """Simple test forecast endpoint."""
    try:
        logger.info("Test forecast endpoint called")
        return jsonify({
            'status': 'working',
            'message': 'Forecast API is accessible',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Test forecast error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/current_threshold')
@login_required
def api_current_threshold():
    """Return current storm confidence threshold (0..1)."""
    try:
        return jsonify({'storm_confidence_threshold': config.ai.storm_confidence_threshold})
    except Exception as e:
        logger.error(f"Error getting threshold: {e}")
        return jsonify({'error': 'Could not read threshold'}), 500

@app.route('/api/set_threshold', methods=['POST'])
@login_required
def api_set_threshold():
    """Set storm confidence threshold (0..1)."""
    try:
        if not request.is_json:
            return jsonify({'error': 'Invalid request'}), 400
        value = request.json.get('storm_confidence_threshold')
        try:
            value = float(value)
        except Exception:
            return jsonify({'error': 'Threshold must be a number'}), 400
        if value < 0.0 or value > 1.0:
            return jsonify({'error': 'Threshold must be between 0 and 1'}), 400
        # Update in-memory config (scheduler holds a reference to this object)
        config.ai.storm_confidence_threshold = value
        return jsonify({'success': True, 'storm_confidence_threshold': value})
    except Exception as e:
        logger.error(f"Error setting threshold: {e}")
        return jsonify({'error': 'Failed to set threshold'}), 500

@app.route('/api/send_test_alert', methods=['POST'])
@login_required
def api_send_test_alert():
    """Send a test storm alert email to verify delivery."""
    try:
        from models import StormAnalysis, AlertLevel
        from email_notifier import EmailNotifier

        # Build dummy analysis
        analysis = StormAnalysis(
            timestamp=datetime.now(),
            confidence_score=0.95,
            storm_detected=True,
            alert_level=AlertLevel.HIGH,
            predicted_arrival=None,
            predicted_intensity='moderate',
            analysis_summary='TEST: This is a delivery verification alert from Clipron AI Weather.',
            recommendations=['Toto je testovací zpráva', 'Ověření doručení emailu'],
            data_quality_score=0.9
        )

        # Get recent weather data for context (optional)
        weather_data = db.get_recent_weather_data(hours=2)
        # Generate PDF report for the test
        pdf_path = pdf_generator.generate_storm_report(analysis, weather_data) if weather_data else None

        notifier = EmailNotifier(config)
        notification = notifier.send_storm_alert(analysis, weather_data, pdf_path)
        db.store_email_notification(notification)

        return jsonify({
            'success': notification.sent_successfully,
            'error': notification.error_message,
            'timestamp': notification.timestamp.isoformat(),
            'recipient': notification.recipient,
        }), (200 if notification.sent_successfully else 500)
    except Exception as e:
        logger.error(f"Error sending test alert: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/enhanced_forecast')
@login_required
def api_enhanced_forecast():
    """Get enhanced forecast with multiple prediction methods."""
    try:
        logger.info("Enhanced forecast endpoint called")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get latest forecasts for each method
            forecasts = {}
            for method in ['ensemble', 'physics', 'ai']:
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
                        
                        forecasts[method] = {
                            'timestamp': row[0],
                            'data': forecast_data.get('forecast_data', []),
                            'confidence': confidence_data,
                            'metadata': metadata
                        }
                    except Exception as e:
                        logger.warning(f"Error parsing {method} forecast: {e}")
                        forecasts[method] = None
                else:
                    forecasts[method] = None
            
            # Get the best available forecast
            latest_ensemble = forecasts.get('ensemble')
            latest_physics = forecasts.get('physics') 
            latest_ai = forecasts.get('ai')

            def format_forecast_data(forecast_dict, fallback_method: str):
                if not forecast_dict or not forecast_dict.get('data'):
                    return {
                        'forecast': [],
                        'method': fallback_method,
                        'confidence': 0,
                        'generated_at': datetime.now().isoformat(),
                    }
                formatted = []
                for i, item in enumerate(forecast_dict['data']):
                    formatted.append({
                        'hour': i + 1,
                        'timestamp': item.get('timestamp', ''),
                        'temperature': round(float(item.get('temperature', 0)), 1),
                        'humidity': round(float(item.get('humidity', 0)), 0),
                        'pressure': round(float(item.get('pressure', 1013)), 0),
                        'wind_speed': round(float(item.get('wind_speed', 0)), 1),
                        'precipitation': round(float(item.get('precipitation', 0)), 1),
                        'precipitation_probability': round(float(item.get('precipitation_probability', 0)), 0) if item.get('precipitation_probability') is not None else 0,
                        'condition': item.get('condition', 'clear'),
                        'cloud_cover': round(float(item.get('cloud_cover', 0)), 1),
                        'visibility': round(float(item.get('visibility', 10)), 1),
                        'description': item.get('description', ''),
                        'confidence': round(float(item.get('metadata', {}).get('confidence', 0.5)) * 100, 0),
                        'confidence_level': item.get('metadata', {}).get('confidence_level', 'unknown')
                    })
                # derive a simple confidence from available points if explicit not provided
                conf_values = [item.get('confidence', 0) for item in formatted if item.get('confidence') is not None]
                avg_conf = round(sum(conf_values) / len(conf_values), 0) if conf_values else 0
                method_name = (
                    forecast_dict.get('metadata', {}).get('primary_method') or fallback_method
                )
                return {
                    'forecast': formatted,
                    'method': method_name,
                    'confidence': avg_conf,
                    'generated_at': datetime.now().isoformat(),
                }

            ensemble_forecast = format_forecast_data(latest_ensemble, 'ensemble')
            physics_forecast = format_forecast_data(latest_physics, 'physics')
            ai_forecast = format_forecast_data(latest_ai, 'ai')

            result = {
                'ensemble': ensemble_forecast,
                'physics': physics_forecast,
                'ai': ai_forecast,
                'generated_at': datetime.now().isoformat(), # Overall generation time
                'data_points_used': max(
                    len(ensemble_forecast.get('forecast', [])),
                    len(physics_forecast.get('forecast', [])),
                    len(ai_forecast.get('forecast', [])),
                )
            }
            
            logger.info(
                f"Returning enhanced forecast data for ensemble ({len(ensemble_forecast.get('forecast', []))}), "
                f"physics ({len(physics_forecast.get('forecast', []))}), and AI ({len(ai_forecast.get('forecast', []))})"
            )
            return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting enhanced forecast: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/forecast_accuracy')
def api_forecast_accuracy():
    """Get forecast accuracy statistics."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create accuracy tracking table if it doesn't exist
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
                    created_at TEXT NOT NULL
                )
            """)
            
            # Get accuracy stats for the last 30 days
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            
            cursor.execute("""
                SELECT 
                    forecast_method,
                    parameter,
                    COUNT(*) as prediction_count,
                    AVG(error_abs) as mean_absolute_error,
                    AVG(error_relative) as mean_relative_error,
                    STDDEV(error_abs) as std_absolute_error
                FROM forecast_accuracy 
                WHERE created_at > ?
                GROUP BY forecast_method, parameter
            """, (thirty_days_ago,))
            
            accuracy_stats = {}
            for row in cursor.fetchall():
                method, param, count, mae, mre, std = row
                if method not in accuracy_stats:
                    accuracy_stats[method] = {}
                
                accuracy_stats[method][param] = {
                    'prediction_count': count,
                    'mean_absolute_error': round(mae, 2) if mae else 0,
                    'mean_relative_error': round(mre * 100, 1) if mre else 0,  # Convert to percentage
                    'std_absolute_error': round(std, 2) if std else 0,
                    'accuracy_score': max(0, 100 - (mre * 100)) if mre else 50  # Simple accuracy score
                }
            
            return jsonify({
                'accuracy_stats': accuracy_stats,
                'period_days': 30,
                'last_updated': datetime.now().isoformat()
            })
        
    except Exception as e:
        logger.error(f"Error fetching forecast accuracy: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/forecast_comparison')
def api_forecast_comparison():
    """Get side-by-side comparison of all forecast methods."""
    try:
        from storage import WeatherDatabase
        
        db = WeatherDatabase(config)
        
        # Get latest forecasts from different methods
        latest_physics = db.get_latest_forecast_by_method('physics')
        latest_ai = db.get_latest_forecast_by_method('ai')
        latest_ensemble = db.get_latest_forecast_by_method('ensemble')
        
        comparison = {
            'methods': {
                'physics': {
                    'name': 'Local Physics',
                    'description': 'Atmospheric physics and mathematical trends',
                    'icon': '🧮',
                    'color': 'warning',
                    'data': latest_physics.to_dict() if latest_physics else None
                },
                'ai': {
                    'name': 'AI Prediction',
                    'description': 'DeepSeek AI meteorological analysis',
                    'icon': '🤖',
                    'color': 'info',
                    'data': latest_ai.to_dict() if latest_ai else None
                },
                'ensemble': {
                    'name': 'Ensemble Forecast',
                    'description': 'Combined best predictions from all methods',
                    'icon': '🎯',
                    'color': 'success',
                    'data': latest_ensemble.to_dict() if latest_ensemble else None
                }
            },
            'comparison_matrix': [],
            'last_updated': datetime.now().isoformat()
        }
        
        # Create comparison matrix for each hour
        if latest_ensemble and latest_ensemble.forecast_data:
            for hour_idx, ensemble_item in enumerate(latest_ensemble.forecast_data):
                hour_data = {
                    'hour': hour_idx + 1,
                    'time': ensemble_item.timestamp.strftime('%H:%M'),
                    'ensemble': {
                        'temperature': round(ensemble_item.temperature, 1),
                        'humidity': round(ensemble_item.humidity, 0),
                        'pressure': round(ensemble_item.pressure, 0),
                        'confidence': round(ensemble_item.metadata.confidence * 100, 0)
                    }
                }
                
                # Add AI data if available
                if latest_ai and hour_idx < len(latest_ai.forecast_data):
                    ai_item = latest_ai.forecast_data[hour_idx]
                    hour_data['ai'] = {
                        'temperature': round(ai_item.temperature, 1),
                        'humidity': round(ai_item.humidity, 0),
                        'pressure': round(ai_item.pressure, 0),
                        'confidence': round(ai_item.metadata.confidence * 100, 0)
                    }
                
                # Add Physics data if available
                if latest_physics and hour_idx < len(latest_physics.forecast_data):
                    physics_item = latest_physics.forecast_data[hour_idx]
                    hour_data['physics'] = {
                        'temperature': round(physics_item.temperature, 1),
                        'humidity': round(physics_item.humidity, 0),
                        'pressure': round(physics_item.pressure, 0),
                        'confidence': round(physics_item.metadata.confidence * 100, 0)
                    }
                
                comparison['comparison_matrix'].append(hour_data)
        
        return jsonify(comparison)
        
    except Exception as e:
        logger.error(f"Error generating forecast comparison: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/system_metrics_history')
@login_required
def api_system_metrics_history():
    """Get system metrics history for charts."""
    try:
        hours = request.args.get('hours', 24, type=int)
        system_monitor = get_system_monitor(config)
        
        history = system_monitor.get_metrics_history(hours)
        summary = system_monitor.get_metrics_summary(hours)
        
        return jsonify({
            'history': history,
            'summary': summary,
            'period_hours': hours,
            'data_points': len(history)
        })
        
    except Exception as e:
        logger.error(f"Error getting system metrics history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/system_metrics_current')
@login_required
def api_system_metrics_current():
    """Get current system metrics."""
    try:
        system_monitor = get_system_monitor(config)
        current_metrics = system_monitor.get_current_metrics()
        
        return jsonify(current_metrics)
        
    except Exception as e:
        logger.error(f"Error getting current system metrics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/smtp_health_check')
@login_required
def api_smtp_health_check():
    """Perform a quick SMTP health check by attempting a login only."""
    try:
        import smtplib, ssl
        server = None
        try:
            if config.email.smtp_use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(config.email.smtp_server, config.email.smtp_port, context=context, timeout=10)
            else:
                server = smtplib.SMTP(config.email.smtp_server, config.email.smtp_port, timeout=10)
                server.starttls(context=ssl.create_default_context())
            server.login(config.email.sender_email, config.email.sender_password)
            return jsonify({'status': 'ok'})
        finally:
            try:
                if server:
                    server.quit()
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"SMTP health check failed: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/snow_summary')
@login_required
def api_snow_summary():
    """Summarize snow/frost/cold conditions from current, history, forecast, and CHMI warnings."""
    try:
        summary = {
            'current': None,
            'min_temp_24h': None,
            'forecast': None,
            'warnings': [],
            'risk_level': 'LOW'
        }

        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Latest current conditions
            cursor.execute(
                """
                SELECT timestamp, temperature, precipitation, precipitation_probability, description
                FROM weather_data ORDER BY timestamp DESC LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row:
                summary['current'] = {
                    'timestamp': row[0],
                    'temperature': row[1],
                    'precipitation': row[2],
                    'precipitation_probability': row[3],
                    'description': row[4],
                }

            # Minimum temperature in last 24 hours
            cursor.execute(
                """
                SELECT MIN(temperature) FROM weather_data
                WHERE datetime(timestamp) > datetime('now','-24 hours')
                """
            )
            tmin = cursor.fetchone()[0]
            summary['min_temp_24h'] = tmin

            # Forecast analysis (ensemble)
            cursor.execute(
                """
                SELECT forecast_data_json FROM enhanced_forecasts
                WHERE method = 'ensemble' ORDER BY timestamp DESC LIMIT 1
                """
            )
            row = cursor.fetchone()
            snow_risk_hours = 0
            first_freeze_time = None
            subzero_hours = 0
            if row:
                try:
                    fdata = json.loads(row[0])
                    items = fdata.get('forecast_data', [])
                    for item in items[:12]:  # next ~12 hours
                        temp = float(item.get('temperature', 100))
                        precip = float(item.get('precipitation', 0) or 0)
                        pprob = float(item.get('precipitation_probability', 0) or 0)
                        ts = item.get('timestamp')
                        if temp <= 0.0:
                            subzero_hours += 1
                            if not first_freeze_time and ts:
                                first_freeze_time = ts
                        # simple snow risk heuristic: cold and precip present or high prob
                        if temp <= 1.0 and (precip > 0.0 or pprob >= 60.0):
                            snow_risk_hours += 1
                    summary['forecast'] = {
                        'subzero_hours': subzero_hours,
                        'snow_risk_hours': snow_risk_hours,
                        'first_freeze_time': first_freeze_time
                    }
                except Exception as e:
                    logger.warning(f"Error parsing ensemble forecast for snow summary: {e}")

        # CHMI warnings filtering for snow/frost/ice
        try:
            from chmi_warnings import ChmiWarningMonitor
            chmi_monitor = ChmiWarningMonitor(config)
            warnings = chmi_monitor.get_all_active_warnings()
            snow_keywords = ['sníh', 'led', 'náledí', 'mráz', 'namrzání', 'ice', 'snow', 'frost', 'freezing']
            snow_warnings = []
            for w in warnings:
                text = (getattr(w, 'event', '') + ' ' + getattr(w, 'description_text', '')).lower()
                if any(k in text for k in snow_keywords):
                    snow_warnings.append({
                        'event': getattr(w, 'event', ''),
                        'color': getattr(w, 'color', ''),
                        'time_start': getattr(w, 'time_start_iso', None),
                        'time_end': getattr(w, 'time_end_iso', None),
                    })
            summary['warnings'] = snow_warnings
        except Exception as e:
            logger.warning(f"CHMI snow warnings unavailable: {e}")

        # Risk assessment
        risk = 'LOW'
        colors = {w['color'] for w in summary['warnings']}
        if 'red' in colors or 'orange' in colors:
            risk = 'HIGH'
        elif summary.get('forecast') and (summary['forecast'].get('snow_risk_hours', 0) >= 2 or summary['forecast'].get('subzero_hours', 0) >= 4):
            risk = 'MEDIUM'
        elif tmin is not None and tmin <= -3:
            risk = 'MEDIUM'
        summary['risk_level'] = risk

        return jsonify(summary)
    except Exception as e:
        logger.error(f"Error building snow summary: {e}")
        return jsonify({'error': 'Failed to build snow summary'}), 500

@app.route('/api/weather_processes')
@login_required
def api_weather_processes():
    """Get running weather-related processes."""
    try:
        system_monitor = get_system_monitor(config)
        processes = system_monitor.check_weather_processes()
        return jsonify(processes)
    except Exception as e:
        logger.error(f"Error getting weather processes: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/log_stats')
@login_required
def api_log_stats():
    """Get log file statistics."""
    try:
        log_rotator = get_log_rotator(config)
        stats = log_rotator.get_log_stats()
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting log stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/database_health')
@login_required
def api_database_health():
    """Get database health and optimization status."""
    try:
        db_optimizer = get_database_optimizer(config)
        health = db_optimizer.check_database_health()
        table_stats = db_optimizer.get_table_stats()
        index_info = db_optimizer.get_index_usage()
        
        return jsonify({
            'health': health,
            'table_stats': table_stats,
            'index_info': index_info
        })
        
    except Exception as e:
        logger.error(f"Error getting database health: {e}")
        return jsonify({'error': 'Database inaccessible'}), 500

@app.route('/api/optimize_database', methods=['POST'])
@login_required
def api_optimize_database():
    """Trigger database optimization."""
    try:
        full_optimization = request.json.get('full', False) if request.is_json else False
        
        db_optimizer = get_database_optimizer(config)
        results = db_optimizer.optimize_database(full_optimization)
        
        return jsonify({
            'success': True,
            'results': results,
            'full_optimization': full_optimization
        })
        
    except Exception as e:
        logger.error(f"Error optimizing database: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/force_log_rotation', methods=['POST'])
@login_required
def api_force_log_rotation():
    """Force log rotation."""
    try:
        log_rotator = get_log_rotator(config)
        log_rotator.force_rotation()
        
        return jsonify({
            'success': True,
            'message': 'Log rotation completed'
        })
        
    except Exception as e:
        logger.error(f"Error forcing log rotation: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    Path('templates').mkdir(exist_ok=True)
    
    # Start system monitoring
    # start system monitoring with proper config
    start_system_monitoring(config, interval=60)
    logger.info("System monitoring started")
    # Start Telegram getUpdates poller (no webhook needed)
    try:
        if getattr(config, 'telegram', None) and config.telegram.enabled:
            start_telegram_polling(config)
            logger.info("Telegram polling enabled")
        else:
            logger.info("Telegram polling disabled (config)")
    except Exception as e:
        logger.warning(f"Failed to start Telegram polling: {e}")
    
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context=('cert.pem', 'key.pem'))
