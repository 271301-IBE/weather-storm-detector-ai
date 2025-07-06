#!/usr/bin/env python3
"""Simple CPU and memory monitor for Raspberry Pi optimization."""

import time
import datetime
import json
import os

try:
    import psutil
except ImportError:
    print("psutil not available - CPU monitoring disabled")
    psutil = None

def get_system_stats():
    """Get current system statistics."""
    if psutil is None:
        return {
            'timestamp': datetime.datetime.now().isoformat(),
            'cpu_percent': 0,
            'memory_percent': 0,
            'memory_used_mb': 0,
            'memory_total_mb': 0,
            'disk_percent': 0,
            'disk_used_gb': 0,
            'disk_total_gb': 0,
            'temperature_c': None,
            'load_avg': None,
            'error': 'psutil not available'
        }
    
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Get temperature if available (Raspberry Pi specific)
    temp = None
    try:
        if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000.0
    except:
        pass
    
    return {
        'timestamp': datetime.datetime.now().isoformat(),
        'cpu_percent': cpu_percent,
        'memory_percent': memory.percent,
        'memory_used_mb': memory.used / (1024 * 1024),
        'memory_total_mb': memory.total / (1024 * 1024),
        'disk_percent': disk.percent,
        'disk_used_gb': disk.used / (1024 * 1024 * 1024),
        'disk_total_gb': disk.total / (1024 * 1024 * 1024),
        'temperature_c': temp,
        'load_avg': os.getloadavg() if hasattr(os, 'getloadavg') else None
    }

def monitor_continuous(duration_minutes=10):
    """Monitor system stats continuously."""
    print("📊 CPU & Memory Monitor")
    print("=" * 50)
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    stats_history = []
    
    try:
        while time.time() < end_time:
            stats = get_system_stats()
            stats_history.append(stats)
            
            # Print current stats
            print(f"\r⏰ {datetime.datetime.now().strftime('%H:%M:%S')} | "
                  f"CPU: {stats['cpu_percent']:5.1f}% | "
                  f"RAM: {stats['memory_percent']:5.1f}% | "
                  f"Disk: {stats['disk_percent']:5.1f}% | "
                  f"Temp: {stats['temperature_c']:5.1f}°C" if stats['temperature_c'] else "Temp: N/A", 
                  end='', flush=True)
            
            time.sleep(5)  # Update every 5 seconds
            
    except KeyboardInterrupt:
        print("\n\n🛑 Monitoring stopped by user")
    
    # Calculate averages
    if stats_history:
        avg_cpu = sum(s['cpu_percent'] for s in stats_history) / len(stats_history)
        avg_memory = sum(s['memory_percent'] for s in stats_history) / len(stats_history)
        max_cpu = max(s['cpu_percent'] for s in stats_history)
        max_memory = max(s['memory_percent'] for s in stats_history)
        
        print(f"\n\n📈 Summary ({len(stats_history)} samples):")
        print(f"Average CPU: {avg_cpu:.1f}%")
        print(f"Average Memory: {avg_memory:.1f}%")
        print(f"Peak CPU: {max_cpu:.1f}%")
        print(f"Peak Memory: {max_memory:.1f}%")
        
        # Save stats to file
        with open('system_stats.json', 'w') as f:
            json.dump(stats_history, f, indent=2)
        
        print(f"📁 Stats saved to system_stats.json")

def show_current_stats():
    """Show current system stats once."""
    stats = get_system_stats()
    
    print("📊 Current System Statistics")
    print("=" * 40)
    print(f"🕐 Time: {stats['timestamp']}")
    print(f"🔥 CPU Usage: {stats['cpu_percent']:.1f}%")
    print(f"💾 Memory Usage: {stats['memory_percent']:.1f}% ({stats['memory_used_mb']:.0f}/{stats['memory_total_mb']:.0f} MB)")
    print(f"💿 Disk Usage: {stats['disk_percent']:.1f}% ({stats['disk_used_gb']:.1f}/{stats['disk_total_gb']:.1f} GB)")
    if stats['temperature_c']:
        print(f"🌡️  Temperature: {stats['temperature_c']:.1f}°C")
    if stats['load_avg']:
        print(f"⚡ Load Average: {stats['load_avg'][0]:.2f}, {stats['load_avg'][1]:.2f}, {stats['load_avg'][2]:.2f}")

def check_weather_processes():
    """Check running weather-related processes."""
    print("\n🌤️  Weather System Processes")
    print("=" * 40)
    
    weather_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
            if any(keyword in cmdline.lower() for keyword in ['weather', 'storm', 'scheduler', 'python3']):
                if 'weather' in cmdline.lower() or 'storm' in cmdline.lower() or 'scheduler' in cmdline.lower():
                    weather_processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cpu_percent': proc.info['cpu_percent'],
                        'memory_percent': proc.info['memory_percent'],
                        'cmdline': cmdline[:80] + '...' if len(cmdline) > 80 else cmdline
                    })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if weather_processes:
        for proc in weather_processes:
            print(f"PID {proc['pid']:5d}: {proc['name']:15s} CPU:{proc['cpu_percent']:5.1f}% MEM:{proc['memory_percent']:5.1f}%")
            print(f"         {proc['cmdline']}")
    else:
        print("No weather-related processes found")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'monitor':
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            monitor_continuous(duration)
        elif sys.argv[1] == 'processes':
            check_weather_processes()
        else:
            print("Usage: python3 cpu_monitor.py [monitor [minutes] | processes]")
    else:
        show_current_stats()
        check_weather_processes()