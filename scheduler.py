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

from config import Config, load_config
from data_fetcher import WeatherDataCollector
from ai_analysis import StormDetectionEngine
from email_notifier import EmailNotifier
from pdf_generator import WeatherReportGenerator
from storage import WeatherDatabase
from models import EmailNotification
from chmi_warnings import ChmiWarningMonitor

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
        self.email_notifier = EmailNotifier(config)
        self.pdf_generator = WeatherReportGenerator(config)
        self.database = WeatherDatabase(config)
        self.chmi_monitor = ChmiWarningMonitor("6203")  # Brno CISORP code
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(self.stop())
    
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
            
            # 3. Get ČHMÚ warnings for analysis
            chmi_warnings = self.chmi_monitor.get_all_active_warnings()
            
            # 4. Analyze storm potential with ČHMÚ data
            historical_data = self.database.get_recent_weather_data(hours=6)
            analysis = await self.storm_engine.analyze_storm_potential(weather_data, historical_data, chmi_warnings)
            
            if analysis:
                # 5. Store analysis results
                self.database.store_storm_analysis(analysis)
                
                # 6. Check if combined storm alert should be sent
                if self.storm_engine.should_send_alert(analysis):
                    last_alert_time = self.database.get_last_storm_alert()
                    
                    if self.email_notifier.can_send_storm_alert(last_alert_time):
                        # Generate PDF report
                        pdf_path = self.pdf_generator.generate_storm_report(
                            analysis, weather_data, historical_data
                        )
                        
                        # Send combined weather alert email (AI + ČHMÚ)
                        notification = self.email_notifier.send_combined_weather_alert(
                            analysis, weather_data, chmi_warnings, pdf_path
                        )
                        self.database.store_email_notification(notification)
                        
                        if notification.sent_successfully:
                            logger.warning(f"COMBINED WEATHER ALERT SENT: AI Confidence {analysis.confidence_score:.1%}, ČHMÚ warnings: {len(chmi_warnings)}")
                        else:
                            logger.error(f"Failed to send combined weather alert: {notification.error_message}")
                    else:
                        logger.info("Storm detected but email delay period not elapsed")
                
            cycle_duration = (datetime.now() - cycle_start).total_seconds()
            logger.info(f"Monitoring cycle completed in {cycle_duration:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}", exc_info=True)
    
    async def daily_summary_task(self):
        """Send daily weather summary with AI-generated content."""
        logger.info("Executing daily summary task with AI analysis")
        
        try:
            # Get recent weather data for summary
            recent_data = self.database.get_recent_weather_data(hours=24)
            
            # Get current weather data
            weather_data = await self.data_collector.collect_weather_data()
            
            # Get current ČHMÚ warnings for context
            chmi_warnings = self.chmi_monitor.get_all_active_warnings()
            
            # Send daily summary email with AI-generated content
            notification = await self.email_notifier.send_daily_summary_with_ai(
                weather_data, 
                chmi_warnings
            )
            
            self.database.store_email_notification(notification)
            
            if notification.sent_successfully:
                logger.info(f"Daily summary email with AI content sent successfully (ČHMÚ warnings: {len(chmi_warnings)})")
            else:
                logger.error(f"Failed to send daily summary: {notification.error_message}")
                
        except Exception as e:
            logger.error(f"Error in daily summary task: {e}", exc_info=True)
    
    async def cleanup_task(self):
        """Perform database cleanup and maintenance."""
        logger.info("Executing cleanup task")
        
        try:
            # Clean up old data (keep 30 days of regular data, 90 days of analysis)
            self.database.cleanup_old_data(days_to_keep=30)
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
        
        # Daily summary at 9 AM
        self.scheduler.add_job(
            self.daily_summary_task,
            trigger=CronTrigger(hour=self.config.system.daily_summary_hour, minute=0),
            id='daily_summary',
            name='Daily Weather Summary',
            max_instances=1
        )
        
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
        logger.info(f"Daily summary time: {self.config.system.daily_summary_hour}:00")
        logger.info(f"Storm confidence threshold: {self.config.ai.storm_confidence_threshold:.1%}")
        
        # Set up jobs
        self.setup_jobs()
        
        # Start scheduler
        self.scheduler.start()
        self.is_running = True
        
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