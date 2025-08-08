"""PDF report generation for weather analysis."""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import numpy as np

from models import WeatherData, StormAnalysis
from config import Config

logger = logging.getLogger(__name__)

class WeatherReportGenerator:
    """Generates detailed PDF reports for weather analysis."""
    
    def __init__(self, config: Config):
        """Initialize PDF generator."""
        self.config = config
        self.styles = getSampleStyleSheet()
        self.reports_dir = "reports"
        
        # Create reports directory if it doesn't exist
        os.makedirs(self.reports_dir, exist_ok=True)
        
        # Custom styles
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            textColor=colors.darkblue
        )
        
        self.heading_style = ParagraphStyle(
            'CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.darkgreen
        )
    
    def _create_weather_chart_cz(self, weather_data: List[WeatherData], analysis_time: datetime) -> Optional[str]:
        """Vytvoří kombinovaný graf počasí v češtině a uloží ho jako obrázek."""
        if not weather_data or len(weather_data) < 2:
            return None

        df = pd.DataFrame([vars(d) for d in weather_data])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').set_index('timestamp')

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax1 = plt.subplots(figsize=(12, 6.75))

        # Teplota a Srážky (levá osa Y)
        ax1.set_xlabel('Čas (posledních 24 hodin)', fontsize=12)
        ax1.set_ylabel('Teplota (°C) / Srážky (mm)', fontsize=12, color='#d62728')
        ax1.plot(df.index, df['temperature'], color='#d62728', marker='o', linestyle='-', label='Teplota')
        ax1.tick_params(axis='y', labelcolor='#d62728')
        ax1.axhline(0, color='blue', linestyle='--', linewidth=1, label='Bod mrazu')

        # Srážky jako sloupcový graf
        ax1.bar(df.index, df['precipitation'], width=0.01, color='#1f77b4', alpha=0.6, label='Srážky')

        # Tlak (pravá osa Y)
        ax2 = ax1.twinx()
        ax2.set_ylabel('Tlak (hPa)', fontsize=12, color='#2ca02c')
        ax2.plot(df.index, df['pressure'], color='#2ca02c', marker='s', linestyle='--', label='Tlak')
        ax2.tick_params(axis='y', labelcolor='#2ca02c')

        # Formátování a titulky
        plt.title(f'Vývoj počasí předcházející analýze ze dne {analysis_time.strftime("%d.%m.%Y %H:%M")}', fontsize=16, fontweight='bold')
        fig.legend(loc="upper right", bbox_to_anchor=(1,1), bbox_transform=ax1.transAxes)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.xticks(rotation=45)
        fig.tight_layout()

        chart_path = os.path.join(self.reports_dir, f"combined_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(chart_path, dpi=300)
        plt.close(fig)

        return chart_path

    def create_chart_image(self, weather_data: List[WeatherData], title_time: datetime) -> Optional[str]:
        """Public wrapper to create and return path to a weather chart PNG for messaging apps."""
        try:
            return self._create_weather_chart_cz(weather_data, title_time)
        except Exception as e:
            logger.error(f"Failed to create chart image: {e}")
            return None
    
    def _create_weather_summary_table(self, weather_data: List[WeatherData]) -> List[List[str]]:
        """Create summary table data for weather conditions."""
        if not weather_data:
            return [["No data available"]]
            
        # Get latest data from each source
        sources = {}
        for data in weather_data:
            if data.source not in sources or data.timestamp > sources[data.source].timestamp:
                sources[data.source] = data
        
        table_data = [["Metric", "OpenWeather", "Visual Crossing", "Average"]]
        
        if len(sources) >= 2:
            ow_data = sources.get("openweather")
            vc_data = sources.get("visual_crossing")
            
            # Temperature
            temp_avg = (ow_data.temperature + vc_data.temperature) / 2 if ow_data and vc_data else "N/A"
            table_data.append([
                "Temperature (°C)",
                f"{ow_data.temperature:.1f}" if ow_data else "N/A",
                f"{vc_data.temperature:.1f}" if vc_data else "N/A",
                f"{temp_avg:.1f}" if isinstance(temp_avg, float) else temp_avg
            ])
            
            # Humidity
            hum_avg = (ow_data.humidity + vc_data.humidity) / 2 if ow_data and vc_data else "N/A"
            table_data.append([
                "Humidity (%)",
                f"{ow_data.humidity:.0f}" if ow_data else "N/A",
                f"{vc_data.humidity:.0f}" if vc_data else "N/A",
                f"{hum_avg:.0f}" if isinstance(hum_avg, float) else hum_avg
            ])
            
            # Pressure
            press_avg = (ow_data.pressure + vc_data.pressure) / 2 if ow_data and vc_data else "N/A"
            table_data.append([
                "Pressure (hPa)",
                f"{ow_data.pressure:.0f}" if ow_data else "N/A",
                f"{vc_data.pressure:.0f}" if vc_data else "N/A",
                f"{press_avg:.0f}" if isinstance(press_avg, float) else press_avg
            ])
            
            # Wind Speed
            wind_avg = (ow_data.wind_speed + vc_data.wind_speed) / 2 if ow_data and vc_data else "N/A"
            table_data.append([
                "Wind Speed (m/s)",
                f"{ow_data.wind_speed:.1f}" if ow_data else "N/A",
                f"{vc_data.wind_speed:.1f}" if vc_data else "N/A",
                f"{wind_avg:.1f}" if isinstance(wind_avg, float) else wind_avg
            ])
            
        return table_data
    
    def generate_storm_report(self, analysis: StormAnalysis, weather_data: List[WeatherData]) -> str:
        """Generuje detailní PDF report o analýze bouřky v češtině."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"storm_report_{timestamp}.pdf"
        filepath = os.path.join(self.reports_dir, filename)
        
        try:
            doc = SimpleDocTemplate(filepath, pagesize=A4, topMargin=0.8*inch, bottomMargin=0.8*inch, leftMargin=0.8*inch, rightMargin=0.8*inch)
            story = []
            
            # Titulek
            title_text = f"Zpráva o analýze bouřky - {self.config.weather.city_name}"
            story.append(Paragraph(title_text, self.title_style))
            story.append(Spacer(1, 15))
            
            # Informace o reportu
            report_info = f"""
            <b>Vytvořeno:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}<br/>
            <b>Lokalita:</b> {self.config.weather.city_name}, {self.config.weather.region}<br/>
            <b>Souřadnice:</b> {self.config.weather.latitude:.4f}, {self.config.weather.longitude:.4f}<br/>
            <b>Čas analýzy:</b> {analysis.timestamp.strftime('%d.%m.%Y %H:%M:%S')}
            """
            story.append(Paragraph(report_info, self.styles['Normal']))
            story.append(Spacer(1, 15))
            
            # Souhrn detekce bouřky
            story.append(Paragraph("Souhrn detekce bouřky", self.heading_style))
            
            alert_color = colors.red if analysis.storm_detected else colors.green
            detection_text = f"""
            <b>Detekována bouřka:</b> <font color="{alert_color}">{'ANO' if analysis.storm_detected else 'NE'}</font><br/>
            <b>Spolehlivost detekce:</b> {analysis.confidence_score:.1%}<br/>
            <b>Úroveň varování:</b> {analysis.alert_level.value.upper()}<br/>
            """
            
            if analysis.predicted_arrival:
                detection_text += f"<b>Předpokládaný příchod:</b> {analysis.predicted_arrival.strftime('%d.%m.%Y %H:%M')}<br/>"
            if analysis.predicted_intensity:
                detection_text += f"<b>Předpokládaná intenzita:</b> {analysis.predicted_intensity}<br/>"
                
            story.append(Paragraph(detection_text, self.styles['Normal']))
            story.append(Spacer(1, 10))
            
            # Meteorologická analýza
            story.append(Paragraph("Meteorologická analýza", self.heading_style))
            analysis_summary = analysis.analysis_summary.replace('\n', '<br/>')
            story.append(Paragraph(analysis_summary, self.styles['Normal']))
            story.append(Spacer(1, 10))
            
            # Doporučení
            if analysis.recommendations:
                story.append(Paragraph("Doporučení", self.heading_style))
                recommendations_text = "<br/>".join([f"• {rec}" for rec in analysis.recommendations])
                story.append(Paragraph(recommendations_text, self.styles['Normal']))
                story.append(Spacer(1, 10))
            
            # Tabulka aktuálního počasí
            story.append(Paragraph("Aktuální povětrnostní podmínky", self.heading_style))
            
            table_data = self._create_weather_summary_table(weather_data)
            weather_table = Table(table_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            weather_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(weather_table)
            story.append(Spacer(1, 15))
            
            # Graf vývoje počasí
            if len(weather_data) > 1:
                story.append(Paragraph("Graf vývoje počasí (24h)", self.heading_style))
                
                combined_chart = self._create_weather_chart_cz(weather_data, analysis.timestamp)
                if combined_chart and os.path.exists(combined_chart):
                    story.append(Image(combined_chart, width=7*inch, height=3.75*inch))
                    story.append(Spacer(1, 10))
            
            # Posouzení kvality dat
            story.append(Paragraph("Posouzení kvality dat", self.heading_style))
            latest_data_time = max(d.timestamp for d in weather_data) if weather_data else datetime.now()
            quality_text = f"""
            <b>Skóre kvality dat:</b> {analysis.data_quality_score:.1%}<br/>
            <b>Počet zdrojů dat:</b> {len(set(d.source for d in weather_data))}<br/>
            <b>Stáří posledních dat:</b> {(datetime.now() - latest_data_time).total_seconds() / 60:.1f} minut
            """
            story.append(Paragraph(quality_text, self.styles['Normal']))
            
            # Patička
            story.append(Spacer(1, 20))
            footer_text = """
            <i>Tento report byl automaticky vygenerován systémem Clipron AI Weather Detection.<br/>
            V případě dotazů nebo technické podpory kontaktujte správce systému.</i>
            """
            story.append(Paragraph(footer_text, self.styles['Italic']))
            
            # Sestavení PDF
            doc.build(story)
            
            logger.info(f"Storm report generated successfully: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating storm report: {e}")
            return None
        finally:
            # Vyčištění dočasných souborů grafů
            for f in os.listdir(self.reports_dir):
                if f.startswith('combined_chart_') and f.endswith('.png'):
                    try:
                        os.remove(os.path.join(self.reports_dir, f))
                    except OSError as e:
                        logger.warning(f"Could not remove temporary chart file {f}: {e}")
    
    def generate_daily_report(self, weather_data: List[WeatherData], analyses: List[StormAnalysis]) -> str:
        """Generate daily weather summary report."""
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"daily_report_{timestamp}.pdf"
        filepath = os.path.join(self.reports_dir, filename)
        
        try:
            doc = SimpleDocTemplate(filepath, pagesize=A4, topMargin=1*inch, bottomMargin=1*inch)
            story = []
            
            # Title
            title_text = f"Daily Weather Report - {self.config.weather.city_name}"
            story.append(Paragraph(title_text, self.title_style))
            story.append(Spacer(1, 20))
            
            # Report summary
            today = datetime.now().strftime('%d/%m/%Y')
            storm_detections = len([a for a in analyses if a.storm_detected])
            
            summary_text = f"""
            <b>Date:</b> {today}<br/>
            <b>Location:</b> {self.config.weather.city_name}, {self.config.weather.region}<br/>
            <b>Total Monitoring Cycles:</b> {len(analyses)}<br/>
            <b>Storm Detections:</b> {storm_detections}<br/>
            <b>Data Points Collected:</b> {len(weather_data)}
            """
            story.append(Paragraph(summary_text, self.styles['Normal']))
            story.append(Spacer(1, 20))
            
            # Build and return the PDF
            doc.build(story)
            
            logger.info(f"Daily report generated successfully: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating daily report: {e}")
            return None