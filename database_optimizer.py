"""Database optimization module for weather monitoring system."""

import sqlite3
import logging
from typing import List, Dict, Any
from pathlib import Path
import time

class DatabaseOptimizer:
    """Database optimizer for weather monitoring system."""
    
    def __init__(self, db_path: str = 'weather_data.db'):
        """
        Initialize database optimizer.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
    
    def create_indexes(self) -> bool:
        """
        Create database indexes for better performance.
        
        Returns:
            True if successful, False otherwise
        """
        indexes = [
            # Weather data indexes
            "CREATE INDEX IF NOT EXISTS idx_weather_timestamp ON weather_data(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_weather_date ON weather_data(date(timestamp))",
            "CREATE INDEX IF NOT EXISTS idx_weather_temp ON weather_data(temperature)",
            "CREATE INDEX IF NOT EXISTS idx_weather_pressure ON weather_data(pressure)",
            
            # Storm analysis indexes
            "CREATE INDEX IF NOT EXISTS idx_storm_timestamp ON storm_analysis(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_storm_confidence ON storm_analysis(confidence_score)",
            "CREATE INDEX IF NOT EXISTS idx_storm_alert_level ON storm_analysis(alert_level)",
            
            # Email notifications indexes
            "CREATE INDEX IF NOT EXISTS idx_email_timestamp ON email_notifications(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_email_type ON email_notifications(message_type)",
            "CREATE INDEX IF NOT EXISTS idx_email_success ON email_notifications(sent_successfully)",
            
            # System status indexes
            "CREATE INDEX IF NOT EXISTS idx_system_timestamp ON system_status(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_system_component ON system_status(component)",
            "CREATE INDEX IF NOT EXISTS idx_system_status ON system_status(status)",
            
            # Weather condition cache indexes
            "CREATE INDEX IF NOT EXISTS idx_cache_expires ON weather_condition_cache(expires_at)",

            # Storm patterns indexes
            "CREATE INDEX IF NOT EXISTS idx_patterns_recorded_at ON storm_patterns(recorded_at)",
            
            # Weather forecasts indexes
            "CREATE INDEX IF NOT EXISTS idx_forecast_timestamp ON weather_forecasts(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_forecast_date ON weather_forecasts(forecast_date)",
            "CREATE INDEX IF NOT EXISTS idx_forecast_method ON weather_forecasts(method)",
            
            # Enhanced forecasts indexes
            "CREATE INDEX IF NOT EXISTS idx_enhanced_timestamp ON enhanced_forecasts(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_enhanced_date ON enhanced_forecasts(forecast_date)",
            "CREATE INDEX IF NOT EXISTS idx_enhanced_confidence ON enhanced_forecasts(confidence_score)"
        ]
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for index_sql in indexes:
                    start_time = time.time()
                    cursor.execute(index_sql)
                    execution_time = time.time() - start_time
                    
                    index_name = index_sql.split('idx_')[1].split(' ')[0] if 'idx_' in index_sql else 'unknown'
                    self.logger.info(f"Created index {index_name} in {execution_time:.3f}s")
                
                conn.commit()
                self.logger.info("All database indexes created successfully")
                return True
                
        except Exception as e:
            self.logger.error(f"Error creating database indexes: {e}")
            return False
    
    def analyze_database(self) -> bool:
        """
        Analyze database to update statistics for query optimizer.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                start_time = time.time()
                cursor.execute("ANALYZE")
                execution_time = time.time() - start_time
                
                self.logger.info(f"Database analysis completed in {execution_time:.3f}s")
                return True
                
        except Exception as e:
            self.logger.error(f"Error analyzing database: {e}")
            return False
    
    def vacuum_database(self) -> bool:
        """
        Vacuum database to reclaim space and defragment.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get database size before vacuum
            db_size_before = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
            
            with sqlite3.connect(self.db_path) as conn:
                start_time = time.time()
                conn.execute("VACUUM")
                execution_time = time.time() - start_time
                
                # Get database size after vacuum
                db_size_after = Path(self.db_path).stat().st_size
                space_saved = db_size_before - db_size_after
                
                self.logger.info(
                    f"Database vacuum completed in {execution_time:.3f}s. "
                    f"Space saved: {space_saved / 1024 / 1024:.2f} MB"
                )
                return True
                
        except Exception as e:
            self.logger.error(f"Error vacuuming database: {e}")
            return False
    
    def get_table_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all tables.
        
        Returns:
            Dictionary with table statistics
        """
        stats = {}
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all table names
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    table_stats = {
                        'row_count': 0,
                        'size_estimate': 0,
                        'indexes': []
                    }
                    
                    # Get row count
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    table_stats['row_count'] = cursor.fetchone()[0]
                    
                    # Get indexes for this table
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
                        (table,)
                    )
                    table_stats['indexes'] = [row[0] for row in cursor.fetchall()]
                    
                    # Estimate table size (rough calculation)
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = cursor.fetchall()
                    avg_row_size = len(columns) * 50  # Rough estimate
                    table_stats['size_estimate'] = table_stats['row_count'] * avg_row_size
                    
                    stats[table] = table_stats
                    
        except Exception as e:
            self.logger.error(f"Error getting table stats: {e}")
        
        return stats
    
    def get_index_usage(self) -> List[Dict[str, Any]]:
        """
        Get index usage statistics.
        
        Returns:
            List of index usage information
        """
        index_info = []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all indexes
                cursor.execute(
                    "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
                )
                indexes = cursor.fetchall()
                
                for index_name, table_name, sql in indexes:
                    index_info.append({
                        'name': index_name,
                        'table': table_name,
                        'sql': sql
                    })
                    
        except Exception as e:
            self.logger.error(f"Error getting index usage: {e}")
        
        return index_info
    
    def optimize_database(self, full_optimization: bool = False) -> Dict[str, bool]:
        """
        Perform complete database optimization.
        
        Args:
            full_optimization: Whether to perform full optimization including vacuum
            
        Returns:
            Dictionary with optimization results
        """
        results = {
            'indexes_created': False,
            'database_analyzed': False,
            'database_vacuumed': False
        }
        
        self.logger.info("Starting database optimization...")
        
        # Create indexes
        results['indexes_created'] = self.create_indexes()
        
        # Analyze database
        results['database_analyzed'] = self.analyze_database()
        
        # Vacuum database (only if full optimization requested)
        if full_optimization:
            results['database_vacuumed'] = self.vacuum_database()
        
        success_count = sum(results.values())
        total_operations = len(results)
        
        self.logger.info(
            f"Database optimization completed. "
            f"Success: {success_count}/{total_operations} operations"
        )
        
        return results
    
    def check_database_health(self) -> Dict[str, Any]:
        """
        Check database health and integrity.
        
        Returns:
            Dictionary with health check results
        """
        health = {
            'integrity_check': False,
            'foreign_key_check': False,
            'file_exists': False,
            'file_size_mb': 0,
            'table_count': 0,
            'index_count': 0
        }
        
        try:
            # Check if file exists
            if Path(self.db_path).exists():
                health['file_exists'] = True
                health['file_size_mb'] = round(
                    Path(self.db_path).stat().st_size / (1024 * 1024), 2
                )
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Integrity check
                cursor.execute("PRAGMA integrity_check")
                integrity_result = cursor.fetchone()[0]
                health['integrity_check'] = integrity_result == 'ok'
                
                # Foreign key check
                cursor.execute("PRAGMA foreign_key_check")
                fk_errors = cursor.fetchall()
                health['foreign_key_check'] = len(fk_errors) == 0
                
                # Count tables
                cursor.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                health['table_count'] = cursor.fetchone()[0]
                
                # Count indexes
                cursor.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
                )
                health['index_count'] = cursor.fetchone()[0]
                
        except Exception as e:
            self.logger.error(f"Error checking database health: {e}")
        
        return health

def optimize_weather_database(db_path: str = 'weather_data.db', full: bool = False) -> Dict[str, bool]:
    """
    Convenience function to optimize weather database.
    
    Args:
        db_path: Path to database
        full: Whether to perform full optimization
        
    Returns:
        Optimization results
    """
    optimizer = DatabaseOptimizer(db_path)
    return optimizer.optimize_database(full)

def get_database_optimizer(db_path: str = 'weather_data.db') -> DatabaseOptimizer:
    """
    Get a database optimizer instance.
    
    Args:
        db_path: Path to database
        
    Returns:
        DatabaseOptimizer instance
    """
    return DatabaseOptimizer(db_path)