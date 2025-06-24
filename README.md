# Weather Storm Detection System

A comprehensive weather monitoring and storm detection system for Czech Republic, specifically designed for the Brno/Reckovice area in South Moravia.

## Features

- **Real-time Weather Monitoring**: Fetches data every 10 minutes from multiple APIs
- **AI-Powered Storm Detection**: Uses DeepSeek AI for high-accuracy thunderstorm prediction
- **Smart Email Alerts**: Sends notifications only for high-confidence storm detections (99%+)
- **Detailed PDF Reports**: Generates comprehensive weather analysis reports
- **Daily Weather Summary**: Automatic morning summary at 9:00 AM
- **Long-term Data Storage**: SQLite database for historical weather data
- **Raspberry Pi Optimized**: Designed for continuous operation on Raspberry Pi

## System Requirements

- Python 3.8+
- Internet connection for API access
- Email account (Seznam.cz SMTP configured)
- 500MB+ free disk space for reports and database

## Installation

1. **Clone and setup the project:**
   ```bash
   cd /home/patrik/Documents/weather-storm-detector
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**
   Edit `.env` file with your API keys and settings:
   ```env
   OPENWEATHER_API_KEY=your_openweather_key
   VISUAL_CROSSING_API_KEY=your_visual_crossing_key
   DEEPSEEK_API_KEY=your_deepseek_key
   SENDER_EMAIL=your_email@seznam.cz
   SENDER_PASSWORD=your_password
   RECIPIENT_EMAIL=recipient@email.com
   ```

3. **Test the system:**
   ```bash
   python main.py
   ```

## Usage

### Starting the System

```bash
python main.py
```

The system will:
- Start continuous monitoring every 10 minutes
- Send daily summary emails at 9:00 AM
- Alert via email when storms are detected with 99%+ confidence
- Maintain 30-minute minimum delay between storm alerts
- Generate detailed PDF reports for each storm detection

### Manual Testing

To test individual components:

```python
from config import load_config
from data_fetcher import WeatherDataCollector
import asyncio

config = load_config()
collector = WeatherDataCollector(config)
weather_data = asyncio.run(collector.collect_weather_data())
print(f"Collected {len(weather_data)} data points")
```

## Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENWEATHER_API_KEY` | OpenWeather API key | `abc123...` |
| `VISUAL_CROSSING_API_KEY` | Visual Crossing API key | `xyz789...` |
| `DEEPSEEK_API_KEY` | DeepSeek AI API key | `sk-...` |
| `LATITUDE` | Location latitude | `49.2384` |
| `LONGITUDE` | Location longitude | `16.6073` |
| `STORM_CONFIDENCE_THRESHOLD` | Minimum confidence for alerts | `0.99` |
| `EMAIL_DELAY_MINUTES` | Delay between storm emails | `30` |
| `MONITORING_INTERVAL_MINUTES` | Data collection interval | `10` |

### Email Configuration

The system uses Seznam.cz SMTP with the following settings:
- **Server**: smtp.seznam.cz
- **Port**: 465 (SSL) or 587 (STARTTLS)
- **Authentication**: Required

## System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Weather APIs  │    │  DeepSeek AI     │    │  Email Service  │
│                 │    │  Analysis        │    │  (Seznam.cz)    │
│ • OpenWeather   │    │                  │    │                 │
│ • Visual Cross. │    │ • Storm Detection│    │ • Alerts        │
└─────────┬───────┘    └─────────┬────────┘    │ • Daily Summary │
          │                      │             └─────────────────┘
          ▼                      ▼                       ▲
