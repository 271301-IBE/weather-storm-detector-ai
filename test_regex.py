#!/usr/bin/env python3

import re

# Real example from the output
test_data = '{"time":175120ċ69933Ĉ30Ė,"latĆ14.916135ĘlonĆ-1čĠ68982Ęal'

print("Test data:", repr(test_data))
print()

# Extract timestamp
time_match = re.search(r'"time"\s*:\s*(\d+[^\d,\s]*\d*)', test_data)
if time_match:
    print("Time raw:", repr(time_match.group(1)))
    timestamp_str = re.sub(r'[^\d]', '', time_match.group(1))
    print("Time cleaned:", timestamp_str)

# Extract latitude
lat_match = re.search(r'"lat".*?(\d+\.\d+)', test_data)
if lat_match:
    print("Lat match:", lat_match.group(1))
else:
    print("Lat match: None")

# Extract longitude  
lon_match = re.search(r'"lon".*?(-?\d+\.\d+)', test_data)
if lon_match:
    print("Lon match:", lon_match.group(1))
else:
    print("Lon match: None")

# Let's try a more robust approach - extract ALL decimal numbers
print("\nAll decimal numbers found:")
all_decimals = re.findall(r'-?\d+\.\d+', test_data)
print(all_decimals)

# Check specifically around lat and lon
lat_pos = test_data.find('"lat"')
lon_pos = test_data.find('"lon"')
print(f"\nLat position: {lat_pos}")
print(f"Text around lat: {repr(test_data[lat_pos:lat_pos+30])}")
print(f"Lon position: {lon_pos}")  
print(f"Text around lon: {repr(test_data[lon_pos:lon_pos+30])}")