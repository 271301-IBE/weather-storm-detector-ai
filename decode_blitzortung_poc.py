#!/usr/bin/env python3
"""
Blitzortung Lightning Data Decoder - Enhanced Version
Dekodér pro data blesku z Blitzortung.org WebSocket streamu
"""

import json
import re
import asyncio
import websockets
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import unicodedata

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BlitzortungDecoder:
    """Enhanced decoder for Blitzortung lightning data"""
    
    def __init__(self):
        self.ws_url = "wss://ws1.blitzortung.org/"
        self.subscription_message = json.dumps({"a": 111})
        # Precise character mappings based on observed lightning data
        self.char_mappings = {
            # Numbers 0-9 (most common corrupted characters)
            'Ā': '0', 'ĕ': '1', 'Ġ': '2', 'ı': '3', 'Ĉ': '4', 'Ć': '5', 'ě': '6', 'ď': '7', 'İ': '8', 'Ċ': '9',
            'Ě': '0', 'Ď': '1', 'ő': '2', 'č': '3', 'ă': '4', 'ĩ': '5', 'ů': '6', 'Ĥ': '7', 'ā': '8', 'ą': '9',
            'ƃ': '0', 'ĺ': '1', 'Ŵ': '2', 'ģ': '3', 'Ĳ': '4', 'ż': '5', 'Ĭ': '6', 'ĵ': '7', 'ķ': '8', 'Ɗ': '9',
            'Œ': '0', 'ŏ': '1', 'Ŕ': '2', 'ē': '3', 'Ƒ': '4', 'Ť': '5', 'Ŧ': '6', 'ũ': '7', 'Ɨ': '8', 'Ŭ': '9',
            'ĝ': '0', 'į': '1', 'ƶ': '2', 'ź': '3', 'Ư': '4', 'Ũ': '5', 'Ž': '6', 'Ŷ': '7', 'Ʋ': '8', 'ū': '9',
            'Đ': '0', 'Ļ': '1', 'ƌ': '2', 'Ƹ': '3', 'ƺ': '4', 'ţ': '5', 'ƚ': '6', 'ǀ': '7', 'Ą': '8', 'Ė': '9',
            'Ĕ': '0', 'Ĺ': '1', 'ĥ': '2', 'ĉ': '3', 'Č': '4', 'Ś': '5', 'Ň': '6', 'Ń': '7', 'ň': '8', 'ŗ': '9',
            'ġ': '9', 'Ż': '0', 'Ĝ': '1', 'œ': '3', 'ń': '4', 'Ţ': '5', 'Ɖ': '7', 'ī': '8',
            
            # Punctuation and delimiters
            'ę': ',', 'ĭ': ':', 'ś': ':', 'Ŏ': '"', 'ğ': '"', 'Ğ': '"', 'ŋ': '"',
            'ĝ': '"', 'ł': '"', 'Ł': '"', 'ň': '"', 'ŉ': '"', 'Ň': '"', 'ŋ': '"',
            'ń': '"', 'Ń': '"', 'ų': '"', 'Ų': '"', 'ŭ': '"', 'Ŭ': '"', 'ů': '"',
            
            # Common text patterns that appear in corrupted form
            'Ĳ': '4', 'ŏ': '1', 'Ô': '2', 'Ë': '0', 'ë': '0',
            
            # Additional numeric mappings from new data
            'đ': '1', 'Đ': '0', 'Ġ': '2', 'ġ': '9', 'Ĥ': '7', 'ĥ': '2', 'Ĩ': '8', 'ĩ': '5',
            'ı': '3', 'İ': '8', 'į': '1', 'Į': '1', 'Ī': '8', 'ī': '8', 'Ĭ': '6', 'ĭ': '1',
            'Ķ': '9', 'ķ': '8', 'Ĺ': '1', 'ĺ': '1', 'Ļ': '1', 'ļ': '1', 'Ľ': '1', 'ľ': '1',
            'Ł': '1', 'ł': '1', 'Ń': '7', 'ń': '4', 'Ņ': '5', 'ņ': '5', 'Ň': '6', 'ň': '8',
            'ŉ': '9', 'Ō': '0', 'ō': '1', 'Ŏ': '0', 'ŏ': '1', 'Ő': '0', 'ő': '2',
            'Ŕ': '2', 'ŕ': '2', 'Ŗ': '2', 'ŗ': '9', 'Ř': '2', 'ř': '2', 'Ś': '5', 'ś': '5',
            'Ŝ': '5', 'ŝ': '5', 'Ş': '5', 'ş': '5', 'Š': '5', 'š': '5', 'Ţ': '5', 'ţ': '5',
            'Ť': '5', 'ť': '5', 'Ŧ': '6', 'ŧ': '6', 'Ũ': '5', 'ũ': '7', 'Ū': '9', 'ū': '9',
            'Ŭ': '9', 'ŭ': '9', 'Ů': '6', 'ů': '6', 'Ű': '9', 'ű': '9', 'Ų': '9', 'ų': '9',
            'Ŵ': '2', 'ŵ': '2', 'Ŷ': '7', 'ŷ': '7', 'Ÿ': '7', 'Ź': '3', 'ź': '3',
            'Ż': '0', 'ż': '5', 'Ž': '6', 'ž': '6',
            
            # Cleanup - remove remaining noise patterns
            'ĸ': '', 'Ķ': '', 'ĻĂĄ': '', 'ĴĶ': '', 'ĵķ': '', 'ŝő': '', 'tœ': '', 
            'ţő': '', 'šŎ': '', 'šŏ': '', 'ťŒ': '', 'ŢŒ': '', 'ŤŒ': '', 'şăą': '',
            'řć': '', 'Ħř': '', 'ĩŘ': '', 'ňě': '', 'ĩŝ': '', 'ħĝ': '', 'ħěř': '',
            'ħĩ': '', 'ĥň': '', 'ěŘ': '', 'Ĭġ': '', 'Ôăą': '', 'ĀŐa': '', 'ĂĄĆ': '',
            'āăą': '', 'ĝğġ': '', 'ĝğĞĠ': '', 'ěĝğ': '', 'ĨĝĞ': '', 'ĩĝğ': '',
            'ħĜĞ': '', 'ĦĜĞ': '', 'ĨĜĞ': '', 'ĚĜĞ': '', 'ĩĚĜ': '', 'ĦĚŜ': '',
            'ħĚś': '', 'ĨŜć': '', 'ĩŘć': '', 'ĦĚŘ': '', 'ħĩř': '', 'ĥĩŚ': ''
        }
    
    def lzw_decompress(self, compressed_data: bytes) -> str:
        """
        LZW decompression algorithm based on the R code shown in the video.
        Converts compressed bytes to string using LZW algorithm.
        """
        try:
            # Convert bytes to list of integers (codes)
            if isinstance(compressed_data, str):
                codes = [ord(c) for c in compressed_data]
            else:
                codes = list(compressed_data)
            
            if not codes:
                return ""
            
            # Initialize dictionary with ASCII characters (0-255)
            dict_size = 256
            dictionary = {i: chr(i) for i in range(dict_size)}
            
            # Initialize result and previous code
            result = []
            prev_code = codes[0]
            result.append(dictionary[prev_code])
            
            # Process remaining codes
            for i in range(1, len(codes)):
                code = codes[i]
                
                if code < len(dictionary):
                    # Code exists in dictionary
                    entry = dictionary[code]
                elif code == dict_size:
                    # New code - create from previous + first char of previous
                    entry = dictionary[prev_code] + dictionary[prev_code][0]
                else:
                    # Invalid code
                    logger.warning(f"Bad LZW code: {code}")
                    break
                
                result.append(entry)
                
                # Add new entry to dictionary
                if dict_size < 4096:  # Limit dictionary size to prevent memory issues
                    dictionary[dict_size] = dictionary[prev_code] + entry[0]
                    dict_size += 1
                
                prev_code = code
            
            return ''.join(result)
            
        except Exception as e:
            logger.error(f"LZW decompression error: {e}")
            return ""

    def clean_and_extract_json(self, data: str) -> Optional[Dict]:
        """Clean the string and extract the core JSON object."""
        original_data = data
        
        # Try LZW decompression if data looks compressed
        if self.detect_compression(data):
            logger.info("Data appears compressed, attempting LZW decompression...")
            
            # Try primary LZW method
            try:
                if isinstance(data, str):
                    data_bytes = data.encode('latin1', errors='ignore')
                else:
                    data_bytes = data
                
                decompressed = self.lzw_decompress(data_bytes)
                if decompressed and ('{' in decompressed or '"' in decompressed):
                    logger.info(f"Primary LZW decompression successful, length: {len(decompressed)}")
                    data = decompressed
                else:
                    # Try alternative LZW method
                    logger.info("Primary LZW failed, trying alternative method...")
                    decompressed = self.try_alternative_lzw(data_bytes)
                    if decompressed and ('{' in decompressed or '"' in decompressed):
                        logger.info(f"Alternative LZW decompression successful, length: {len(decompressed)}")
                        data = decompressed
                    else:
                        logger.info("Both LZW methods failed, using original data")
                        data = original_data
                        
            except Exception as e:
                logger.error(f"LZW decompression failed: {e}")
                data = original_data
        
        # First, find the main JSON object
        json_start = data.find('{')
        json_end = data.rfind('}') + 1
        
        if json_start == -1 or json_end == 0:
            # Try to find JSON in quotes
            quote_start = data.find('"')
            if quote_start != -1:
                quote_content = data[quote_start+1:]
                json_start = quote_content.find('{')
                if json_start != -1:
                    json_end = quote_content.rfind('}') + 1
                    if json_end > 0:
                        potential_json = quote_content[json_start:json_end]
                    else:
                        logger.warning("No JSON object found in the data.")
                        return None
                else:
                    logger.warning("No JSON object found in the data.")
                    return None
            else:
                logger.warning("No JSON object found in the data.")
                return None
        else:
            potential_json = data[json_start:json_end]
        
        # Iteratively replace known bad characters
        cleaned_json = potential_json
        for corrupt, replacement in self.char_mappings.items():
            cleaned_json = cleaned_json.replace(corrupt, replacement)
        
        # Final cleanup: remove any remaining non-standard characters that might break JSON parsing
        # Keep only printable ASCII characters (0x20 to 0x7E) and common whitespace
        cleaned_json = ''.join(c for c in cleaned_json if 0x20 <= ord(c) <= 0x7E or c in '\t\n\r')
        
        logger.debug(f"Potential JSON after char mapping: {potential_json[:200]}...")
        logger.debug(f"Cleaned JSON before final parse: {cleaned_json[:200]}...")
        
        try:
            return json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON after cleaning: {e}")
            logger.debug(f"Problematic string: {cleaned_json}")
            return None

    def decode_lightning_data(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """Main decoding function"""
        try:
            decoded_json = self.clean_and_extract_json(raw_data)
            
            if not decoded_json:
                return {
                    'timestamp': datetime.now().isoformat(),
                    'raw_data_sample': raw_data[:150] + '...' if len(raw_data) > 150 else raw_data,
                    'decoding_status': 'failed - no JSON object could be parsed'
                }

            # Convert nanosecond timestamp to a readable format
            timestamp_ns = decoded_json.get('time')
            if isinstance(timestamp_ns, int):
                try:
                    # Assuming timestamp is in nanoseconds
                    dt_object = datetime.fromtimestamp(timestamp_ns / 1e9)
                    decoded_json['time_readable'] = dt_object.isoformat()
                except (ValueError, OSError) as e:
                    decoded_json['time_readable'] = f"Invalid timestamp: {e}"

            return {
                'timestamp': datetime.now().isoformat(),
                'decoded_strike': decoded_json,
                'decoding_status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Error decoding lightning data: {e}")
            return None
    
    def detect_compression(self, data) -> bool:
        """Detect if data might be compressed"""
        if isinstance(data, str):
            # Check for non-printable characters or high byte values
            return any(ord(c) > 127 for c in data[:100])
        elif isinstance(data, (bytes, bytearray)):
            # Check byte patterns that might indicate compression
            return any(b > 127 for b in data[:100])
        return False

    def try_alternative_lzw(self, data) -> str:
        """Alternative LZW implementation with different dictionary initialization"""
        try:
            if isinstance(data, str):
                codes = [ord(c) for c in data]
            else:
                codes = list(data)
            
            if not codes:
                return ""
            
            # Alternative approach: start with smaller dictionary
            dictionary = {}
            for i in range(256):
                dictionary[i] = chr(i)
            
            dict_size = 256
            result = []
            
            # Handle first code
            prev_string = dictionary[codes[0]]
            result.append(prev_string)
            
            for code in codes[1:]:
                if code in dictionary:
                    current_string = dictionary[code]
                elif code == dict_size:
                    current_string = prev_string + prev_string[0]
                else:
                    logger.warning(f"Invalid LZW code encountered: {code}")
                    continue
                
                result.append(current_string)
                
                # Add to dictionary
                if dict_size < 4095:  # Leave some room
                    dictionary[dict_size] = prev_string + current_string[0]
                    dict_size += 1
                
                prev_string = current_string
            
            return ''.join(result)
            
        except Exception as e:
            logger.error(f"Alternative LZW decompression error: {e}")
            return ""

    async def connect_websocket(self):
        """Connect to Blitzortung WebSocket and receive data"""
        try:
            logger.info(f"Connecting to {self.ws_url}")
            
            async with websockets.connect(self.ws_url) as websocket:
                logger.info("Connected to Blitzortung WebSocket!")
                await websocket.send(self.subscription_message)
                logger.info("Subscription message sent.")
                
                message_count = 0
                async for message in websocket:
                    message_count += 1
                    logger.info(f"Received message #{message_count} (length: {len(message)})")
                    
                    # Log raw data info for debugging
                    if isinstance(message, str):
                        logger.debug(f"Message type: string, first 50 chars: {message[:50]}")
                        logger.debug(f"Contains non-ASCII: {any(ord(c) > 127 for c in message[:100])}")
                    else:
                        logger.debug(f"Message type: {type(message)}, first 50 bytes: {message[:50]}")
                    
                    decoded = self.decode_lightning_data(message)
                    
                    print(f"\n=== Decoded Data #{message_count} ===")
                    if decoded:
                        print(json.dumps(decoded, indent=2, ensure_ascii=False))
                    else:
                        print("Failed to decode message.")
                        # Show raw data sample for debugging
                        if isinstance(message, str):
                            print(f"Raw data sample: {message[:200]}")
                        else:
                            print(f"Raw data sample: {message[:200]}")
                    print("-" * 50)
                    
                    # Limit to first 20 messages for testing
                    if message_count >= 20:
                        break
                        
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)

def test_lzw_algorithm():
    """Test the LZW algorithm with sample data"""
    print("=== Testing LZW Algorithm ===")
    
    decoder = BlitzortungDecoder()
    
    # Test with simple string
    test_string = "TOBEORNOTTOBEORTOBEORNOT"
    print(f"Original: {test_string}")
    
    # Simple LZW compression for testing (this would normally come from the server)
    test_codes = [ord(c) for c in test_string]
    
    # Test decompression
    result = decoder.lzw_decompress(test_codes)
    print(f"LZW decompressed: {result}")
    
    # Test with JSON-like data
    test_json = '{"time":1234567890,"lat":49.2,"lon":16.6,"alt":0}'
    test_codes_json = [ord(c) for c in test_json]
    result_json = decoder.lzw_decompress(test_codes_json)
    print(f"JSON test - Original: {test_json}")
    print(f"JSON test - Decompressed: {result_json}")
    
    print("-" * 50)

def main():
    """Main function to start the decoder"""
    decoder = BlitzortungDecoder()
    
    print("=== Blitzortung Lightning Data Decoder ===")
    
    # Test LZW algorithm first
    test_lzw_algorithm()
    
    print("\nConnecting to live WebSocket stream...")
    
    try:
        asyncio.run(decoder.connect_websocket())
    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C)")
    except Exception as e:
        print(f"An error occurred: {e}")
        
    print("\nProcessing complete!")

if __name__ == "__main__":
    main()
