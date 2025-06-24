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
    
    def _create_weather_chart(self, weather_data: List[WeatherData], chart_type: str = "temperature") -> str:
        """Create weather chart and save as image."""
        if not weather_data:
            return None
            
        # Sort data by timestamp
        weather_data = sorted(weather_data, key=lambda x: x.timestamp)
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        timestamps = [data.timestamp for data in weather_data]
        
        if chart_type == "temperature":
            values = [data.temperature for data in weather_data]
            ax.plot(timestamps, values, 'b-', marker='o', linewidth=2, markersize=4)
            ax.set_ylabel('Temperature (°C)', fontsize=12)
            ax.set_title('Temperature Trend', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            
        elif chart_type == "pressure":
            values = [data.pressure for data in weather_data]
            ax.plot(timestamps, values, 'r-', marker='s', linewidth=2, markersize=4)
            ax.set_ylabel('Pressure (hPa)', fontsize=12)
            ax.set_title('Atmospheric Pressure Trend', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            
        elif chart_type == "humidity":
            values = [data.humidity for data in weather_data]
            ax.plot(timestamps, values, 'g-', marker='^', linewidth=2, markersize=4)
            ax.set_ylabel('Humidity (%)', fontsize=12)
            ax.set_title('Humidity Trend', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            
        elif chart_type == "wind":
            wind_speeds = [data.wind_speed for data in weather_data]
            ax.plot(timestamps, wind_speeds, 'orange', marker='d', linewidth=2, markersize=4)
            ax.set_ylabel('Wind Speed (m/s)', fontsize=12)
            ax.set_title('Wind Speed Trend', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        chart_path = os.path.join(self.reports_dir, f"{chart_type}_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return chart_path
    
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
    
    def generate_storm_report(self, analysis: StormAnalysis, weather_data: List[WeatherData], historical_data: List = None) -> str:
        """Generate detailed PDF report for storm analysis."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"storm_report_{timestamp}.pdf"
        filepath = os.path.join(self.reports_dir, filename)
        
        try:
            doc = SimpleDocTemplate(filepath, pagesize=A4, topMargin=1*inch, bottomMargin=1*inch)
            story = []
            
            # Title
            title_text = f"Storm Analysis Report - {self.config.weather.city_name}"
            story.append(Paragraph(title_text, self.title_style))
            story.append(Spacer(1, 20))
            
            # Report info
            report_info = f"""
            <b>Generated:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}<br/>
            <b>Location:</b> {self.config.weather.city_name}, {self.config.weather.region}<br/>
            <b>Coordinates:</b> {self.config.weather.latitude:.4f}, {self.config.weather.longitude:.4f}<br/>
            <b>Analysis Time:</b> {analysis.timestamp.strftime('%d/%m/%Y %H:%M:%S')}
            """
            story.append(Paragraph(report_info, self.styles['Normal']))
            story.append(Spacer(1, 20))
            
            # Storm Detection Summary
            story.append(Paragraph("Storm Detection Summary", self.heading_style))
            
            alert_color = colors.red if analysis.storm_detected else colors.green
            detection_text = f"""
            <b>Storm Detected:</b> <font color="{alert_color}">{'YES' if analysis.storm_detected else 'NO'}</font><br/>
            <b>Confidence Score:</b> {analysis.confidence_score:.1%}<br/>
            <b>Alert Level:</b> {analysis.alert_level.value.upper()}<br/>
            """
            
            if analysis.predicted_arrival:
                detection_text += f"<b>Predicted Arrival:</b> {analysis.predicted_arrival.strftime('%d/%m/%Y %H:%M')}<br/>"
            if analysis.predicted_intensity:
                detection_text += f"<b>Predicted Intensity:</b> {analysis.predicted_intensity}<br/>"
                
            story.append(Paragraph(detection_text, self.styles['Normal']))
            story.append(Spacer(1, 15))
            
            # Analysis Summary
            story.append(Paragraph("Meteorological Analysis", self.heading_style))
            story.append(Paragraph(analysis.analysis_summary, self.styles['Normal']))
            story.append(Spacer(1, 15))
            
            # Recommendations
            if analysis.recommendations:
                story.append(Paragraph("Recommendations", self.heading_style))
                recommendations_text = "<br/>".join([f"• {rec}" for rec in analysis.recommendations])
                story.append(Paragraph(recommendations_text, self.styles['Normal']))
                story.append(Spacer(1, 15))
            
            # Current Weather Data Table
            story.append(Paragraph("Current Weather Conditions", self.heading_style))
            
            table_data = self._create_weather_summary_table(weather_data)
            weather_table = Table(table_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            weather_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(weather_table)
            story.append(Spacer(1, 20))
            
            # Add weather charts if enough data
            if len(weather_data) > 1:
                story.append(Paragraph("Weather Trends", self.heading_style))
                
                # Create charts
                temp_chart = self._create_weather_chart(weather_data, "temperature")
                if temp_chart and os.path.exists(temp_chart):
                    story.append(Image(temp_chart, width=6*inch, height=3*inch))
                    story.append(Spacer(1, 10))
                
                pressure_chart = self._create_weather_chart(weather_data, "pressure")
                if pressure_chart and os.path.exists(pressure_chart):
                    story.append(Image(pressure_chart, width=6*inch, height=3*inch))
                    story.append(Spacer(1, 10))
            
            # Data Quality Assessment
            story.append(Paragraph("Data Quality Assessment", self.heading_style))
            quality_text = f"""
            <b>Data Quality Score:</b> {analysis.data_quality_score:.1%}<br/>
            <b>Number of Data Sources:</b> {len(weather_data)}<br/>
            <b>Latest Data Age:</b> {(datetime.now() - max(data.timestamp for data in weather_data) if weather_data else datetime.now()).total_seconds() / 60:.1f} minutes
            """
            story.append(Paragraph(quality_text, self.styles['Normal']))
            
            # Footer
            story.append(Spacer(1, 30))
            footer_text = """
            <i>This report was automatically generated by the Clipron AI Weather Detection System.<br/>
            For questions or technical support, please contact the system administrator.</i>
            """
            story.append(Paragraph(footer_text, self.styles['Normal']))
            
            # Build PDF
            doc.build(story)
            
            logger.info(f"Storm report generated successfully: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating storm report: {e}")
            return None
        finally:
            # Clean up chart files
            for chart_type in ["temperature", "pressure", "humidity", "wind"]:
                chart_files = [f for f in os.listdir(self.reports_dir) if f.startswith(f"{chart_type}_chart_")]
                for chart_file in chart_files:
                    try:
                        os.remove(os.path.join(self.reports_dir, chart_file))
                    except:
                        pass
    
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