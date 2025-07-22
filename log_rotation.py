"""Log rotation module for weather monitoring system."""

import os
import logging
import gzip
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

class WeatherLogRotator:
    """Custom log rotator for weather monitoring system."""
    
    def __init__(self, log_file: str = 'weather_monitor.log', max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
        """
        Initialize log rotator.
        
        Args:
            log_file: Path to log file
            max_bytes: Maximum size in bytes before rotation (default: 10MB)
            backup_count: Number of backup files to keep
        """
        self.log_file = log_file
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.logger = logging.getLogger(__name__)
    
    def setup_rotating_logger(self, logger_name: str = None) -> logging.Logger:
        """
        Set up a logger with automatic rotation.
        
        Args:
            logger_name: Name of the logger (default: root logger)
            
        Returns:
            Configured logger with rotation
        """
        logger = logging.getLogger(logger_name)
        
        # Remove existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create rotating file handler
        rotating_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count
        )
        
        # Set format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        rotating_handler.setFormatter(formatter)
        
        # Add console handler for important messages
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        logger.addHandler(rotating_handler)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
        
        return logger
    
    def compress_old_logs(self):
        """
        Compress old log files to save disk space.
        """
        log_dir = Path(self.log_file).parent
        log_name = Path(self.log_file).stem
        
        # Find all rotated log files
        for i in range(1, self.backup_count + 1):
            old_log = log_dir / f"{log_name}.{i}"
            compressed_log = log_dir / f"{log_name}.{i}.gz"
            
            if old_log.exists() and not compressed_log.exists():
                try:
                    with open(old_log, 'rb') as f_in:
                        with gzip.open(compressed_log, 'wb') as f_out:
                            f_out.writelines(f_in)
                    
                    # Remove original file after compression
                    old_log.unlink()
                    self.logger.info(f"Compressed log file: {old_log} -> {compressed_log}")
                    
                except Exception as e:
                    self.logger.error(f"Error compressing log file {old_log}: {e}")
    
    def cleanup_old_compressed_logs(self, max_age_days: int = 30):
        """
        Remove compressed log files older than specified days.
        
        Args:
            max_age_days: Maximum age in days for compressed logs
        """
        log_dir = Path(self.log_file).parent
        cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 3600)
        
        for log_file in log_dir.glob("*.gz"):
            try:
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    self.logger.info(f"Removed old compressed log: {log_file}")
            except Exception as e:
                self.logger.error(f"Error removing old log {log_file}: {e}")
    
    def get_log_stats(self) -> dict:
        """
        Get statistics about log files.
        
        Returns:
            Dictionary with log file statistics
        """
        stats = {
            'current_log_size_mb': 0,
            'total_log_size_mb': 0,
            'backup_files': 0,
            'compressed_files': 0
        }
        
        try:
            log_dir = Path(self.log_file).parent
            log_name = Path(self.log_file).stem
            
            # Current log file
            if Path(self.log_file).exists():
                stats['current_log_size_mb'] = round(
                    Path(self.log_file).stat().st_size / (1024 * 1024), 2
                )
                stats['total_log_size_mb'] += stats['current_log_size_mb']
            
            # Backup files
            for i in range(1, self.backup_count + 1):
                backup_file = log_dir / f"{log_name}.{i}"
                if backup_file.exists():
                    stats['backup_files'] += 1
                    stats['total_log_size_mb'] += round(
                        backup_file.stat().st_size / (1024 * 1024), 2
                    )
            
            # Compressed files
            for compressed_file in log_dir.glob(f"{log_name}.*.gz"):
                stats['compressed_files'] += 1
                stats['total_log_size_mb'] += round(
                    compressed_file.stat().st_size / (1024 * 1024), 2
                )
                
        except Exception as e:
            self.logger.error(f"Error getting log stats: {e}")
        
        return stats
    
    def force_rotation(self):
        """
        Force log rotation immediately.
        """
        try:
            # Get all handlers that are RotatingFileHandler
            for handler in logging.getLogger().handlers:
                if isinstance(handler, RotatingFileHandler):
                    handler.doRollover()
                    self.logger.info("Forced log rotation completed")
                    break
        except Exception as e:
            self.logger.error(f"Error forcing log rotation: {e}")

def setup_weather_logging(log_file: str = 'weather_monitor.log') -> logging.Logger:
    """
    Convenience function to set up weather monitoring logging with rotation.
    
    Args:
        log_file: Path to log file
        
    Returns:
        Configured logger
    """
    rotator = WeatherLogRotator(log_file)
    return rotator.setup_rotating_logger()

def get_log_rotator(log_file: str = 'weather_monitor.log') -> WeatherLogRotator:
    """
    Get a log rotator instance.
    
    Args:
        log_file: Path to log file
        
    Returns:
        WeatherLogRotator instance
    """
    return WeatherLogRotator(log_file)