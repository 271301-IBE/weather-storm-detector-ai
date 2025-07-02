#!/usr/bin/env python3

import re

# Real example from the output  
test_data = '{"time":175120ċ69933Ĉ30Ė,"latĆ14.916135ĘlonĆ-1čĠ68982Ęal'

print("Test data:", repr(test_data))
print()

# Let's look for the actual pattern
print("Finding lat:")
lat_start = test_data.find('lat')
if lat_start >= 0:
    print(f"Found 'lat' at position {lat_start}")
    print(f"Text around: {repr(test_data[lat_start-5:lat_start+20])}")

print("\nFinding lon:")  
lon_start = test_data.find('lon')
if lon_start >= 0:
    print(f"Found 'lon' at position {lon_start}")
    print(f"Text around: {repr(test_data[lon_start-5:lon_start+20])}")

# Extract all decimal numbers and try to match them to fields
decimals = re.findall(r'-?\d+\.\d+', test_data)
print(f"\nDecimal numbers found: {decimals}")

# If we find lat and lon, get the first decimal after each
if lat_start >= 0:
    lat_text = test_data[lat_start:]
    lat_decimal = re.search(r'(\d+\.\d+)', lat_text)
    if lat_decimal:
        print(f"Latitude: {lat_decimal.group(1)}")

if lon_start >= 0:
    lon_text = test_data[lon_start:]
    lon_decimal = re.search(r'(-?\d+\.\d+)', lon_text)
    if lon_decimal:
        print(f"Longitude: {lon_decimal.group(1)}")