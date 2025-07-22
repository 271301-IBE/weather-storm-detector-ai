"""System monitoring module for tracking CPU and memory usage history."""

import psutil
import sqlite3
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class SystemMetrics:
    """System metrics data class."""
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    cpu_temperature: Optional[float] = None
    disk_usage: Optional[float] = None
    network_bytes_sent: Optional[int] = None
    network_bytes_recv: Optional[int] = None

class SystemMonitor:
    """System monitor for tracking hardware metrics."""
    
    def __init__(self, db_path: str = 'weather_data.db', collection_interval: int = 60):
        """
        Initialize system monitor.
        
        Args:
            db_path: Path to SQLite database
            collection_interval: Interval in seconds between metric collections
        """
        self.db_path = db_path
        self.collection_interval = collection_interval
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.monitor_thread = None
        self._init_database()
    
    def _init_database(self):
        """Initialize system metrics table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME NOT NULL,
                        cpu_usage REAL NOT NULL,
                        memory_usage REAL NOT NULL,
                        cpu_temperature REAL,
                        disk_usage REAL,
                        network_bytes_sent INTEGER,
                        network_bytes_recv INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create index for timestamp
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_system_metrics_timestamp 
                    ON system_metrics(timestamp)
                """)
                
                conn.commit()
                self.logger.info("System metrics table initialized")
                
        except Exception as e:
            self.logger.error(f"Error initializing system metrics database: {e}")
    
    def get_cpu_temperature(self) -> Optional[float]:
        """Get CPU temperature if available."""
        try:
            # Try different methods to get CPU temperature
            if hasattr(psutil, 'sensors_temperatures'):
                temps = psutil.sensors_temperatures()
                
                # Try common temperature sensor names
                for sensor_name in ['cpu_thermal', 'coretemp', 'k10temp', 'acpi']:
                    if sensor_name in temps:
                        for temp in temps[sensor_name]:
                            if temp.current:
                                return round(temp.current, 1)
                
                # If no specific sensor found, try the first available
                for sensor_temps in temps.values():
                    for temp in sensor_temps:
                        if temp.current:
                            return round(temp.current, 1)
            
            # Raspberry Pi specific temperature reading
            try:
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temp = int(f.read().strip()) / 1000.0
                    return round(temp, 1)
            except (FileNotFoundError, PermissionError):
                pass
                
        except Exception as e:
            self.logger.debug(f"Could not read CPU temperature: {e}")
        
        return None
    
    def collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        try:
            # CPU usage
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            
            # CPU temperature
            cpu_temp = self.get_cpu_temperature()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            
            # Network statistics
            network = psutil.net_io_counters()
            network_sent = network.bytes_sent
            network_recv = network.bytes_recv
            
            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                cpu_temperature=cpu_temp,
                disk_usage=disk_usage,
                network_bytes_sent=network_sent,
                network_bytes_recv=network_recv
            )
            
        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")
            # Return basic metrics even if some fail
            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_usage=psutil.cpu_percent(),
                memory_usage=psutil.virtual_memory().percent
            )
    
    def store_metrics(self, metrics: SystemMetrics):
        """Store metrics in database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO system_metrics 
                    (timestamp, cpu_usage, memory_usage, cpu_temperature, 
                     disk_usage, network_bytes_sent, network_bytes_recv)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    metrics.timestamp,
                    metrics.cpu_usage,
                    metrics.memory_usage,
                    metrics.cpu_temperature,
                    metrics.disk_usage,
                    metrics.network_bytes_sent,
                    metrics.network_bytes_recv
                ))
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Error storing system metrics: {e}")
    
    def get_metrics_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get system metrics history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                since_time = datetime.now() - timedelta(hours=hours)
                
                cursor.execute("""
                    SELECT timestamp, cpu_usage, memory_usage, cpu_temperature,
                           disk_usage, network_bytes_sent, network_bytes_recv
                    FROM system_metrics 
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                """, (since_time,))
                
                rows = cursor.fetchall()
                
                metrics = []
                for row in rows:
                    metrics.append({
                        'timestamp': row[0],
                        'cpu_usage': row[1],
                        'memory_usage': row[2],
                        'cpu_temperature': row[3],
                        'disk_usage': row[4],
                        'network_bytes_sent': row[5],
                        'network_bytes_recv': row[6]
                    })
                
                return metrics
                
        except Exception as e:
            self.logger.error(f"Error getting metrics history: {e}")
            return []
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics as dictionary."""
        metrics = self.collect_metrics()
        return {
            'timestamp': metrics.timestamp.isoformat(),
            'cpu_usage': metrics.cpu_usage,
            'memory_usage': metrics.memory_usage,
            'cpu_temperature': metrics.cpu_temperature,
            'disk_usage': metrics.disk_usage,
            'network_bytes_sent': metrics.network_bytes_sent,
            'network_bytes_recv': metrics.network_bytes_recv
        }
    
    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get summary statistics for metrics."""
        history = self.get_metrics_history(hours)
        
        if not history:
            return {}
        
        cpu_values = [m['cpu_usage'] for m in history if m['cpu_usage'] is not None]
        memory_values = [m['memory_usage'] for m in history if m['memory_usage'] is not None]
        temp_values = [m['cpu_temperature'] for m in history if m['cpu_temperature'] is not None]
        
        summary = {
            'period_hours': hours,
            'data_points': len(history),
            'cpu_usage': {
                'current': cpu_values[-1] if cpu_values else None,
                'average': round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else None,
                'max': max(cpu_values) if cpu_values else None,
                'min': min(cpu_values) if cpu_values else None
            },
            'memory_usage': {
                'current': memory_values[-1] if memory_values else None,
                'average': round(sum(memory_values) / len(memory_values), 1) if memory_values else None,
                'max': max(memory_values) if memory_values else None,
                'min': min(memory_values) if memory_values else None
            }
        }
        
        if temp_values:
            summary['cpu_temperature'] = {
                'current': temp_values[-1],
                'average': round(sum(temp_values) / len(temp_values), 1),
                'max': max(temp_values),
                'min': min(temp_values)
            }
        
        return summary
    
    def cleanup_old_metrics(self, days: int = 30):
        """Remove old metrics data."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cutoff_time = datetime.now() - timedelta(days=days)
                
                cursor.execute(
                    "DELETE FROM system_metrics WHERE timestamp < ?",
                    (cutoff_time,)
                )
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    self.logger.info(f"Cleaned up {deleted_count} old system metrics records")
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old metrics: {e}")
    
    def _monitor_loop(self):
        """Main monitoring loop running in separate thread."""
        self.logger.info(f"System monitoring started (interval: {self.collection_interval}s)")
        
        while self.running:
            try:
                # Collect and store metrics
                metrics = self.collect_metrics()
                self.store_metrics(metrics)
                
                # Log current metrics periodically
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    self.logger.info(
                        f"System metrics - CPU: {metrics.cpu_usage}%, "
                        f"Memory: {metrics.memory_usage}%, "
                        f"Temp: {metrics.cpu_temperature}°C"
                    )
                
                # Wait for next collection
                time.sleep(self.collection_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.collection_interval)
    
    def start_monitoring(self):
        """Start system monitoring in background thread."""
        if self.running:
            self.logger.warning("System monitoring is already running")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("System monitoring started")
    
    def stop_monitoring(self):
        """Stop system monitoring."""
        if not self.running:
            return
        
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        self.logger.info("System monitoring stopped")
    
    def is_running(self) -> bool:
        """Check if monitoring is running."""
        return self.running and self.monitor_thread and self.monitor_thread.is_alive()

# Global system monitor instance
_system_monitor = None

def get_system_monitor(db_path: str = 'weather_data.db') -> SystemMonitor:
    """Get global system monitor instance."""
    global _system_monitor
    if _system_monitor is None:
        _system_monitor = SystemMonitor(db_path)
    return _system_monitor

def start_system_monitoring(db_path: str = 'weather_data.db', interval: int = 60):
    """Start system monitoring."""
    monitor = get_system_monitor(db_path)
    monitor.collection_interval = interval
    monitor.start_monitoring()

def stop_system_monitoring():
    """Stop system monitoring."""
    global _system_monitor
    if _system_monitor:
        _system_monitor.stop_monitoring()