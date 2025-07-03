"""Scheduling system for weather monitoring tasks."""

import asyncio
import logging
import signal
import sys
from datetime import datetime, time, timedelta
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import json
import os

from config import Config, load_config
from data_fetcher import WeatherDataCollector
from ai_analysis import StormDetectionEngine, LocalForecastGenerator, DeepSeekPredictor, DeepSeekPredictor
from email_notifier import EmailNotifier
from web_notifier import WebNotifier
from pdf_generator import WeatherReportGenerator
from storage import WeatherDatabase
from models import EmailNotification, WeatherForecast
from chmi_warnings import ChmiWarningMonitor
from lightning_monitor import LightningMonitor, LightningStrike

logger = logging.getLogger(__name__)

class WeatherMonitoringScheduler:
    """Main scheduler for weather monitoring system."""
    
    def __init__(self, config: Config):
        """Initialize scheduler with configuration."""
        self.config = config
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        
        # Initialize components
        self.data_collector = WeatherDataCollector(config)
        self.storm_engine = StormDetectionEngine(config)
        self.deepseek_predictor = DeepSeekPredictor(config)
        self.email_notifier = EmailNotifier(config)
        self.web_notifier = WebNotifier(config)
        self.pdf_generator = WeatherReportGenerator(config)
        self.database = WeatherDatabase(config)
        self.chmi_monitor = ChmiWarningMonitor(config)
        self.lightning_monitor = LightningMonitor(config, self.database, self._on_lightning_strike)
        
        # Warning analysis cache to prevent duplicate AI analysis
        self._warning_analysis_cache = {}  # {warning_key: analysis_timestamp}
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(self.stop())
    
    def _on_lightning_strike(self, strike: LightningStrike):
        """Callback for lightning strikes - triggers immediate analysis if nearby."""
        try:
            if strike.distance_from_brno <= 30:  # Within 30km
                logger.warning(f"Lightning strike detected {strike.distance_from_brno:.1f}km from Brno - triggering immediate analysis")
                # Create async task for immediate analysis
                asyncio.create_task(self._handle_nearby_lightning(strike))
            elif strike.is_in_czech_region:
                logger.info(f"Lightning strike in Czech region: {strike.distance_from_brno:.1f}km from Brno")
        except Exception as e:
            logger.error(f"Error in lightning strike callback: {e}")
    
    async def _handle_nearby_lightning(self, strike: LightningStrike):
        """Handle nearby lightning strike with immediate storm analysis."""
        try:
            logger.info(f"Processing immediate analysis for lightning at {strike.distance_from_brno:.1f}km")
            
            # Get recent weather data
            weather_data = self.database.get_recent_weather_data(hours=2)
            if not weather_data:
                logger.warning("No recent weather data for lightning analysis")
                return
            
            # Get lightning activity for the analysis
            lightning_activity = self.lightning_monitor.get_recent_lightning_activity(hours=1)
            
            # Get ČHMÚ warnings
            chmi_warnings = self.chmi_monitor.get_storm_warnings()
            
            # Run immediate AI analysis with lightning data
            analysis = await self.storm_engine.analyze_storm_potential(
                weather_data, chmi_warnings, lightning_activity
            )
            
            if analysis:
                # Store analysis
                self.database.store_storm_analysis(analysis)
                
                # Send immediate alert if confidence is high
                if analysis.confidence_score >= self.config.ai.storm_confidence_threshold:
                    logger.warning(f"HIGH CONFIDENCE storm detected due to lightning activity: {analysis.confidence_score:.3f}")
                    
                    # Check if we should send alert (rate limiting)
                    last_alert_time = self.database.get_last_storm_alert()
                    if not last_alert_time or (datetime.now() - last_alert_time).total_seconds() > 1800:  # 30 min
                        await self._send_lightning_alert(analysis, strike)
                    else:
                        logger.info("Skipping lightning alert due to rate limiting")
                        
        except Exception as e:
            logger.error(f"Error handling nearby lightning: {e}")
    
    async def _send_lightning_alert(self, analysis, strike: LightningStrike):
        """Send specialized lightning-based storm alert."""
        try:
            subject = f"⚡ IMMEDIATE STORM ALERT - Lightning {strike.distance_from_brno:.1f}km from Brno"
            
            message = f"""
            🚨 IMMEDIATE THUNDERSTORM ALERT 🚨
            
            Lightning strike detected at {strike.distance_from_brno:.1f} kilometers from Brno!
            
            ⚡ Lightning Location: {strike.latitude:.4f}°N, {strike.longitude:.4f}°E
            ⏰ Strike Time: {strike.timestamp.strftime('%H:%M:%S')}
            🎯 Confidence: {analysis.confidence_score:.1%}
            📊 Alert Level: {analysis.alert_level.value.upper()}
            
            {analysis.analysis_summary}
            
            IMMEDIATE RECOMMENDATIONS:
            """
            
            for rec in analysis.recommendations:
                message += f"• {rec}\n"
            
            message += f"""
            
            This alert was triggered by REAL-TIME lightning detection.
            Take shelter immediately if outdoors.
            
            Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            # Send email alert
            await self.email_notifier.send_storm_alert(
                self.config.email.recipient_email,
                subject,
                message,
                "lightning_storm_alert"
            )
            
            logger.info("Lightning-triggered storm alert sent successfully")
            
        except Exception as e:
            logger.error(f"Error sending lightning alert: {e}")
    
    async def monitoring_cycle(self):
        """Execute one complete monitoring cycle."""
        cycle_start = datetime.now()
        logger.info(f"Starting monitoring cycle at {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # 1. Collect weather data
            weather_data = await self.data_collector.collect_weather_data()
            
            if not weather_data:
                logger.warning("No weather data collected, skipping analysis")
                return
            
            # 2. Store weather data
            for data in weather_data:
                self.database.store_weather_data(data)
            
            # 3. Generate and store 6-hour forecast
            # This is now handled by separate scheduled jobs (local and DeepSeek)

            # 4. Get ČHMÚ warnings for analysis (focus on storm-related warnings)
            chmi_warnings = self.chmi_monitor.get_storm_warnings()
            
            # 5. Decide if AI analysis is needed (save costs)
            should_run_ai = self._should_run_ai_analysis(weather_data, chmi_warnings)
            
            analysis = None
            if should_run_ai:
                logger.info("Running AI analysis - conditions indicate potential storm activity")
                # Get recent lightning activity for analysis
                lightning_activity = self.lightning_monitor.get_recent_lightning_activity(hours=2)
                analysis = await self.storm_engine.analyze_storm_potential(weather_data, chmi_warnings, lightning_activity)
            else:
                logger.debug("Skipping AI analysis - conditions normal")
            
            if analysis:
                # 6. Store analysis results
                self.database.store_storm_analysis(analysis)
                
                # 7. Check if combined storm alert should be sent
                if self.storm_engine.should_send_alert(analysis):
                    last_alert_time = self.database.get_last_storm_alert()
                    
                    if self.email_notifier.can_send_storm_alert(last_alert_time):
                        # Generate PDF report
                        pdf_path = self.pdf_generator.generate_storm_report(
                            analysis, weather_data
                        )
                        
                        # Send combined weather alert email (AI + ČHMÚ)
                        notification = self.email_notifier.send_combined_weather_alert(
                            analysis, weather_data, chmi_warnings, pdf_path
                        )
                        self.database.store_email_notification(notification)
                        
                        if notification.sent_successfully:
                            logger.warning(f"COMBINED WEATHER ALERT SENT: AI Confidence {analysis.confidence_score:.1%}, ČHMÚ warnings: {len(chmi_warnings)}")
                            # Send web push notifications
                            if os.path.exists('subscriptions.json'):
                                with open('subscriptions.json', 'r') as f:
                                    subscriptions = json.load(f)
                                for sub in subscriptions:
                                    self.web_notifier.send_notification(sub, analysis)
                        else:
                            logger.error(f"Failed to send combined weather alert: {notification.error_message}")
                    else:
                        logger.info("Storm detected but email delay period not elapsed")
                
            cycle_duration = (datetime.now() - cycle_start).total_seconds()
            logger.info(f"Monitoring cycle completed in {cycle_duration:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}", exc_info=True)
    
    # ODSTRANĚNO: Denní souhrny - uživatel je zakázal
    # "Asi se vyser na denni emaily. Je to zbytečný. Stačí jen extremní výstrahy a bouřky a deště nad Brnem."
    
    async def cleanup_task(self):
        """Perform database cleanup and maintenance."""
        logger.info("Executing cleanup task")
        
        try:
            # Clean up old data (keep 30 days of regular data, 90 days of analysis)
            self.database.cleanup_old_data(days_to_keep=30)
            # Clean up expired weather condition cache entries
            self.database.cleanup_weather_condition_cache()
            logger.info("Database cleanup completed")
            
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}", exc_info=True)
    
    async def chmi_warning_check(self):
        """Check for new standalone ČHMÚ warnings (separate from storm alerts)."""
        logger.info("Checking for standalone ČHMÚ warnings")
        
        try:
            # Check for new warnings that aren't part of storm analysis
            new_warnings = self.chmi_monitor.check_for_new_warnings()
            
            if new_warnings:
                logger.info(f"Found {len(new_warnings)} new ČHMÚ warning(s)")
                
                # Only send standalone ČHMÚ email if no recent storm alert was sent
                last_alert_time = self.database.get_last_storm_alert()
                recent_storm_alert = (
                    last_alert_time and 
                    (datetime.now() - last_alert_time).total_seconds() < 3600  # Within last hour
                )
                
                if not recent_storm_alert:
                    # Send standalone ČHMÚ notification email
                    notification = self.email_notifier.send_chmi_warning(new_warnings)
                    
                    if notification.sent_successfully:
                        logger.warning(f"STANDALONE ČHMÚ WARNING EMAIL SENT: {len(new_warnings)} warning(s) for {self.config.weather.city_name}")
                        
                        # Log each warning
                        for warning in new_warnings:
                            logger.info(f"  - {warning.event} ({warning.color}) - {warning.time_start_text}")
                    else:
                        logger.error(f"Failed to send ČHMÚ warning email: {notification.error_message}")
                else:
                    logger.info("New ČHMÚ warnings detected but recent storm alert already sent - skipping standalone email")
            else:
                logger.debug("No new ČHMÚ warnings detected")
                
        except Exception as e:
            logger.error(f"Error checking ČHMÚ warnings: {e}", exc_info=True)
    
    async def chmi_warning_check(self):
        """Check for new standalone ČHMÚ warnings (separate from storm alerts)."""
        logger.info("Checking for standalone ČHMÚ warnings")
        
        try:
            # Check for new warnings that aren't part of storm analysis
            new_warnings = self.chmi_monitor.check_for_new_warnings()
            
            if new_warnings:
                logger.info(f"Found {len(new_warnings)} new ČHMÚ warning(s)")
                
                # Only send standalone ČHMÚ email if no recent storm alert was sent
                last_alert_time = self.database.get_last_storm_alert()
                recent_storm_alert = (
                    last_alert_time and 
                    (datetime.now() - last_alert_time).total_seconds() < 3600  # Within last hour
                )
                
                if not recent_storm_alert:
                    # Send standalone ČHMÚ notification email
                    notification = self.email_notifier.send_chmi_warning(new_warnings)
                    
                    if notification.sent_successfully:
                        logger.warning(f"STANDALONE ČHMÚ WARNING EMAIL SENT: {len(new_warnings)} warning(s) for {self.config.weather.city_name}")
                        
                        # Log each warning
                        for warning in new_warnings:
                            logger.info(f"  - {warning.event} ({warning.color}) - {warning.time_start_text}")
                    else:
                        logger.error(f"Failed to send ČHMÚ warning email: {notification.error_message}")
                else:
                    logger.info("New ČHMÚ warnings detected but recent storm alert already sent - skipping standalone email")
            else:
                logger.debug("No new ČHMÚ warnings detected")
                
        except Exception as e:
            logger.error(f"Error checking ČHMÚ warnings: {e}", exc_info=True)

    async def generate_local_forecast_task(self):
        """Generates and stores a local 6-hour forecast."""
        logger.info("Generating local 6-hour forecast...")
        try:
            weather_data = self.database.get_recent_weather_data(hours=24)
            from advanced_forecast import AdvancedForecastGenerator
            async with AdvancedForecastGenerator(self.config) as forecast_generator:
                forecast = await forecast_generator.generate_physics_forecast(weather_data)
                if forecast:
                    self.database.store_enhanced_forecast(forecast, 'physics')
                    logger.info("Local physics forecast generated and stored in enhanced_forecasts.")
        except Exception as e:
            logger.error(f"Error generating local forecast: {e}", exc_info=True)

    async def generate_deepseek_forecast_task(self):
        """Generates and stores a DeepSeek 6-hour forecast."""
        logger.info("Generating DeepSeek 6-hour forecast...")
        try:
            weather_data = await self.data_collector.collect_weather_data()
            from advanced_forecast import AdvancedForecastGenerator
            async with AdvancedForecastGenerator(self.config) as forecast_generator:
                forecast = await forecast_generator.generate_ai_forecast(weather_data)
                if forecast:
                    self.database.store_enhanced_forecast(forecast, 'ai')
                    logger.info("DeepSeek AI forecast generated and stored in enhanced_forecasts.")
        except Exception as e:
            logger.error(f"Error generating DeepSeek forecast: {e}", exc_info=True)

    async def run_thunderstorm_predictor(self):
        """Runs the thunderstorm predictor script."""
        logger.info("Running thunderstorm predictor...")
        try:
            from thunderstorm_predictor import ThunderstormPredictor
            predictor = ThunderstormPredictor(self.config)
            predicted_time, confidence = predictor.predict_next_storm()
            predictor.store_prediction(predicted_time, confidence)
            logger.info("Thunderstorm predictor run successfully.")
        except Exception as e:
            logger.error(f"Error running thunderstorm predictor: {e}", exc_info=True)

    def setup_jobs(self):
        """Set up scheduled jobs."""
        logger.info("Setting up scheduled jobs...")
        
        # Main monitoring cycle every 10 minutes
        self.scheduler.add_job(
            self.monitoring_cycle,
            trigger=IntervalTrigger(minutes=self.config.system.monitoring_interval_minutes),
            id='monitoring_cycle',
            name='Weather Monitoring Cycle',
            max_instances=1,  # Prevent overlapping executions
            coalesce=True,
            misfire_grace_time=60
        )
        
        # Local forecast generation every 2 minutes
        self.scheduler.add_job(
            self.generate_local_forecast_task,
            trigger=IntervalTrigger(minutes=2),
            id='local_forecast_generation',
            name='Local Forecast Generation',
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60
        )

        # DeepSeek forecast generation every 5 hours (configurable)
        self.scheduler.add_job(
            self.generate_deepseek_forecast_task,
            trigger=IntervalTrigger(hours=self.config.system.deepseek_forecast_interval_hours),
            id='deepseek_forecast_generation',
            name='DeepSeek Forecast Generation',
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60
        )
        
        # ODSTRANĚNO: Denní souhrny - uživatel je zakázal
        # "Asi se vyser na denni emaily. Je to zbytečný. Stačí jen extremní výstrahy a bouřky a deště nad Brnem."
        
        # ČHMÚ warning check every 10 minutes (same as weather monitoring)
        self.scheduler.add_job(
            self.chmi_warning_check,
            trigger=IntervalTrigger(minutes=self.config.system.monitoring_interval_minutes),
            id='chmi_warning_check',
            name='ČHMÚ Warning Check',
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60
        )
        
        # Thunderstorm prediction generation every hour
        self.scheduler.add_job(
            self.run_thunderstorm_predictor,
            trigger=IntervalTrigger(hours=1),
            id='thunderstorm_prediction',
            name='Thunderstorm Prediction',
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        
        # Database cleanup every day at 2 AM
        self.scheduler.add_job(
            self.cleanup_task,
            trigger=CronTrigger(hour=2, minute=0),
            id='cleanup_task',
            name='Database Cleanup',
            max_instances=1
        )
        
        logger.info("Scheduled jobs configured successfully")
    
    async def start(self):
        """Start the monitoring system."""
        if self.is_running:
            logger.warning("Monitoring system is already running")
            return
        
        logger.info("Starting Weather Storm Detection System...")
        logger.info(f"Monitoring location: {self.config.weather.city_name}, {self.config.weather.region}")
        logger.info(f"Monitoring interval: {self.config.system.monitoring_interval_minutes} minutes")
        logger.info("Daily summaries: DISABLED (only storm alerts enabled)")
        logger.info(f"Storm confidence threshold: {self.config.ai.storm_confidence_threshold:.1%}")
        
        # Set up jobs
        self.setup_jobs()
        
        # Start scheduler
        self.scheduler.start()
        self.is_running = True
        
        # Start lightning monitor
        logger.info("Starting lightning monitor...")
        asyncio.create_task(self.lightning_monitor.monitor_lightning())
        
        # Run initial monitoring cycle
        logger.info("Running initial monitoring cycle...")
        await self.monitoring_cycle()
        
        logger.info("Weather Storm Detection System started successfully")
        logger.info("System is now monitoring weather conditions...")
        
    async def stop(self):
        """Stop the monitoring system."""
        if not self.is_running:
            return
            
        logger.info("Stopping Weather Storm Detection System...")
        
        # Stop lightning monitor
        self.lightning_monitor.stop()
        
        # Shutdown scheduler
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
        
        self.is_running = False
        logger.info("Weather Storm Detection System stopped")
    
    async def run_forever(self):
        """Run the monitoring system indefinitely."""
        await self.start()
        
        try:
            # Keep the event loop running
            while self.is_running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Monitoring system cancelled")
        finally:
            await self.stop()
    
    def _should_run_ai_analysis(self, weather_data, chmi_warnings) -> bool:
        """
        Determine if AI analysis should run to save API costs.
        Only run AI when there are storm indicators, including lightning activity.
        """
        # Check for recent lightning activity first (highest priority)
        lightning_activity = self.lightning_monitor.get_recent_lightning_activity(hours=1)
        if lightning_activity.get('czech_strikes', 0) > 0 or lightning_activity.get('nearby_strikes', 0) > 0:
            logger.info(f"AI analysis triggered by lightning activity: {lightning_activity.get('czech_strikes', 0)} Czech strikes, {lightning_activity.get('nearby_strikes', 0)} nearby strikes")
            return True
        # Check ČHMÚ warnings with smart filtering (based on CAP documentation)
        if chmi_warnings:
            current_time = datetime.now()
            
            for warning in chmi_warnings:
                # Check for storm-related warning types (already filtered by get_storm_warnings)
                # Focus on significant warnings (yellow, orange, red)
                if warning.color in ['yellow', 'orange', 'red']:
                    
                    # Parse warning start time to check if it's within next 24 hours
                    try:
                        if hasattr(warning, 'time_start_iso') and warning.time_start_iso:
                            # Handle timezone info properly
                            start_time_str = warning.time_start_iso.replace('Z', '+00:00')
                            warning_start = datetime.fromisoformat(start_time_str)
                            
                            # Convert to local time if needed
                            if warning_start.tzinfo:
                                warning_start = warning_start.replace(tzinfo=None)
                            
                            # Smart timing for warnings:
                            # - Immediate warnings (next 6 hours): analyze immediately
                            # - Tomorrow's warnings: analyze only 3 hours before start time
                            # - Far future warnings (>48h): ignore completely
                            time_until_warning = (warning_start - current_time).total_seconds()
                            
                            if time_until_warning > 172800:  # More than 48 hours away
                                logger.info(f"Skipping AI analysis for far future warning: {warning.event} starts in {time_until_warning/3600:.1f} hours")
                                continue
                            elif time_until_warning > 21600:  # More than 6 hours away (tomorrow's warnings)
                                # Only analyze if warning starts within 3 hours 
                                if time_until_warning > 10800:  # More than 3 hours away
                                    logger.info(f"Tomorrow's warning scheduled - will analyze 3h before: {warning.event} starts in {time_until_warning/3600:.1f} hours")
                                    continue
                                
                        # Check if we've already analyzed this specific warning recently
                        warning_cache_key = f"chmi_{warning.identifier}_{warning.event}"
                        if self._is_warning_recently_analyzed(warning_cache_key):
                            logger.info(f"Skipping AI analysis - warning already analyzed recently: {warning.event}")
                            continue
                            
                        # Mark this warning as analyzed
                        self._mark_warning_analyzed(warning_cache_key)
                        logger.info(f"AI analysis triggered by ČHMÚ warning: {warning.event}")
                        return True
                        
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Could not parse warning time for {warning.event}: {e}")
                        # If we can't parse time, analyze it to be safe (but cache it)
                        warning_cache_key = f"chmi_{warning.identifier}_{warning.event}"
                        if not self._is_warning_recently_analyzed(warning_cache_key):
                            self._mark_warning_analyzed(warning_cache_key)
                            logger.info(f"AI analysis triggered by ČHMÚ warning (unparseable time): {warning.event}")
                            return True
        
        # Check weather conditions for storm indicators with caching
        current_time = datetime.now()
        
        for data in weather_data:
            # Very high precipitation probability (more conservative)
            if data.precipitation_probability and data.precipitation_probability > 80:
                cache_key = f"precip_prob_{data.precipitation_probability:.0f}"
                if not self.database.is_weather_condition_recently_analyzed(cache_key):
                    self.database.mark_weather_condition_analyzed(cache_key)
                    logger.info(f"AI analysis triggered by very high precipitation probability: {data.precipitation_probability}%")
                    return True
            
            # Heavy precipitation only
            if data.precipitation and data.precipitation > 5.0:
                cache_key = f"precipitation_{data.precipitation:.1f}"
                if not self.database.is_weather_condition_recently_analyzed(cache_key):
                    self.database.mark_weather_condition_analyzed(cache_key)
                    logger.info(f"AI analysis triggered by active precipitation: {data.precipitation}mm")
                    return True
            
            # High humidity + low pressure (storm conditions)
            if data.humidity > 80 and data.pressure < 1010:
                cache_key = f"storm_conditions_{data.humidity:.0f}_{data.pressure:.0f}"
                if not self.database.is_weather_condition_recently_analyzed(cache_key):
                    self.database.mark_weather_condition_analyzed(cache_key)
                    logger.info(f"AI analysis triggered by storm conditions: humidity {data.humidity}%, pressure {data.pressure}hPa")
                    return True
            
            # Extreme wind speeds (severe gale/storm force winds only)
            if data.wind_speed and data.wind_speed > 24:  # >24 m/s (~86 km/h, severe gale force)
                # Group wind speeds into ranges to avoid repeated analysis for similar values
                wind_range = int(data.wind_speed // 5) * 5  # Group into 5 m/s ranges
                cache_key = f"extreme_wind_range_{wind_range}"
                if not self.database.is_weather_condition_recently_analyzed(cache_key):
                    self.database.mark_weather_condition_analyzed(cache_key)
                    logger.info(f"AI analysis triggered by very high wind speed: {data.wind_speed} m/s (range {wind_range}-{wind_range+4})")
                    return True
                else:
                    logger.debug(f"Skipping AI analysis - high wind speed {data.wind_speed} m/s already analyzed recently")
            
            # Stormy conditions in description
            if data.description:
                stormy_keywords = ['storm', 'thunder', 'lightning', 'heavy rain', 
                                 'bouř', 'déšť', 'blesk', 'prudký']
                if any(keyword in data.description.lower() for keyword in stormy_keywords):
                    cache_key = f"description_{hash(data.description.lower())}"
                    if not self.database.is_weather_condition_recently_analyzed(cache_key):
                        self.database.mark_weather_condition_analyzed(cache_key)
                        logger.info(f"AI analysis triggered by weather description: {data.description}")
                        return True
        
        # Run AI analysis occasionally even in normal conditions (once per hour max)
        last_analysis = self.database.get_last_storm_analysis()
        if last_analysis is None:
            logger.info("AI analysis triggered - no previous analysis found")
            return True
        
        # If last analysis was more than 1 hour ago, run periodic check
        time_since_last = datetime.now() - last_analysis.timestamp
        if time_since_last.total_seconds() > 3600:  # 1 hour
            logger.info("AI analysis triggered - periodic check (>1 hour since last)")
            return True
        
        # Skip AI analysis - normal conditions
        return False
    
    def _is_warning_recently_analyzed(self, warning_key: str) -> bool:
        """Check if a warning has been analyzed recently (within 6 hours)."""
        if warning_key not in self._warning_analysis_cache:
            return False
            
        last_analysis = self._warning_analysis_cache[warning_key]
        time_since_analysis = (datetime.now() - last_analysis).total_seconds()
        
        # Consider warning recently analyzed if within 6 hours
        return time_since_analysis < 21600  # 6 hours
    
    def _mark_warning_analyzed(self, warning_key: str):
        """Mark a warning as analyzed with current timestamp."""
        self._warning_analysis_cache[warning_key] = datetime.now()
        
        # Clean up old cache entries (older than 24 hours)
        current_time = datetime.now()
        expired_keys = [
            key for key, timestamp in self._warning_analysis_cache.items()
            if (current_time - timestamp).total_seconds() > 86400  # 24 hours
        ]
        
        for key in expired_keys:
            del self._warning_analysis_cache[key]
        
        logger.debug(f"Warning cache updated. Current entries: {len(self._warning_analysis_cache)}")
    

async def main():
    """Main entry point for the weather monitoring system."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('weather_monitor.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        config = load_config()
        
        # Validate configuration
        if not config.weather.openweather_api_key:
            raise ValueError("OpenWeather API key not configured")
        if not config.weather.visual_crossing_api_key:
            raise ValueError("Visual Crossing API key not configured")
        if not config.ai.deepseek_api_key:
            raise ValueError("DeepSeek API key not configured")
        if not config.email.sender_email or not config.email.sender_password:
            raise ValueError("Email configuration incomplete")
        
        # Create and start monitoring system
        scheduler = WeatherMonitoringScheduler(config)
        await scheduler.run_forever()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    # Run the monitoring system
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMonitoring system interrupted by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)