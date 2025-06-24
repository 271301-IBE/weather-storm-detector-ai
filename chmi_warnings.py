#!/usr/bin/env python3
"""
ČHMÚ Warning Integration Module

Integrates official ČHMÚ (Czech Hydrometeorological Institute) warnings
into the weather monitoring system. Monitors official weather warnings
for Brno (CISORP code 6203) and sends email notifications when new
warnings are issued.

This module parses CAP (Common Alerting Protocol) XML data from ČHMÚ
and provides change detection to avoid duplicate notifications.
"""

import xml.etree.ElementTree as ET
import requests
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import time

logger = logging.getLogger(__name__)

@dataclass
class ChmiWarning:
    """Represents a ČHMÚ weather warning."""
    identifier: str
    event: str
    detailed_text: str
    instruction: str
    time_start_iso: str
    time_end_iso: Optional[str]
    time_start_unix: int
    time_end_unix: Optional[int]
    time_start_text: str
    time_end_text: Optional[str]
    response_type: str
    urgency: str
    severity: str
    certainty: str
    color: str
    warning_type: str
    in_progress: bool
    area_description: str

class ChmiWarningParser:
    """Parser for ČHMÚ CAP XML warnings."""
    
    def __init__(self, region_code: str = "6203"):
        """
        Initialize parser.
        
        Args:
            region_code: CISORP code for the region (6203 for Brno)
        """
        self.region_code = region_code
        self.xml_url = "https://www.chmi.cz/files/portal/docs/meteo/om/bulletiny/XOCZ50_OKPR.xml"
        self.state_file = Path("./chmi_warnings_state.json")
        
        # Czech day names for human-readable dates
        self.day_names = ['', 'po', 'út', 'st', 'čt', 'pá', 'so', 'ne']
        
        # Warning type mapping from ČHMÚ codes
        self.warning_types = {
            '1': 'Wind',
            '2': 'snow-ice', 
            '3': 'Thunderstorm',
            '4': 'Fog',
            '5': 'high-temperature',
            '6': 'low-temperature',
            '7': 'coastalevent',
            '8': 'forest-fire',
            '9': 'avalanches',
            '10': 'Rain',
            '11': 'unknown',
            '12': 'flooding',
            '13': 'rain-flood'
        }
        
        # Color mapping from awareness levels
        self.color_mapping = {
            '1': 'green',
            '2': 'yellow', 
            '3': 'orange',
            '4': 'red'
        }
    
    def fetch_xml_data(self) -> str:
        """
        Fetch ČHMÚ XML data from official source.
        
        Returns:
            XML content as string
            
        Raises:
            requests.RequestException: If download fails
        """
        try:
            response = requests.get(self.xml_url, timeout=30)
            response.raise_for_status()
            
            # Validate minimum expected size (original PHP checks 700KB)
            if len(response.content) < 700000:
                raise ValueError(f"Downloaded file too small: {len(response.content)} bytes")
            
            logger.debug(f"Successfully downloaded ČHMÚ XML: {len(response.content)} bytes")
            return response.content.decode('utf-8')
            
        except requests.RequestException as e:
            logger.error(f"Failed to download ČHMÚ XML: {e}")
            raise
        except Exception as e:
            logger.error(f"Error processing ČHMÚ XML: {e}")
            raise
    
    def format_czech_datetime(self, dt: datetime) -> str:
        """
        Format datetime in Czech-friendly format.
        
        Args:
            dt: Datetime object
            
        Returns:
            Human-readable Czech datetime string
        """
        today = datetime.now()
        date_str = dt.strftime('%Y-%m-%d')
        today_str = today.strftime('%Y-%m-%d')
        tomorrow_str = (today.replace(day=today.day + 1)).strftime('%Y-%m-%d')
        
        if date_str == today_str:
            return f"dnes {dt.strftime('%H:%M')}"
        elif date_str == tomorrow_str:
            return f"zítra {dt.strftime('%H:%M')}"
        else:
            day_name = self.day_names[dt.weekday() + 1]
            return f"{day_name} {dt.strftime('%-d.%-m. %H:%M')}"
    
    def parse_warning_info(self, info_element: ET.Element) -> Optional[ChmiWarning]:
        """
        Parse individual warning info element.
        
        Args:
            info_element: XML info element
            
        Returns:
            ChmiWarning object or None if not applicable
        """
        try:
            # Check if this is a Czech warning and not a clearance
            language = info_element.find('language')
            if language is None or language.text != 'cs':
                return None
            
            response_type = info_element.find('responseType')
            if response_type is not None and response_type.text in ['None', 'AllClear']:
                return None
            
            # Check if warning applies to our region
            if not self._applies_to_region(info_element):
                return None
            
            # Extract basic information
            event = self._get_text(info_element, 'event', 'Neznámá výstraha')
            description = self._get_text(info_element, 'description', '')
            instruction = self._get_text(info_element, 'instruction', '')
            
            # Parse timing
            onset = info_element.find('onset')
            expires = info_element.find('expires')
            
            if onset is None:
                logger.warning("Warning missing onset time, skipping")
                return None
            
            time_start = datetime.fromisoformat(onset.text.replace('Z', '+00:00'))
            time_end = None
            if expires is not None:
                time_end = datetime.fromisoformat(expires.text.replace('Z', '+00:00'))
            
            # Check for eventEndingTime parameter
            for param in info_element.findall('parameter'):
                value_name = param.find('valueName')
                if value_name is not None and value_name.text == 'eventEndingTime':
                    value = param.find('value')
                    if value is not None:
                        time_end = datetime.fromisoformat(value.text.replace('Z', '+00:00'))
            
            # Skip warnings that ended more than 4 hours ago
            if time_end and time_end.timestamp() < (time.time() - 4 * 3600):
                logger.debug(f"Warning already ended, skipping: {event}")
                return None
            
            # Extract warning classification
            urgency = self._get_text(info_element, 'urgency', 'Unknown')
            severity = self._get_text(info_element, 'severity', 'Unknown') 
            certainty = self._get_text(info_element, 'certainty', 'Unknown')
            response_type_text = response_type.text if response_type is not None else 'Unknown'
            
            # Parse awareness level and type from parameters
            color = 'unknown'
            warning_type = 'unknown'
            
            for param in info_element.findall('parameter'):
                value_name = param.find('valueName')
                if value_name is None:
                    continue
                    
                value = param.find('value')
                if value is None:
                    continue
                
                if value_name.text == 'awareness_level':
                    # Format: "2; yellow; Moderate"
                    parts = value.text.split(';')
                    if len(parts) >= 2:
                        color = parts[1].strip()
                
                elif value_name.text == 'awareness_type':
                    # Format: "3; Thunderstorm"
                    parts = value.text.split(';')
                    if len(parts) >= 2:
                        warning_type = parts[1].strip()
                    elif len(parts) == 1 and parts[0].strip() in self.warning_types:
                        warning_type = self.warning_types[parts[0].strip()]
            
            # Determine if warning is currently in progress
            now = time.time()
            in_progress = (time_start.timestamp() <= now and 
                          (time_end is None or time_end.timestamp() >= now))
            
            # Get area description
            area_desc = "Jihomoravský kraj"
            area = info_element.find('area/areaDesc')
            if area is not None:
                area_desc = area.text
            
            # Create identifier from multiple sources
            identifier_elem = info_element.find('../identifier')
            identifier = identifier_elem.text if identifier_elem is not None else f"chmi_{int(time_start.timestamp())}"
            
            return ChmiWarning(
                identifier=identifier,
                event=event,
                detailed_text=description,
                instruction=instruction,
                time_start_iso=onset.text,
                time_end_iso=expires.text if expires is not None else None,
                time_start_unix=int(time_start.timestamp()),
                time_end_unix=int(time_end.timestamp()) if time_end else None,
                time_start_text=self.format_czech_datetime(time_start),
                time_end_text=self.format_czech_datetime(time_end) if time_end else None,
                response_type=response_type_text,
                urgency=urgency,
                severity=severity,
                certainty=certainty,
                color=color,
                warning_type=warning_type,
                in_progress=in_progress,
                area_description=area_desc
            )
            
        except Exception as e:
            logger.error(f"Error parsing warning info: {e}")
            return None
    
    def _applies_to_region(self, info_element: ET.Element) -> bool:
        """Check if warning applies to our region (CISORP code)."""
        for area in info_element.findall('area'):
            for geocode in area.findall('geocode'):
                value_name = geocode.find('valueName')
                value = geocode.find('value')
                
                if (value_name is not None and value_name.text == 'CISORP' and
                    value is not None and value.text == self.region_code):
                    return True
        return False
    
    def _get_text(self, element: ET.Element, tag: str, default: str = '') -> str:
        """Safely get text from XML element."""
        child = element.find(tag)
        return child.text if child is not None and child.text else default
    
    def parse_xml(self, xml_content: str) -> List[ChmiWarning]:
        """
        Parse ČHMÚ XML and extract warnings for our region.
        
        Args:
            xml_content: Raw XML content
            
        Returns:
            List of applicable ChmiWarning objects
        """
        try:
            root = ET.fromstring(xml_content)
            warnings = []
            
            # Find all info elements in the CAP XML
            for info in root.findall('.//{urn:oasis:names:tc:emergency:cap:1.2}info'):
                warning = self.parse_warning_info(info)
                if warning:
                    warnings.append(warning)
                    logger.debug(f"Parsed warning: {warning.event} - {warning.color}")
            
            logger.info(f"Parsed {len(warnings)} applicable warnings for region {self.region_code}")
            return warnings
            
        except ET.ParseError as e:
            logger.error(f"Failed to parse ČHMÚ XML: {e}")
            raise
        except Exception as e:
            logger.error(f"Error processing ČHMÚ warnings: {e}")
            raise
    
    def load_state(self) -> Dict[str, Any]:
        """Load previous warning state from file."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load warning state: {e}")
        
        return {"last_check": 0, "warnings": {}}
    
    def save_state(self, warnings: List[ChmiWarning]) -> None:
        """Save current warning state to file."""
        try:
            state = {
                "last_check": int(time.time()),
                "warnings": {}
            }
            
            for warning in warnings:
                state["warnings"][warning.identifier] = {
                    "event": warning.event,
                    "color": warning.color,
                    "time_start": warning.time_start_unix,
                    "hash": self._calculate_warning_hash(warning)
                }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Could not save warning state: {e}")
    
    def _calculate_warning_hash(self, warning: ChmiWarning) -> str:
        """Calculate hash of warning content for change detection."""
        content = f"{warning.event}|{warning.detailed_text}|{warning.color}|{warning.time_start_unix}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def detect_new_warnings(self, current_warnings: List[ChmiWarning]) -> List[ChmiWarning]:
        """
        Detect new warnings by comparing with saved state.
        
        Args:
            current_warnings: List of current warnings
            
        Returns:
            List of new warnings that should trigger notifications
        """
        previous_state = self.load_state()
        previous_warnings = previous_state.get("warnings", {})
        
        new_warnings = []
        
        for warning in current_warnings:
            warning_id = warning.identifier
            warning_hash = self._calculate_warning_hash(warning)
            
            # Check if this is a completely new warning
            if warning_id not in previous_warnings:
                new_warnings.append(warning)
                logger.info(f"New warning detected: {warning.event}")
                continue
            
            # Check if warning content has changed significantly
            previous_hash = previous_warnings[warning_id].get("hash", "")
            if warning_hash != previous_hash:
                new_warnings.append(warning)
                logger.info(f"Warning updated: {warning.event}")
        
        return new_warnings
    
    def get_current_warnings(self) -> List[ChmiWarning]:
        """
        Fetch and parse current ČHMÚ warnings.
        
        Returns:
            List of current warnings for the region
        """
        xml_content = self.fetch_xml_data()
        return self.parse_xml(xml_content)

class ChmiWarningMonitor:
    """High-level monitor for ČHMÚ warnings with change detection."""
    
    def __init__(self, region_code: str = "6203"):
        self.parser = ChmiWarningParser(region_code)
    
    def check_for_new_warnings(self) -> List[ChmiWarning]:
        """
        Check for new ČHMÚ warnings and return any new ones.
        
        Returns:
            List of new warnings that should trigger notifications
        """
        try:
            # Get current warnings
            current_warnings = self.parser.get_current_warnings()
            
            # Detect new warnings
            new_warnings = self.parser.detect_new_warnings(current_warnings)
            
            # Save current state
            self.parser.save_state(current_warnings)
            
            return new_warnings
            
        except Exception as e:
            logger.error(f"Error checking ČHMÚ warnings: {e}")
            return []
    
    def get_all_active_warnings(self) -> List[ChmiWarning]:
        """Get all currently active warnings."""
        try:
            return self.parser.get_current_warnings()
        except Exception as e:
            logger.error(f"Error fetching ČHMÚ warnings: {e}")
            return []