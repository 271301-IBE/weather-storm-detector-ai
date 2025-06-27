"""Přepsaný výstižný email notifikační systém - jen důležité výstrahy."""

import smtplib
import ssl
import logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List
import os
import asyncio

from models import StormAnalysis, WeatherData, EmailNotification, ChmiWarningNotification, WeatherForecast
from chmi_warnings import ChmiWarning
from config import Config
from ai_analysis import StormDetectionEngine
from storage import WeatherDatabase

logger = logging.getLogger(__name__)

class EmailNotifier:
    """Výstižný email notifikátor jen pro kritické výstrahy."""
    
    def __init__(self, config: Config):
        """Initialize email notifier."""
        self.config = config
        
    def _create_smtp_connection(self):
        """Create SMTP connection with Seznam.cz."""
        try:
            if self.config.email.smtp_use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(
                    self.config.email.smtp_server,
                    self.config.email.smtp_port,
                    context=context
                )
            else:
                server = smtplib.SMTP(
                    self.config.email.smtp_server,
                    self.config.email.smtp_port
                )
                server.starttls()
            
            server.login(
                self.config.email.sender_email,
                self.config.email.sender_password
            )
            
            logger.debug("SMTP connection established successfully")
            return server
            
        except Exception as e:
            logger.error(f"Failed to create SMTP connection: {e}")
            raise
    
    def _create_storm_alert_email(self, analysis: StormAnalysis, weather_data: List[WeatherData] = None) -> MIMEMultipart:
        """Výstižný storm alert email."""
        msg = MIMEMultipart()
        msg['From'] = f"{self.config.email.sender_name} <{self.config.email.sender_email}>"
        msg['To'] = self.config.email.recipient_email
        
        # Výstižný nadpis podle závažnosti
        if analysis.alert_level.value.upper() in ['CRITICAL', 'HIGH']:
            msg['Subject'] = f"🚨 BOUŘE NAD BRNEM - {analysis.alert_level.value.upper()}"
        else:
            msg['Subject'] = f"⚠️ Riziko bouře - Brno"
        
        # Jednoduché HTML - výstižné a přehledné
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                .alert {{ background: #f8d7da; border-left: 5px solid #dc3545; padding: 20px; border-radius: 5px; }}
                .warning {{ background: #fff3cd; border-left: 5px solid #ffc107; padding: 20px; border-radius: 5px; }}
                .info {{ background: #d1ecf1; border-left: 5px solid #0dcaf0; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .weather {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                h1 {{ margin-top: 0; }}
                .time {{ color: #666; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="{'alert' if analysis.alert_level.value.upper() in ['CRITICAL', 'HIGH'] else 'warning'}">
                <h1>{'🚨 BOUŘE NAD BRNEM' if analysis.alert_level.value.upper() in ['CRITICAL', 'HIGH'] else '⚠️ Riziko bouře nad Brnem'}</h1>
                <p><strong>Detekováno:</strong> {analysis.timestamp.strftime('%d.%m. %H:%M')}</p>
                <p><strong>Spolehlivost:</strong> {analysis.confidence_score:.0%}</p>
        """
        
        if analysis.predicted_arrival:
            html_content += f"<p><strong>Příchod:</strong> {analysis.predicted_arrival.strftime('%d.%m. %H:%M')}</p>"
            
        if analysis.predicted_intensity:
            intensity_czech = {
                "light": "slabá",
                "moderate": "střední", 
                "heavy": "silná",
                "severe": "extrémní"
            }
            html_content += f"<p><strong>Intenzita:</strong> {intensity_czech.get(analysis.predicted_intensity, analysis.predicted_intensity)}</p>"
        
        html_content += f"""
            </div>
            
            <div class="info">
                <h3>📋 Shrnutí</h3>
                <p>{analysis.analysis_summary}</p>
            </div>
            
            <div class="weather">
                <h3>🌤️ Aktuální počasí</h3>
        """
        
        if weather_data:
            # Jednoduché zobrazení nejdůležitějších dat
            latest_data = weather_data[0]
            html_content += f"""
                <p><strong>Teplota:</strong> {latest_data.temperature:.1f}°C | <strong>Vlhkost:</strong> {latest_data.humidity:.0f}% | <strong>Vítr:</strong> {latest_data.wind_speed:.1f} m/s</p>
                <p><strong>Tlak:</strong> {latest_data.pressure:.0f} hPa | <strong>Srážky:</strong> {latest_data.precipitation:.1f} mm</p>
                <p><strong>Podmínky:</strong> {latest_data.description}</p>
            """
        else:
            html_content += "<p>Data nejsou k dispozici</p>"
            
        html_content += f"""
            </div>
            
            {f'<div class="info"><h3>⚠️ Doporučení</h3><ul>{"".join([f"<li>{rec}</li>" for rec in analysis.recommendations])}</ul></div>' if analysis.recommendations else ''}
            
            <div class="info">
                <p><strong>Sledujte:</strong> <a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/radar">ČHMÚ radar</a> | 
                <a href="https://www.windy.com/?49.238,16.607,8">Windy Brno</a></p>
            </div>
            
            <p class="time">⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')} | Clipron AI Weather</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        return msg
    
    def _create_chmi_warning_email(self, warnings: List[ChmiWarning], ai_analysis: Optional[StormAnalysis] = None) -> MIMEMultipart:
        """Výstižný ČHMÚ warning email s volitelnou AI analýzou."""
        msg = MIMEMultipart()
        msg['From'] = f"{self.config.email.sender_name} <{self.config.email.sender_email}>"
        msg['To'] = self.config.email.recipient_email
        
        # Výstižný nadpis podle závažnosti
        severity_order = {'red': 4, 'orange': 3, 'yellow': 2, 'green': 1, 'unknown': 0}
        most_severe = max(warnings, key=lambda w: severity_order.get(w.color, 0))
        
        if most_severe.color == 'red':
            msg['Subject'] = f"🔴 EXTRÉMNÍ VÝSTRAHA ČHMÚ - {most_severe.event} - {self.config.weather.city_name}"
        elif most_severe.color == 'orange':
            msg['Subject'] = f"🟠 VELKÁ VÝSTRAHA ČHMÚ - {most_severe.event} - {self.config.weather.city_name}"
        elif most_severe.color == 'yellow':
            msg['Subject'] = f"🟡 VÝSTRAHA ČHMÚ - {most_severe.event} - {self.config.weather.city_name}"
        else:
            msg['Subject'] = f"🏛️ ČHMÚ - {most_severe.event} - {self.config.weather.city_name}"
        
        # Jednoduché CSS a struktura
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                .red {{ background: #f8d7da; border-left: 5px solid #dc3545; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .orange {{ background: #fde2a3; border-left: 5px solid #fd7e14; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .yellow {{ background: #fff3cd; border-left: 5px solid #ffc107; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .green {{ background: #d4edda; border-left: 5px solid #198754; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                h1 {{ margin-top: 0; }}
                .time {{ color: #666; font-size: 0.9em; }}
                .info {{ background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <h1>🏛️ ČHMÚ Výstraha pro {self.config.weather.city_name}</h1>
            <p class="time">📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        """
        
        # Přidat varování - jednoduše a výstižně
        for warning in warnings:
            color_class = warning.color if warning.color in ['red', 'orange', 'yellow', 'green'] else 'yellow'
            
            html_content += f"""
            <div class="{color_class}">
                <h2>{warning.event}</h2>
                <p><strong>Platnost:</strong> {warning.time_start_text} - {warning.time_end_text or 'neurčeno'}</p>
                <p><strong>Stav:</strong> {'🔴 PROBÍHÁ' if warning.in_progress else '🟡 Očekává se'}</p>
                {f'<p><strong>Popis:</strong> {warning.detailed_text}</p>' if warning.detailed_text else ''}
                {f'<p><strong>⚠️ Doporučení:</strong> {warning.instruction}</p>' if warning.instruction else ''}
            </div>
            """
        
        if ai_analysis:
            html_content += f"""
            <div class="info">
                <h3>🧠 AI Analýza počasí</h3>
                <p><strong>Spolehlivost AI:</strong> {ai_analysis.confidence_score:.0%}</p>
                <p><strong>Detekce bouře:</strong> {'Ano' if ai_analysis.storm_detected else 'Ne'}</p>
                <p><strong>Úroveň upozornění:</strong> {ai_analysis.alert_level.value}</p>
                <p><strong>Shrnutí AI:</strong> {ai_analysis.analysis_summary}</p>
                {f'<p><strong>Doporučení AI:</strong><ul>{"".join([f"<li>{rec}</li>" for rec in ai_analysis.recommendations])}</ul></p>' if ai_analysis.recommendations else ''}
            </div>
            """

        html_content += f"""
            <div class="info">
                <p><strong>Sledujte:</strong> <a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/radar">ČHMÚ radar</a> | 
                <a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/meteorologicka-upozorneni">Varování</a> | 
                <a href="https://www.windy.com/?49.238,16.607,8">Windy {self.config.weather.city_name}</a></p>
            </div>
            
            <p class="time">⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')} | Clipron AI Weather | ČHMÚ Data</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        return msg
    
    def send_storm_alert(self, analysis: StormAnalysis, weather_data: Optional[List[WeatherData]] = None, pdf_path: Optional[str] = None) -> EmailNotification:
        """Send storm alert email - jen pro vysoké riziko."""
        # POUZE pro HIGH a CRITICAL úrovně
        if analysis.alert_level.value.upper() not in ['HIGH', 'CRITICAL']:
            logger.info(f"Přeskakuji storm alert pro úroveň {analysis.alert_level.value} - posílám jen HIGH/CRITICAL")
            return EmailNotification(
                timestamp=datetime.now(),
                recipient=self.config.email.recipient_email,
                subject="Alert skipped - low severity",
                message_type="storm_alert_skipped",
                sent_successfully=True,
                error_message="Alert level too low"
            )
        
        notification = EmailNotification(
            timestamp=datetime.now(),
            recipient=self.config.email.recipient_email,
            subject=f"🚨 BOUŘE NAD {self.config.weather.city_name.upper()} - {analysis.alert_level.value.upper()}",
            message_type="storm_alert",
            sent_successfully=False,
            error_message=None
        )
        
        try:
            msg = self._create_storm_alert_email(analysis, weather_data)
            
            # Attach PDF report if provided
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= storm_report_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf'
                )
                msg.attach(part)
            
            with self._create_smtp_connection() as server:
                server.send_message(msg)
                
            notification.sent_successfully = True
            logger.info(f"Storm alert email sent successfully to {self.config.email.recipient_email}")
            
        except Exception as e:
            notification.error_message = str(e)
            logger.error(f"Failed to send storm alert email: {e}")
            
        return notification
    
    def send_chmi_warning(self, warnings: List[ChmiWarning]) -> ChmiWarningNotification:
        """Send ČHMÚ warning email - jen pro bouřky/srážky."""
        if not warnings:
            raise ValueError("No warnings provided")
        
        # Filtr jen pro bouřky, srážky a extrémní výstrahy
        storm_warnings = []
        for warning in warnings:
            # Bouřky a srážky
            if any(keyword in warning.event.lower() for keyword in ['bouř', 'déšť', 'srážk', 'thunder', 'rain']):
                storm_warnings.append(warning)
            # Extrémní výstrahy (červené/oranžové)
            elif warning.color in ['red', 'orange']:
                storm_warnings.append(warning)
        
        if not storm_warnings:
            logger.info("Přeskakuji ČHMÚ email - nejsou bouřky ani extrémní výstrahy")
            # Return dummy notification
            return ChmiWarningNotification(
                timestamp=datetime.now(),
                warning_id="skipped",
                event="No relevant warnings",
                color="green",
                warning_type="skipped",
                time_start=datetime.now(),
                time_end=None,
                recipient=self.config.email.recipient_email,
                sent_successfully=True,
                error_message="No storm/extreme warnings to send"
            )
        
        # Use the most severe warning for notification record
        severity_order = {'red': 4, 'orange': 3, 'yellow': 2, 'green': 1, 'unknown': 0}
        primary_warning = max(storm_warnings, key=lambda w: severity_order.get(w.color, 0))
        
        notification = ChmiWarningNotification(
            timestamp=datetime.now(),
            warning_id=primary_warning.identifier,
            event=primary_warning.event,
            color=primary_warning.color,
            warning_type=primary_warning.warning_type,
            time_start=datetime.fromtimestamp(primary_warning.time_start_unix),
            time_end=datetime.fromtimestamp(primary_warning.time_end_unix) if primary_warning.time_end_unix else None,
            recipient=self.config.email.recipient_email,
            sent_successfully=False,
            error_message=None
        )
        
        try:
            # Fetch current weather data for AI analysis
            weather_db = WeatherDatabase(self.config)
            current_weather_data = weather_db.get_recent_weather_data(hours=1) # Get last hour of data
            
            # Run AI analysis with ČHMÚ warnings as context
            ai_engine = StormDetectionEngine(self.config)
            ai_analysis_result = asyncio.run(ai_engine.analyze_storm_potential(current_weather_data, chmi_warnings=storm_warnings))

            msg = self._create_chmi_warning_email(storm_warnings, ai_analysis=ai_analysis_result)
            
            with self._create_smtp_connection() as server:
                server.send_message(msg)
                
            notification.sent_successfully = True
            logger.info(f"ČHMÚ warning email sent successfully to {self.config.email.recipient_email} for {len(storm_warnings)} relevant warning(s)")
            
        except Exception as e:
            notification.error_message = str(e)
            logger.error(f"Failed to send ČHMÚ warning email: {e}")
            
        return notification
    
    def can_send_storm_alert(self, last_alert_time: Optional[datetime]) -> bool:
        """Check if enough time has passed since last storm alert."""
        if last_alert_time is None:
            return True
            
        time_since_last = datetime.now() - last_alert_time
        min_delay = timedelta(minutes=self.config.email.email_delay_minutes)
        
        return time_since_last >= min_delay
    
    # ODSTRANĚNO: Denní emaily - už se nepoužívají
    def send_daily_summary(self, *args, **kwargs):
        """Deprecated - daily summaries removed."""
        logger.info("Daily summaries are disabled - skipping")
        return EmailNotification(
            timestamp=datetime.now(),
            recipient=self.config.email.recipient_email,
            subject="Daily summary disabled",
            message_type="daily_summary_disabled",
            sent_successfully=True,
            error_message="Daily summaries disabled by design"
        )
    
    async def send_daily_summary_with_ai(self, *args, **kwargs):
        """Deprecated - daily summaries removed."""
        return self.send_daily_summary()
    
    def send_combined_weather_alert(self, analysis: StormAnalysis, weather_data: List[WeatherData], chmi_warnings: List[ChmiWarning] = None, pdf_path: Optional[str] = None) -> EmailNotification:
        """Send combined alert - používá nové výstižné storm_alert."""
        return self.send_storm_alert(analysis, weather_data, pdf_path)