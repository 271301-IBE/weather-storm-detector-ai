#!/usr/bin/env python3
"""
Weather Storm Detection System - Web Interface
Simple web dashboard for monitoring weather data, AI analysis, and system status.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from functools import wraps
import logging
from pathlib import Path
import os
import time

from config import load_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load configuration
config = load_config()
app.secret_key = config.webapp.secret_key

# Simple authentication
USERNAME = config.webapp.username
PASSWORD = config.webapp.password

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_db_connection():
    """Get database connection."""
    return sqlite3.connect('./weather_data.db')

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

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    """Main dashboard page."""
    return render_template('dashboard.html')

@app.route('/api/current_weather')
@login_required
def api_current_weather():
    """Get current weather data."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get latest weather data from all three sources
        cursor.execute("""
            SELECT * FROM weather_data 
            ORDER BY created_at DESC 
            LIMIT 3
        """
)
        
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        
        weather_data = []
        for row in rows:
            data = dict(zip(columns, row))
            weather_data.append(data)
        
        conn.close()
        return jsonify(weather_data)
        
    except Exception as e:
        logger.error(f"Error fetching current weather: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recent_analysis')
@login_required
def api_recent_analysis():
    """Get recent AI analysis results."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM storm_analysis 
            ORDER BY timestamp DESC 
            LIMIT 10
        """
)
        
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
        
        conn.close()
        return jsonify(analysis_data)
        
    except Exception as e:
        logger.error(f"Error fetching analysis data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/weather_history')
@login_required
def api_weather_history():
    """Get weather history for charts."""
    try:
        hours = request.args.get('hours', 24, type=int)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
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
        
        conn.close()
        return jsonify(history_data)
        
    except Exception as e:
        logger.error(f"Error fetching weather history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/system_stats')
@login_required
def api_system_stats():
    """Get system statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Weather data count (last 24h)
        cursor.execute("""
            SELECT COUNT(*) FROM weather_data 
            WHERE datetime(timestamp) > datetime('now', '-24 hours')
        """
)
        stats['weather_data_24h'] = cursor.fetchone()[0]
        
        # AI analysis count (last 24h)
        cursor.execute("""
            SELECT COUNT(*) FROM storm_analysis 
            WHERE datetime(timestamp) > datetime('now', '-24 hours')
        """
)
        stats['ai_analysis_24h'] = cursor.fetchone()[0]
        
        # Email notifications count (last 24h)
        cursor.execute("""
            SELECT COUNT(*) FROM email_notifications 
            WHERE datetime(timestamp) > datetime('now', '-24 hours')
        """
)
        stats['emails_24h'] = cursor.fetchone()[0]
        
        # Storm detections (last 7 days)
        cursor.execute("""
            SELECT COUNT(*) FROM storm_analysis 
            WHERE datetime(timestamp) > datetime('now', '-7 days')
            AND storm_detected = 1
        """
)
        stats['storms_detected_7d'] = cursor.fetchone()[0]
        
        # High confidence predictions (last 7 days)
        cursor.execute("""
            SELECT COUNT(*) FROM storm_analysis 
            WHERE datetime(timestamp) > datetime('now', '-7 days')
            AND confidence_score > 0.8
        """
)
        stats['high_confidence_7d'] = cursor.fetchone()[0]
        
        # Average confidence score (last 7 days)
        cursor.execute("""
            SELECT AVG(confidence_score) FROM storm_analysis 
            WHERE datetime(timestamp) > datetime('now', '-7 days')
        """
)
        avg_confidence = cursor.fetchone()[0]
        stats['avg_confidence_7d'] = round(avg_confidence * 100, 1) if avg_confidence else 0
        
        # Cache efficiency
        cursor.execute("""
            SELECT COUNT(*) FROM weather_condition_cache 
            WHERE expires_at > datetime('now')
        """
)
        stats['active_cache_entries'] = cursor.fetchone()[0]
        
        # Database size estimation
        cursor.execute("SELECT COUNT(*) FROM weather_data")
        stats['total_weather_records'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM storm_analysis")
        stats['total_analysis_records'] = cursor.fetchone()[0]
        
        conn.close()
        
        # Estimate API costs (rough calculation)
        # DeepSeek: ~$0.001 per analysis
        # Weather APIs: free tier usage
        stats['estimated_ai_cost_24h'] = round(stats['ai_analysis_24h'] * 0.001, 3)
        stats['estimated_ai_cost_7d'] = round(stats['ai_analysis_24h'] * 7 * 0.001, 2)
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error fetching system stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/email_history')
@login_required
def api_email_history():
    """Get email notification history."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, recipient, subject, message_type, sent_successfully, error_message
            FROM email_notifications 
            ORDER BY timestamp DESC 
            LIMIT 20
        """
)
        
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        
        email_data = []
        for row in rows:
            data = dict(zip(columns, row))
            email_data.append(data)
        
        conn.close()
        return jsonify(email_data)
        
    except Exception as e:
        logger.error(f"Error fetching email history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/api_usage_stats')
@login_required
def api_usage_stats():
    """Get API usage statistics for all weather sources."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # API call counts by source (last 24 hours)
        cursor.execute("""
            SELECT source, COUNT(*) as call_count
            FROM weather_data 
            WHERE datetime(timestamp) > datetime('now', '-24 hours')
            GROUP BY source
            ORDER BY call_count DESC
        """
)
        
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
        """
)
        
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
        """
)
        
        api_usage_total = {}
        rows = cursor.fetchall()
        for source, count in rows:
            api_usage_total[source] = count
        
        # Latest data timestamp for each API
        cursor.execute("""
            SELECT source, MAX(timestamp) as last_update
            FROM weather_data 
            GROUP BY source
        """
)
        
        api_last_update = {}
        rows = cursor.fetchall()
        for source, timestamp in rows:
            api_last_update[source] = timestamp
            
        conn.close()
        
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
        conn = get_db_connection()
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
        """
)
        
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
            
        conn.close()
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
        # Filter out Praha and keep only Jihomoravský kraj warnings
        warnings = [w for w in all_warnings if 'jihomoravský' in (getattr(w, 'area_description', '') or '').lower() or 
                   'brno' in (getattr(w, 'area_description', '') or '').lower()] if all_warnings else []
        
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

@app.route('/api/live_logs')
@login_required
def live_logs():
    def generate():
        log_file_path = 'weather_monitor.log'
        if not os.path.exists(log_file_path):
            yield "Log file not found."
            return

        # Initial read of the last few lines
        try:
            with open(log_file_path, 'r') as f:
                # Seek to the end and read backwards to get the last N lines
                f.seek(0, os.SEEK_END)
                buffer_size = 4096
                f.seek(max(0, f.tell() - buffer_size), os.SEEK_SET)
                lines = f.readlines()
                # Get the last 50 lines
                for line in lines[-50:]:
                    yield f"data: {line.strip()}\n\n"
        except Exception as e:
            yield f"data: Error reading log file: {e}\n\n"
            return

        # Stream new lines
        with open(log_file_path, 'r') as f:
            f.seek(0, os.SEEK_END) # Move to the end of the file
            while True:
                line = f.readline()
                if not line:
                    # No new line, wait a bit
                    time.sleep(1)
                    continue
                yield f"data: {line.strip()}\n\n"

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    Path('templates').mkdir(exist_ok=True)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
