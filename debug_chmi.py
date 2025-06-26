#!/usr/bin/env python3

from chmi_warnings import ChmiWarningParser
import xml.etree.ElementTree as ET
from config import load_config

config = load_config()
parser = ChmiWarningParser(config)
xml_content = parser.fetch_xml_data()
root = ET.fromstring(xml_content)

print('=== VŠECHNA DOSTUPNÁ VAROVÁNÍ ===')
count = 0
for info in root.findall('.//{urn:oasis:names:tc:emergency:cap:1.2}info'):
    language = info.find('language')
    if language is None or language.text != 'cs':
        continue
    
    event = info.find('event')
    if event is None:
        continue
        
    onset = info.find('onset')
    expires = info.find('expires')
    
    print(f'{count+1}. {event.text}')
    if onset: print(f'   Od: {onset.text}')
    if expires: print(f'   Do: {expires.text}')
    
    # Zobrazit všechny oblasti
    for area in info.findall('area'):
        area_desc = area.find('areaDesc')
        if area_desc is not None:
            print(f'   Oblast: {area_desc.text}')
        
        for geocode in area.findall('geocode'):
            value_name = geocode.find('valueName')
            value = geocode.find('value')
            if value_name and value and value_name.text == 'CISORP':
                print(f'   CISORP: {value.text}')
    
    print()
    count += 1
    if count >= 10: 
        break

print(f'Celkem nalezeno {count} varování')