┌─────────────────────────────────────────────────────────┼─────┐
│                 Main Scheduler                          │     │
│                                                         │     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐   │     │
│  │Data Fetcher │  │AI Analyzer   │  │PDF Generator│   │     │
│  └─────────────┘  └──────────────┘  └─────────────┘   │     │
│                                                         │     │
│  ┌─────────────────────────────────────────────────────┤     │
│  │            SQLite Database                          │     │
│  │  • Weather Data    • Storm Analysis                │     │
│  │  • Email Logs      • System Status                 │     │
│  └─────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────┘
```

## Storm Detection Logic

The system uses a multi-step approach for storm detection:

1. **Data Collection**: Gathers current weather conditions from multiple APIs
2. **AI Analysis**: DeepSeek AI analyzes meteorological patterns and trends
3. **Confidence Scoring**: Only predictions with 99%+ confidence trigger alerts
4. **Validation**: Cross-references multiple data sources for accuracy
5. **Alert Decision**: Considers recent alert history and timing constraints

### Detection Criteria

The AI considers:
- Rapid atmospheric pressure changes
- Wind speed and direction shifts
- Humidity and precipitation patterns
- Regional Czech weather patterns
- Historical storm behavior

## Email Notifications

### Storm Alerts
- **Trigger**: 99%+ confidence storm detection
- **Frequency**: Maximum one per 30 minutes
- **Content**: Detailed analysis, timing, intensity, recommendations
- **Language**: Czech (targeted for local users)

### Daily Summary
- **Schedule**: Every day at 9:00 AM
- **Content**: Current conditions, 24-hour summary, system status
- **Format**: HTML email with weather data tables

## PDF Reports

Detailed reports include:
- Storm analysis summary
- Weather condition trends
- Data quality assessment  
- Meteorological charts
- AI reasoning and recommendations

Reports are saved in `./reports/` directory and attached to storm alert emails.

## Database Schema

### Tables

- `weather_data`: Raw weather measurements from APIs
- `storm_analysis`: AI analysis results and predictions
- `email_notifications`: Email delivery logs and status
- `system_status`: System health and performance metrics

### Data Retention

- Weather data: 30 days
- Storm analysis: 90 days
- Email logs: 30 days
- Automatic cleanup daily at 2:00 AM

## Raspberry Pi Deployment

### Setup for Continuous Operation

1. **Install as systemd service:**
   ```bash
   sudo cp weather-monitor.service /etc/systemd/system/
   sudo systemctl enable weather-monitor
   sudo systemctl start weather-monitor
   ```

2. **Monitor logs:**
   ```bash
   sudo journalctl -u weather-monitor -f
   ```

3. **Resource optimization:**
   - System uses approximately 50-100MB RAM
   - Database grows ~10MB per month
   - PDF reports: ~500KB each

### Performance Monitoring

The system logs performance metrics:
- API response times
- Analysis duration
- Database query performance
- Email delivery success rates

## Troubleshooting

### Common Issues

**API Connection Errors:**
- Check internet connection
- Verify API keys in `.env` file
- Monitor API rate limits

**Email Delivery Issues:**
- Verify Seznam.cz SMTP credentials
- Check firewall settings for SMTP ports
- Test with alternative SMTP port (587 vs 465)

**High CPU Usage:**
- Monitor DeepSeek AI analysis duration
- Consider reducing monitoring frequency
- Check for memory leaks in long-running processes

**Database Errors:**
- Ensure sufficient disk space
- Check file permissions for SQLite database
- Monitor database size and cleanup schedule

### Log Files

- `weather_monitor.log`: Main system log
- `./reports/`: PDF reports directory
- Database: `weather_data.db`

## API Documentation

### OpenWeather API
- **Endpoint**: `https://api.openweathermap.org/data/2.5/weather`
- **Rate Limit**: 60 calls/minute, 1,000,000 calls/month
- **Documentation**: https://openweathermap.org/api

### Visual Crossing Weather API
- **Endpoint**: `https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline`
- **Rate Limit**: 1000 calls/day (free tier)
- **Documentation**: https://www.visualcrossing.com/weather-api

### DeepSeek AI API
- **Endpoint**: `https://api.deepseek.com/v1/chat/completions`
- **Model**: `deepseek-reasoner`
- **Documentation**: https://api-docs.deepseek.com/

## License

This project is developed by Clipron AI for weather monitoring purposes.

## Support

For technical issues or questions, check:
1. System logs in `weather_monitor.log`
2. Database integrity with manual queries
3. API connectivity and response formats
4. Email SMTP configuration and authentication

## Version History

- **v1.0.0**: Initial release with core storm detection functionality
- Multi-API weather data collection
- DeepSeek AI integration
- Email alert system
- PDF report generation
- Raspberry Pi optimization