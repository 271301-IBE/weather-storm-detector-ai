"""Email notification system for weather alerts."""

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

from models import StormAnalysis, WeatherData, EmailNotification, ChmiWarningNotification
from chmi_warnings import ChmiWarning
from config import Config

logger = logging.getLogger(__name__)

class EmailNotifier:
    """Handles email notifications for weather alerts."""
    
    def __init__(self, config: Config):
        """Initialize email notifier."""
        self.config = config
        
    def _create_smtp_connection(self):
        """Create SMTP connection with Seznam.cz."""
        try:
            if self.config.email.smtp_use_ssl:
                # Use SSL connection (port 465)
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(
                    self.config.email.smtp_server,
                    self.config.email.smtp_port,
                    context=context
                )
            else:
                # Use STARTTLS connection (port 587)
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
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed. Check email credentials: {e}")
            raise
        except smtplib.SMTPServerDisconnected as e:
            logger.error(f"SMTP server disconnected: {e}")
            raise
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error occurred: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to create SMTP connection: {e}")
            raise
    
    def _create_storm_alert_email(self, analysis: StormAnalysis, weather_data: List[WeatherData] = None) -> MIMEMultipart:
        """Create storm alert email message."""
        msg = MIMEMultipart()
        msg['From'] = f"{self.config.email.sender_name} <{self.config.email.sender_email}>"
        msg['To'] = self.config.email.recipient_email
        msg['Subject'] = f"⛈️ VAROVÁNÍ PŘED BOUŘÍ - {self.config.weather.city_name} - {analysis.alert_level.value.upper()}"
        
        # Create HTML content
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .alert-box {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .critical {{ background-color: #f8d7da; border-color: #f5c6cb; }}
                .high {{ background-color: #fff3cd; border-color: #ffeaa7; }}
                .medium {{ background-color: #d4edda; border-color: #c3e6cb; }}
                .timestamp {{ color: #666; font-size: 0.9em; }}
                .confidence {{ font-weight: bold; color: #e74c3c; }}
                .recommendations {{ background-color: #f8f9fa; padding: 10px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h2>🌩️ Varování před bouří - {self.config.weather.city_name}</h2>
            
            <div class="alert-box {analysis.alert_level.value.lower()}">
                <h3>⚠️ Úroveň varování: {analysis.alert_level.value.upper()}</h3>
                <p><strong>Čas detekce:</strong> {analysis.timestamp.strftime('%d.%m.%Y %H:%M:%S')}</p>
                <p><strong>Místo:</strong> {self.config.weather.city_name}, {self.config.weather.region}</p>
                <p class="confidence"><strong>Spolehlivost detekce:</strong> {analysis.confidence_score:.1%}</p>
        """
        
        if analysis.predicted_arrival:
            html_content += f"<p><strong>Předpokládaný příchod:</strong> {analysis.predicted_arrival.strftime('%d.%m.%Y %H:%M')}</p>"
            
        if analysis.predicted_intensity:
            intensity_czech = {
                "light": "slabá",
                "moderate": "mírná", 
                "heavy": "silná",
                "severe": "velmi silná"
            }
            html_content += f"<p><strong>Předpokládaná intenzita:</strong> {intensity_czech.get(analysis.predicted_intensity, analysis.predicted_intensity)}</p>"
        
        html_content += f"""
            </div>
            
            <h3>📊 Analýza počasí</h3>
            <p>{analysis.analysis_summary}</p>
            
            <h3>🌡️ Aktuální meteorologické údaje</h3>
        """
        
        if weather_data:
            # Add detailed weather data from all sources
            html_content += """
            <div class="weather-data">
                <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
                    <tr style="background-color: #f8f9fa;">
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Zdroj</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Teplota</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Vlhkost</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Tlak</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Vítr</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Srážky</th>
                    </tr>
            """
            
            for data in weather_data:
                source_name = "OpenWeather" if "openweather" in data.source.lower() else "Visual Crossing"
                html_content += f"""
                    <tr>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{source_name}</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.temperature:.1f}°C</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.humidity:.0f}%</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.pressure:.0f} hPa</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.wind_speed:.1f} m/s ({data.wind_direction}°)</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.precipitation:.1f} mm</td>
                    </tr>
                """
            
            html_content += """
                </table>
            """
            
            # Additional detailed information
            latest_data = weather_data[0]
            html_content += f"""
                <div style="margin: 15px 0; padding: 10px; background-color: #f8f9fa; border-radius: 5px;">
                    <h4>🔍 Podrobné údaje</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div><strong>Oblačnost:</strong> {latest_data.cloud_cover:.0f}%</div>
                        <div><strong>Viditelnost:</strong> {latest_data.visibility:.1f} km</div>
                        <div><strong>UV index:</strong> {getattr(latest_data, 'uv_index', 'N/A')}</div>
                        <div><strong>Rosný bod:</strong> {getattr(latest_data, 'dew_point', 'N/A')}°C</div>
                        <div><strong>Pocitová teplota:</strong> {getattr(latest_data, 'feels_like', 'N/A')}°C</div>
                        <div><strong>Podmínky:</strong> {latest_data.description}</div>
                    </div>
                </div>
            """
        else:
            html_content += "<p><em>Meteorologická data nejsou k dispozici.</em></p>"
            
        html_content += f"""
            </div>
            
            <div class="recommendations">
                <h3>💡 Doporučení</h3>
                <ul>
        """
        
        for recommendation in analysis.recommendations:
            html_content += f"<li>{recommendation}</li>"
            
        html_content += f"""
                </ul>
            </div>
            
            <div style="margin: 20px 0; padding: 15px; background-color: #e3f2fd; border-radius: 5px; border-left: 4px solid #2196f3;">
                <h3>🌐 Oficiální meteorologické zdroje</h3>
                <div style="margin: 10px 0;">
                    <h4>🏛️ ČHMÚ - Český hydrometeorologický ústav</h4>
                    <ul style="margin: 5px 0;">
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/meteorologicka-upozorneni" target="_blank" style="color: #1976d2; text-decoration: none;">📢 Meteorologická upozornění a varování</a></li>
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/radar" target="_blank" style="color: #1976d2; text-decoration: none;">🌧️ Meteorologický radar</a></li>
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/predpoved-pocasi" target="_blank" style="color: #1976d2; text-decoration: none;">🌤️ Předpověď počasí</a></li>
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/bourkova-aktivita" target="_blank" style="color: #1976d2; text-decoration: none;">⚡ Bouřková aktivita</a></li>
                    </ul>
                </div>
                
                <div style="margin: 10px 0;">
                    <h4>🌍 Další užitečné zdroje</h4>
                    <ul style="margin: 5px 0;">
                        <li><a href="https://www.windy.com/?49.238,16.607,8" target="_blank" style="color: #1976d2; text-decoration: none;">🌬️ Windy.com - Interaktivní mapa počasí</a></li>
                        <li><a href="https://www.lightningmaps.org/?lang=cs#m=oss;t=3;s=0;o=0;b=;ts=0;" target="_blank" style="color: #1976d2; text-decoration: none;">⚡ Mapa blesků v reálném čase</a></li>
                        <li><a href="https://www.yr.no/en/forecast/graph/2-3078610/Czech%20Republic/South%20Moravian%20Region/Brno" target="_blank" style="color: #1976d2; text-decoration: none;">📊 Yr.no - Podrobná předpověď</a></li>
                    </ul>
                </div>
                
                <div style="background-color: #fff3cd; padding: 10px; border-radius: 3px; margin-top: 10px;">
                    <strong>⚠️ Důležité:</strong> V případě vydání oficiálního varování ČHMÚ se řiďte jejich pokyny a doporučeními.
                </div>
            </div>
            
            <hr>
            <p class="timestamp">Automaticky generováno systémem Clipron AI Weather Detection<br>
            Čas: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br>
            📍 Lokace: {self.config.weather.city_name}, {self.config.weather.region}<br>
            🔄 Interval monitorování: {self.config.system.monitoring_interval_minutes} minut</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        return msg
    
    def _create_daily_summary_email(self, weather_data: List[WeatherData], forecast_summary: str = None) -> MIMEMultipart:
        """Create daily weather summary email."""
        msg = MIMEMultipart()
        msg['From'] = f"{self.config.email.sender_name} <{self.config.email.sender_email}>"
        msg['To'] = self.config.email.recipient_email
        msg['Subject'] = f"🌤️ Denní přehled počasí - {self.config.weather.city_name} - {datetime.now().strftime('%d.%m.%Y')}"
        
        # Get latest weather data
        latest_data = weather_data[0] if weather_data else None
        
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .weather-card {{ background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .current-weather {{ background-color: #e3f2fd; border-color: #bbdefb; }}
                .timestamp {{ color: #666; font-size: 0.9em; }}
                .weather-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
                .weather-item {{ background-color: white; padding: 10px; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <h2>🌤️ Denní přehled počasí - {self.config.weather.city_name}</h2>
            <p class="timestamp">Datum: {datetime.now().strftime('%d.%m.%Y')}, čas: 09:00</p>
            
            <div class="weather-card current-weather">
                <h3>🌡️ Aktuální počasí</h3>
        """
        
        if latest_data and weather_data:
            # Comprehensive weather data table
            html_content += """
                <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
                    <tr style="background-color: #f8f9fa;">
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Zdroj</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Teplota</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Vlhkost</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Tlak</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Vítr</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Srážky</th>
                    </tr>
            """
            
            for data in weather_data:
                source_name = "OpenWeather" if "openweather" in data.source.lower() else "Visual Crossing"
                html_content += f"""
                    <tr>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{source_name}</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.temperature:.1f}°C</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.humidity:.0f}%</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.pressure:.0f} hPa</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.wind_speed:.1f} m/s ({data.wind_direction}°)</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.precipitation:.1f} mm</td>
                    </tr>
                """
            
            html_content += """
                </table>
            """
            
            # Additional detailed information
            html_content += f"""
                <div style="margin: 15px 0; padding: 10px; background-color: #f8f9fa; border-radius: 5px;">
                    <h4>🔍 Podrobné údaje</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
                        <div><strong>Oblačnost:</strong> {latest_data.cloud_cover:.0f}%</div>
                        <div><strong>Viditelnost:</strong> {latest_data.visibility:.1f} km</div>
                        <div><strong>UV index:</strong> {getattr(latest_data, 'uv_index', 'N/A')}</div>
                        <div><strong>Rosný bod:</strong> {getattr(latest_data, 'dew_point', 'N/A')}°C</div>
                        <div><strong>Pocitová teplota:</strong> {getattr(latest_data, 'feels_like', 'N/A')}°C</div>
                        <div><strong>Podmínky:</strong> {latest_data.description}</div>
                    </div>
                </div>
            """
        elif latest_data:
            html_content += f"""
                <div class="weather-grid">
                    <div class="weather-item"><strong>Teplota:</strong> {latest_data.temperature:.1f}°C</div>
                    <div class="weather-item"><strong>Vlhkost:</strong> {latest_data.humidity:.0f}%</div>
                    <div class="weather-item"><strong>Tlak:</strong> {latest_data.pressure:.0f} hPa</div>
                    <div class="weather-item"><strong>Vítr:</strong> {latest_data.wind_speed:.1f} m/s</div>
                    <div class="weather-item"><strong>Oblačnost:</strong> {latest_data.cloud_cover:.0f}%</div>
                    <div class="weather-item"><strong>Viditelnost:</strong> {latest_data.visibility:.1f} km</div>
                </div>
                <p><strong>Popis:</strong> {latest_data.description}</p>
                <p><strong>Srážky:</strong> {latest_data.precipitation:.1f} mm</p>
            """
        else:
            html_content += "<p>Data o aktuálním počasí nejsou k dispozici.</p>"
            
        html_content += """
            </div>
            
            <div class="weather-card">
                <h3>📈 Předpověď na den</h3>
        """
        
        if forecast_summary:
            html_content += f"<p>{forecast_summary}</p>"
        else:
            html_content += "<p>Předpověď bude aktualizována v dalším cyklu monitorování.</p>"
            
        html_content += f"""
            </div>
            
            <div class="weather-card">
                <h3>⚡ Riziko bouře</h3>
                <p>Systém nepřetržitě monitoruje meteorologické podmínky pro detekci bouří.</p>
                <p>V případě vysokého rizika bouře obdržíte okamžité varování.</p>
            </div>
            
            <div style="margin: 20px 0; padding: 15px; background-color: #e3f2fd; border-radius: 5px; border-left: 4px solid #2196f3;">
                <h3>🌐 Oficiální meteorologické zdroje</h3>
                <div style="margin: 10px 0;">
                    <h4>🏛️ ČHMÚ - Český hydrometeorologický ústav</h4>
                    <ul style="margin: 5px 0;">
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/meteorologicka-upozorneni" target="_blank" style="color: #1976d2; text-decoration: none;">📢 Meteorologická upozornění a varování</a></li>
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/radar" target="_blank" style="color: #1976d2; text-decoration: none;">🌧️ Meteorologický radar</a></li>
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/predpoved-pocasi" target="_blank" style="color: #1976d2; text-decoration: none;">🌤️ Předpověď počasí</a></li>
                    </ul>
                </div>
                
                <div style="margin: 10px 0;">
                    <h4>🌍 Další užitečné zdroje</h4>
                    <ul style="margin: 5px 0;">
                        <li><a href="https://www.windy.com/?49.238,16.607,8" target="_blank" style="color: #1976d2; text-decoration: none;">🌬️ Windy.com - Brno</a></li>
                        <li><a href="https://www.yr.no/en/forecast/graph/2-3078610/Czech%20Republic/South%20Moravian%20Region/Brno" target="_blank" style="color: #1976d2; text-decoration: none;">📊 Yr.no - Podrobná předpověď</a></li>
                    </ul>
                </div>
            </div>
            
            <hr>
            <p class="timestamp">Automaticky generováno systémem Clipron AI Weather Detection<br>
            Další souhrn: zítra v 09:00<br>
            📍 Lokace: {self.config.weather.city_name}, {self.config.weather.region}<br>
            🔄 Interval monitorování: {self.config.system.monitoring_interval_minutes} minut</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        return msg
    
    def send_storm_alert(self, analysis: StormAnalysis, weather_data: Optional[List[WeatherData]] = None, pdf_path: Optional[str] = None) -> EmailNotification:
        """Send storm alert email."""
        notification = EmailNotification(
            timestamp=datetime.now(),
            recipient=self.config.email.recipient_email,
            subject=f"Storm Alert - {analysis.alert_level.value}",
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
    
    async def send_daily_summary_with_ai(self, weather_data: List[WeatherData], chmi_warnings: List[ChmiWarning] = None) -> EmailNotification:
        """Send daily weather summary email with AI-generated content."""
        from ai_analysis import DeepSeekChatAnalyzer
        
        # Generate AI summary
        ai_summary = None
        try:
            async with DeepSeekChatAnalyzer(self.config) as chat_analyzer:
                ai_summary = await chat_analyzer.generate_daily_summary(weather_data, chmi_warnings)
        except Exception as e:
            logger.error(f"Failed to generate AI summary: {e}")
            ai_summary = "Automatické AI shrnutí dnes není k dispozici. Sledujte aktuální předpověď na ČHMÚ."
        
        return self.send_daily_summary(weather_data, ai_summary)
    
    def send_daily_summary(self, weather_data: List[WeatherData], forecast_summary: str = None) -> EmailNotification:
        """Send daily weather summary email."""
        notification = EmailNotification(
            timestamp=datetime.now(),
            recipient=self.config.email.recipient_email,
            subject="Daily Weather Summary",
            message_type="daily_summary",
            sent_successfully=False,
            error_message=None
        )
        
        try:
            msg = self._create_daily_summary_email(weather_data, forecast_summary)
            
            with self._create_smtp_connection() as server:
                server.send_message(msg)
                
            notification.sent_successfully = True
            logger.info(f"Daily summary email sent successfully to {self.config.email.recipient_email}")
            
        except Exception as e:
            notification.error_message = str(e)
            logger.error(f"Failed to send daily summary email: {e}")
            
        return notification
    
    def can_send_storm_alert(self, last_alert_time: Optional[datetime]) -> bool:
        """Check if enough time has passed since last storm alert."""
        if last_alert_time is None:
            return True
            
        time_since_last = datetime.now() - last_alert_time
        min_delay = timedelta(minutes=self.config.email.email_delay_minutes)
        
        return time_since_last >= min_delay
    
    def _create_chmi_warning_email(self, warnings: List[ChmiWarning]) -> MIMEMultipart:
        """Create ČHMÚ warning email message."""
        msg = MIMEMultipart()
        msg['From'] = f"{self.config.email.sender_name} <{self.config.email.sender_email}>"
        msg['To'] = self.config.email.recipient_email
        
        # Determine most severe warning for subject
        severity_order = {'red': 4, 'orange': 3, 'yellow': 2, 'green': 1, 'unknown': 0}
        most_severe = max(warnings, key=lambda w: severity_order.get(w.color, 0))
        
        warning_count = len(warnings)
        subject_prefix = "🚨 OFICIÁLNÍ VÝSTRAHA ČHMÚ"
        if warning_count > 1:
            msg['Subject'] = f"{subject_prefix} - {warning_count} varování - {self.config.weather.city_name}"
        else:
            msg['Subject'] = f"{subject_prefix} - {most_severe.event} - {self.config.weather.city_name}"
        
        # Color mapping for display
        color_emoji = {
            'green': '🟢',
            'yellow': '🟡', 
            'orange': '🟠',
            'red': '🔴',
            'unknown': '⚪'
        }
        
        color_names = {
            'green': 'Zelená - Výhledová událost',
            'yellow': 'Žlutá - Výstraha',
            'orange': 'Oranžová - Velká výstraha', 
            'red': 'Červená - Extrémní výstraha',
            'unknown': 'Neznámá úroveň'
        }
        
        # Create HTML content
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                .warning-box {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .warning-red {{ background-color: #f8d7da; border-color: #f5c6cb; }}
                .warning-orange {{ background-color: #fde2a3; border-color: #fdb94e; }}
                .warning-yellow {{ background-color: #fff3cd; border-color: #ffeaa7; }}
                .warning-green {{ background-color: #d4edda; border-color: #c3e6cb; }}
                .warning-header {{ font-size: 1.2em; font-weight: bold; margin-bottom: 10px; }}
                .warning-meta {{ color: #666; font-size: 0.9em; margin: 10px 0; }}
                .warning-time {{ background-color: #f8f9fa; padding: 8px; border-radius: 3px; margin: 8px 0; }}
                .official-notice {{ background-color: #e3f2fd; border-left: 4px solid #2196f3; padding: 15px; margin: 20px 0; }}
                .chmi-links {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .timestamp {{ color: #666; font-size: 0.9em; }}
                .footer-info {{ background-color: #f1f1f1; padding: 10px; border-radius: 3px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <h2>🏛️ Oficiální meteorologická varování ČHMÚ</h2>
            <p><strong>Lokalita:</strong> {self.config.weather.city_name}, {self.config.weather.region}</p>
            <p><strong>Čas vydání:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
            
            <div class="official-notice">
                <h3>⚠️ Důležité informace</h3>
                <p><strong>Toto jsou oficiální meteorologická varování</strong> vydaná Českým hydrometeorologickým ústavem (ČHMÚ). 
                Jedná se o závazné informace o nebezpečných meteorologických jevech, které mohou ohrozit život, zdraví a majetek.</p>
                <p><strong>Doporučujeme:</strong> Řiďte se pokyny a doporučeními uvedenými v jednotlivých varováních.</p>
            </div>
        """
        
        # Add each warning
        for i, warning in enumerate(warnings, 1):
            color_class = f"warning-{warning.color}" if warning.color in ['red', 'orange', 'yellow', 'green'] else "warning-box"
            color_icon = color_emoji.get(warning.color, '⚪')
            color_name = color_names.get(warning.color, 'Neznámá úroveň')
            
            html_content += f"""
            <div class="warning-box {color_class}">
                <div class="warning-header">
                    {color_icon} Varování #{i}: {warning.event}
                </div>
                
                <div class="warning-meta">
                    <strong>Úroveň varování:</strong> {color_name}<br>
                    <strong>Typ jevu:</strong> {warning.warning_type}<br>
                    <strong>Oblast:</strong> {warning.area_description}<br>
                    <strong>Stav:</strong> {'🔴 PROBÍHÁ' if warning.in_progress else '🟡 Očekává se'}
                </div>
                
                <div class="warning-time">
                    <strong>⏰ Platnost varování:</strong><br>
                    📅 <strong>Od:</strong> {warning.time_start_text} ({warning.time_start_iso})<br>
            """
            
            if warning.time_end_text:
                html_content += f"""
                    📅 <strong>Do:</strong> {warning.time_end_text} ({warning.time_end_iso})<br>
                """
            else:
                html_content += """
                    📅 <strong>Do:</strong> Neurčeno<br>
                """
            
            html_content += "</div>"
            
            if warning.detailed_text:
                html_content += f"""
                <div style="margin: 10px 0;">
                    <strong>📝 Popis:</strong><br>
                    {warning.detailed_text}
                </div>
                """
            
            if warning.instruction:
                html_content += f"""
                <div style="background-color: #fff3cd; padding: 10px; border-radius: 3px; margin: 10px 0;">
                    <strong>💡 Doporučené opatření:</strong><br>
                    {warning.instruction}
                </div>
                """
            
            # Technical details
            html_content += f"""
            <details style="margin: 10px 0;">
                <summary style="cursor: pointer; color: #666;">🔍 Technické detaily</summary>
                <div style="margin: 10px 0; font-size: 0.9em; color: #666;">
                    <strong>ID varování:</strong> {warning.identifier}<br>
                    <strong>Naléhavost:</strong> {warning.urgency}<br>
                    <strong>Závažnost:</strong> {warning.severity}<br>
                    <strong>Jistota:</strong> {warning.certainty}<br>
                    <strong>Typ odpovědi:</strong> {warning.response_type}
                </div>
            </details>
            </div>
            """
        
        # ČHMÚ links section
        html_content += f"""
            <div class="chmi-links">
                <h3>🌐 Oficiální zdroje ČHMÚ</h3>
                <ul>
                    <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/meteorologicka-upozorneni" target="_blank">📢 Aktuální meteorologická upozornění</a></li>
                    <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/radar" target="_blank">🌧️ Meteorologický radar</a></li>
                    <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/predpoved-pocasi" target="_blank">🌤️ Předpověď počasí</a></li>
                    <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/bourkova-aktivita" target="_blank">⚡ Bouřková aktivita</a></li>
                    <li><a href="https://www.chmi.cz" target="_blank">🏛️ Hlavní stránka ČHMÚ</a></li>
                </ul>
            </div>
            
            <div class="footer-info">
                <h4>📱 Další užitečné aplikace a služby</h4>
                <ul>
                    <li><a href="https://www.windy.com/?49.238,16.607,8" target="_blank">🌬️ Windy.com - Interaktivní počasí pro Brno</a></li>
                    <li><a href="https://www.lightningmaps.org/?lang=cs" target="_blank">⚡ Mapa blesků v reálném čase</a></li>
                    <li><a href="https://yr.no" target="_blank">📊 Yr.no - Detailní předpovědi</a></li>
                </ul>
            </div>
            
            <hr>
            <p class="timestamp">
                Automaticky generováno systémem Clipron AI Weather Detection<br>
                Oficiální data z ČHMÚ XML API<br>
                Čas generování: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br>
                📍 Monitorovaná oblast: {self.config.weather.city_name}, {self.config.weather.region}<br>
                🔄 Interval kontroly: {self.config.system.monitoring_interval_minutes} minut
            </p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        return msg
    
    def send_chmi_warning(self, warnings: List[ChmiWarning]) -> ChmiWarningNotification:
        """Send ČHMÚ warning email."""
        if not warnings:
            raise ValueError("No warnings provided")
        
        # Use the most severe warning for notification record
        severity_order = {'red': 4, 'orange': 3, 'yellow': 2, 'green': 1, 'unknown': 0}
        primary_warning = max(warnings, key=lambda w: severity_order.get(w.color, 0))
        
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
            msg = self._create_chmi_warning_email(warnings)
            
            with self._create_smtp_connection() as server:
                server.send_message(msg)
                
            notification.sent_successfully = True
            logger.info(f"ČHMÚ warning email sent successfully to {self.config.email.recipient_email} for {len(warnings)} warning(s)")
            
        except Exception as e:
            notification.error_message = str(e)
            logger.error(f"Failed to send ČHMÚ warning email: {e}")
            
        return notification
    
    def _create_combined_weather_alert_email(self, analysis: StormAnalysis, weather_data: List[WeatherData], chmi_warnings: List[ChmiWarning] = None) -> MIMEMultipart:
        """Create combined weather alert email with AI analysis and ČHMÚ warnings."""
        msg = MIMEMultipart()
        msg['From'] = f"{self.config.email.sender_name} <{self.config.email.sender_email}>"
        msg['To'] = self.config.email.recipient_email
        
        # Determine alert level - use highest severity from AI or ČHMÚ
        alert_level = analysis.alert_level.value.upper()
        if chmi_warnings:
            severity_order = {'red': 'CRITICAL', 'orange': 'HIGH', 'yellow': 'MEDIUM', 'green': 'LOW'}
            chmi_max_severity = max(chmi_warnings, key=lambda w: ['green', 'yellow', 'orange', 'red'].index(w.color) if w.color in ['green', 'yellow', 'orange', 'red'] else -1)
            chmi_alert_level = severity_order.get(chmi_max_severity.color, 'LOW')
            # Use higher severity
            if ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].index(chmi_alert_level) > ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].index(alert_level):
                alert_level = chmi_alert_level
        
        warning_icon = "🚨" if alert_level in ["HIGH", "CRITICAL"] else "⚠️"
        msg['Subject'] = f"{warning_icon} VAROVÁNÍ PŘED BOUŘÍ + ČHMÚ - {self.config.weather.city_name} - {alert_level}"
        
        # Create HTML content
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                .alert-box {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .critical {{ background-color: #f8d7da; border-color: #f5c6cb; }}
                .high {{ background-color: #fff3cd; border-color: #ffeaa7; }}
                .medium {{ background-color: #d4edda; border-color: #c3e6cb; }}
                .low {{ background-color: #d1ecf1; border-color: #bee5eb; }}
                .warning-box {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .warning-red {{ background-color: #f8d7da; border-color: #f5c6cb; }}
                .warning-orange {{ background-color: #fde2a3; border-color: #fdb94e; }}
                .warning-yellow {{ background-color: #fff3cd; border-color: #ffeaa7; }}
                .warning-green {{ background-color: #d4edda; border-color: #c3e6cb; }}
                .timestamp {{ color: #666; font-size: 0.9em; }}
                .confidence {{ font-weight: bold; color: #e74c3c; }}
                .recommendations {{ background-color: #f8f9fa; padding: 10px; border-radius: 5px; }}
                .official-notice {{ background-color: #e3f2fd; border-left: 4px solid #2196f3; padding: 15px; margin: 20px 0; }}
                .chmi-section {{ background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <h2>🌩️ Kombinované varování před bouří - {self.config.weather.city_name}</h2>
            
            <div class="official-notice">
                <h3>🤖 AI Analýza + 🏛️ Oficiální ČHMÚ Data</h3>
                <p><strong>Systém detekoval vysoké riziko bouře</strong> na základě analýzy meteorologických dat a oficiálních varování ČHMÚ.</p>
                <p><strong>Spolehlivost detekce:</strong> {analysis.confidence_score:.1%} - Systém odesílá varování pouze při vysoké jistotě</p>
            </div>
            
            <div class="alert-box {alert_level.lower()}">
                <h3>{warning_icon} AI Detekce bouře - Úroveň: {alert_level}</h3>
                <p><strong>Čas detekce:</strong> {analysis.timestamp.strftime('%d.%m.%Y %H:%M:%S')}</p>
                <p><strong>Místo:</strong> {self.config.weather.city_name}, {self.config.weather.region}</p>
                <p class="confidence"><strong>Spolehlivost detekce:</strong> {analysis.confidence_score:.1%}</p>
        """
        
        if analysis.predicted_arrival:
            html_content += f"<p><strong>Předpokládaný příchod:</strong> {analysis.predicted_arrival.strftime('%d.%m.%Y %H:%M')}</p>"
            
        if analysis.predicted_intensity:
            intensity_czech = {
                "light": "slabá",
                "moderate": "mírná", 
                "heavy": "silná",
                "severe": "velmi silná"
            }
            html_content += f"<p><strong>Předpokládaná intenzita:</strong> {intensity_czech.get(analysis.predicted_intensity, analysis.predicted_intensity)}</p>"
        
        html_content += f"""
            </div>
            
            <h3>📊 AI Analýza meteorologických podmínek</h3>
            <p>{analysis.analysis_summary}</p>
        """
        
        # Add ČHMÚ warnings section if available
        if chmi_warnings:
            html_content += f"""
            <div class="chmi-section">
                <h3>🏛️ Oficiální varování ČHMÚ ({len(chmi_warnings)} varování)</h3>
            """
            
            # Color mapping
            color_emoji = {
                'green': '🟢',
                'yellow': '🟡', 
                'orange': '🟠',
                'red': '🔴',
                'unknown': '⚪'
            }
            
            color_names = {
                'green': 'Zelená - Výhledová událost',
                'yellow': 'Žlutá - Výstraha',
                'orange': 'Oranžová - Velká výstraha', 
                'red': 'Červená - Extrémní výstraha',
                'unknown': 'Neznámá úroveň'
            }
            
            for i, warning in enumerate(chmi_warnings, 1):
                color_class = f"warning-{warning.color}" if warning.color in ['red', 'orange', 'yellow', 'green'] else "warning-box"
                color_icon = color_emoji.get(warning.color, '⚪')
                color_name = color_names.get(warning.color, 'Neznámá úroveň')
                
                html_content += f"""
                <div class="warning-box {color_class}" style="margin: 10px 0;">
                    <h4>{color_icon} {warning.event}</h4>
                    <p><strong>Úroveň:</strong> {color_name}</p>
                    <p><strong>Platnost:</strong> {warning.time_start_text} - {warning.time_end_text or 'neurčeno'}</p>
                    <p><strong>Stav:</strong> {'🔴 PROBÍHÁ' if warning.in_progress else '🟡 Očekává se'}</p>
                    {f'<p><strong>Popis:</strong> {warning.detailed_text}</p>' if warning.detailed_text else ''}
                    {f'<p><strong>Doporučení:</strong> {warning.instruction}</p>' if warning.instruction else ''}
                </div>
                """
            
            html_content += "</div>"
        else:
            html_content += """
            <div class="chmi-section">
                <h3>🏛️ Oficiální varování ČHMÚ</h3>
                <p>Žádná aktuální varování ČHMÚ pro region Brno.</p>
                <p><em>AI systém detekoval riziko bouře na základě meteorologických dat.</em></p>
            </div>
            """
        
        # Add weather data table
        html_content += """
            <h3>🌡️ Aktuální meteorologické údaje</h3>
        """
        
        if weather_data:
            html_content += """
            <div class="weather-data">
                <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
                    <tr style="background-color: #f8f9fa;">
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Zdroj</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Teplota</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Vlhkost</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Tlak</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Vítr</th>
                        <th style="border: 1px solid #dee2e6; padding: 8px; text-align: left;">Srážky</th>
                    </tr>
            """
            
            for data in weather_data:
                source_name = "OpenWeather" if "openweather" in data.source.lower() else "Visual Crossing"
                html_content += f"""
                    <tr>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{source_name}</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.temperature:.1f}°C</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.humidity:.0f}%</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.pressure:.0f} hPa</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.wind_speed:.1f} m/s ({data.wind_direction}°)</td>
                        <td style="border: 1px solid #dee2e6; padding: 8px;">{data.precipitation:.1f} mm</td>
                    </tr>
                """
            
            html_content += """
                </table>
            """
            
            # Additional detailed information
            latest_data = weather_data[0]
            html_content += f"""
                <div style="margin: 15px 0; padding: 10px; background-color: #f8f9fa; border-radius: 5px;">
                    <h4>🔍 Podrobné údaje</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div><strong>Oblačnost:</strong> {latest_data.cloud_cover:.0f}%</div>
                        <div><strong>Viditelnost:</strong> {latest_data.visibility:.1f} km</div>
                        <div><strong>UV index:</strong> {getattr(latest_data, 'uv_index', 'N/A')}</div>
                        <div><strong>Rosný bod:</strong> {getattr(latest_data, 'dew_point', 'N/A')}°C</div>
                        <div><strong>Pocitová teplota:</strong> {getattr(latest_data, 'feels_like', 'N/A')}°C</div>
                        <div><strong>Podmínky:</strong> {latest_data.description}</div>
                    </div>
                </div>
            """
        else:
            html_content += "<p><em>Meteorologická data nejsou k dispozici.</em></p>"
            
        html_content += f"""
            </div>
            
            <div class="recommendations">
                <h3>💡 Doporučení a opatření</h3>
                <ul>
        """
        
        for recommendation in analysis.recommendations:
            html_content += f"<li>{recommendation}</li>"
        
        # Add ČHMÚ specific recommendations if available
        if chmi_warnings:
            html_content += """
                </ul>
                <h4>🏛️ Oficiální doporučení ČHMÚ:</h4>
                <ul>
            """
            for warning in chmi_warnings:
                if warning.instruction:
                    html_content += f"<li><strong>{warning.event}:</strong> {warning.instruction}</li>"
            
        html_content += f"""
                </ul>
            </div>
            
            <div style="margin: 20px 0; padding: 15px; background-color: #e3f2fd; border-radius: 5px; border-left: 4px solid #2196f3;">
                <h3>🌐 Oficiální meteorologické zdroje</h3>
                <div style="margin: 10px 0;">
                    <h4>🏛️ ČHMÚ - Český hydrometeorologický ústav</h4>
                    <ul style="margin: 5px 0;">
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/meteorologicka-upozorneni" target="_blank" style="color: #1976d2; text-decoration: none;">📢 Meteorologická upozornění a varování</a></li>
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/radar" target="_blank" style="color: #1976d2; text-decoration: none;">🌧️ Meteorologický radar</a></li>
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/predpoved-pocasi" target="_blank" style="color: #1976d2; text-decoration: none;">🌤️ Předpověď počasí</a></li>
                        <li><a href="https://www.chmi.cz/aktualni-situace/aktualni-stav-pocasi/ceska-republika/bourkova-aktivita" target="_blank" style="color: #1976d2; text-decoration: none;">⚡ Bouřková aktivita</a></li>
                    </ul>
                </div>
                
                <div style="margin: 10px 0;">
                    <h4>🌍 Další užitečné zdroje</h4>
                    <ul style="margin: 5px 0;">
                        <li><a href="https://www.windy.com/?49.238,16.607,8" target="_blank" style="color: #1976d2; text-decoration: none;">🌬️ Windy.com - Interaktivní mapa počasí</a></li>
                        <li><a href="https://www.lightningmaps.org/?lang=cs#m=oss;t=3;s=0;o=0;b=;ts=0;" target="_blank" style="color: #1976d2; text-decoration: none;">⚡ Mapa blesků v reálném čase</a></li>
                        <li><a href="https://www.yr.no/en/forecast/graph/2-3078610/Czech%20Republic/South%20Moravian%20Region/Brno" target="_blank" style="color: #1976d2; text-decoration: none;">📊 Yr.no - Podrobná předpověď</a></li>
                    </ul>
                </div>
                
                <div style="background-color: #fff3cd; padding: 10px; border-radius: 3px; margin-top: 10px;">
                    <strong>⚠️ Důležité:</strong> Toto varování kombinuje AI analýzu s oficiálními daty ČHMÚ. V případě rozporu se řiďte oficiálními varováními ČHMÚ.
                </div>
            </div>
            
            <hr>
            <p class="timestamp">Automaticky generováno systémem Clipron AI Weather Detection<br>
            🤖 AI Analýza: DeepSeek Reasoner (spolehlivost {analysis.confidence_score:.1%})<br>
            🏛️ Oficiální data: ČHMÚ XML API<br>
            Čas: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br>
            📍 Lokace: {self.config.weather.city_name}, {self.config.weather.region}<br>
            🔄 Interval monitorování: {self.config.system.monitoring_interval_minutes} minut</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        return msg
    
    def send_combined_weather_alert(self, analysis: StormAnalysis, weather_data: List[WeatherData], chmi_warnings: List[ChmiWarning] = None, pdf_path: Optional[str] = None) -> EmailNotification:
        """Send combined weather alert email with AI analysis and ČHMÚ warnings."""
        notification = EmailNotification(
            timestamp=datetime.now(),
            recipient=self.config.email.recipient_email,
            subject=f"Combined Weather Alert - {analysis.alert_level.value}",
            message_type="combined_weather_alert",
            sent_successfully=False,
            error_message=None
        )
        
        try:
            msg = self._create_combined_weather_alert_email(analysis, weather_data, chmi_warnings)
            
            # Attach PDF report if provided
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= combined_weather_report_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf'
                )
                msg.attach(part)
            
            with self._create_smtp_connection() as server:
                server.send_message(msg)
                
            notification.sent_successfully = True
            logger.info(f"Combined weather alert email sent successfully to {self.config.email.recipient_email}")
            
        except Exception as e:
            notification.error_message = str(e)
            logger.error(f"Failed to send combined weather alert email: {e}")
            
        return notification