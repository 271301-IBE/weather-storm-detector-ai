# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

This is a comprehensive weather storm detection system for Czech Republic (specifically Brno/Reckovice area) that combines multiple weather APIs with AI analysis to provide intelligent storm alerts. The system runs continuously on Raspberry Pi and sends email notifications for high-confidence storm predictions.

## Core Architecture

The system follows a modular architecture with these key components:

- **WeatherMonitoringScheduler** (`scheduler.py`) - Main orchestrator that runs monitoring cycles every 10 minutes
- **WeatherDataCollector** (`data_fetcher.py`) - Fetches real-time data from OpenWeather and Visual Crossing APIs
- **StormDetectionEngine** (`ai_analysis.py`) - Uses DeepSeek AI for storm analysis with smart caching to prevent duplicate analysis
- **ChmiWarningMonitor** (`chmi_warnings.py`) - Monitors official Czech weather warnings
- **EmailNotifier** (`email_notifier.py`) - Sends storm alerts and daily summaries via Seznam.cz SMTP
- **WeatherDatabase** (`storage.py`) - SQLite database for weather data, analysis results, and email logs
- **PDFGenerator** (`pdf_generator.py`) - Creates detailed weather reports

## Essential Commands

### System Management
```bash
# Start the system
./start.sh

# Stop the system  
./stop.sh

# Update dependencies
./update.sh

# Setup from scratch
./setup.sh
```

### Development & Testing
```bash
# Activate virtual environment
source weather_env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run system tests
python3 test_system.py
python3 test_combined_system.py
python3 test_chmi_integration.py

# Test individual components
python3 test_emails.py
```

### Service Management (Linux)
```bash
# Start as systemd service
sudo systemctl start weather-monitor

# Check service status
sudo systemctl status weather-monitor

# View service logs
sudo journalctl -u weather-monitor -f
```

## Configuration

The system uses `.env` file for configuration with these critical settings:

- **API Keys**: OPENWEATHER_API_KEY, VISUAL_CROSSING_API_KEY, DEEPSEEK_API_KEY
- **Location**: LATITUDE, LONGITUDE, CITY_NAME, REGION  
- **Email**: SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL
- **Thresholds**: STORM_CONFIDENCE_THRESHOLD (0.99 = 99% confidence required)
- **Timing**: MONITORING_INTERVAL_MINUTES (10), EMAIL_DELAY_MINUTES (30)

Configuration is loaded via `config.py` which uses dataclasses for type safety.

## Key Design Patterns

### Smart Caching System
The scheduler implements sophisticated caching to prevent redundant AI analysis:
- **Warning Cache**: Prevents re-analyzing same ČHMÚ warnings within 6 hours
- **Weather Condition Cache**: Groups similar weather conditions (wind speed ranges, etc.) to avoid repeated analysis within 1 hour
- **Date Filtering**: Only analyzes ČHMÚ warnings within next 24 hours, skips far-future warnings

### AI Trigger Logic
AI analysis is triggered only when cost-effective:
- High precipitation probability (>60%)
- Active precipitation (>1.0mm)
- Storm conditions (humidity >80% + pressure <1010 hPa)
- Very high wind speeds (>17 m/s gale force)
- Stormy keywords in weather descriptions
- ČHMÚ storm warnings for next 24 hours
- Periodic check if no analysis for >1 hour

### Error Handling
- Retry logic with exponential backoff for API calls
- AsyncIO cancellation handling for graceful shutdown
- DNS resolution fallbacks and caching
- Comprehensive logging for debugging

## Data Models

Core data structures in `models.py`:
- **WeatherData**: Raw API data with timestamp, source, and meteorological measurements
- **StormAnalysis**: AI analysis results with confidence scores and predictions  
- **ChmiWarning**: Official Czech weather warnings with time windows and severity
- **EmailNotification**: Email delivery tracking with success/failure logging

## Database Schema

SQLite database with automatic cleanup:
- `weather_data` - Raw measurements (30-day retention)
- `storm_analysis` - AI predictions (90-day retention) 
- `email_notifications` - Delivery logs (30-day retention)
- Cleanup runs daily at 2:00 AM

## Development Notes

### When Modifying AI Analysis
- The `ai_analysis.py` uses DeepSeek Chat API (not Reasoner model) for JSON responses
- JSON parsing has multiple fallback strategies (markdown blocks, brace extraction, line-by-line)
- Always handle `asyncio.CancelledError` for graceful shutdowns
- Update cache keys when changing trigger conditions

### When Working with ČHMÚ Integration
- ČHMÚ warnings use specific region codes (6203 for Brno) based on CISORP codes
- Warning parsing follows official CAP v1.2 specification for Czech Republic
- Storm-related warning types: Thunderstorm, Rain, Wind, flooding, rain-flood
- Warning severity levels: Minor (green), Moderate (yellow), Severe (orange), Extreme (red)
- Only yellow/orange/red warnings trigger AI analysis (ignoring green/informational)
- Czech keyword detection for storm events: 'bouř', 'déšť', 'vichr', 'povodeň', 'vítr'
- Time zones and date formats follow ISO 8601 with proper timezone handling
- Warning states are tracked to detect new vs. existing warnings with hash comparison

### Email System
- Uses Seznam.cz SMTP (Czech email provider) with SSL on port 465
- HTML email templates in `sample_emails/` directory
- Rate limiting prevents spam (30-minute delays between storm alerts)
- Supports both storm alerts and daily summaries

### Testing Strategy
- `test_system.py` - Basic functionality tests
- `test_combined_system.py` - Integration tests
- `test_chmi_integration.py` - ČHMÚ API validation
- `test_emails.py` - Email delivery verification

### Raspberry Pi Optimization
- Virtual environment in `weather_env/`
- Systemd service for auto-start
- Log rotation and database cleanup
- Memory-efficient async operations
- DNS caching to handle intermittent connectivity

## Debugging Common Issues

### AI Analysis Not Triggering
Check cache status and trigger conditions in logs. Wind speed threshold is 17 m/s (gale force), not lower values.

### JSON Parsing Errors
DeepSeek responses should use Chat model, not Reasoner. JSON extraction has multiple fallback methods.

### Email Delivery Failures
Verify Seznam.cz SMTP credentials and network connectivity. Check for rate limiting.

### High CPU Usage
Monitor AI analysis frequency and cache effectiveness. Adjust trigger thresholds if needed.

### Database Issues
Ensure sufficient disk space and proper SQLite permissions. Check cleanup schedule.