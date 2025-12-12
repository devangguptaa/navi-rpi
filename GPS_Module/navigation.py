#!/usr/bin/env python3
"""
GPS Navigation System for RPi + NEO-6M
Walks you through turn-by-turn directions to a target location
"""

import serial
import pynmea2
import requests
import time
from math import radians, cos, sin, asin, sqrt, atan2, degrees
import pyttsx3
import sys 

engine = pyttsx3.init()

# Configuration
SERIAL_PORT = '/dev/ttyAMA0'
BAUD_RATE = 9600
# TARGET_LAT = 40.7128  # NYC example - CHANGE THIS
# TARGET_LON = -74.0060  # NYC example - CHANGE THIS
WAYPOINT_THRESHOLD = 15  # meters - advance to next step when this close
UPDATE_INTERVAL = 2  # seconds

# Read target from command line if provided
if len(sys.argv) >= 3:
    try:
        TARGET_LAT = float(sys.argv[1])
        TARGET_LON = float(sys.argv[2])
        print(f"[navigation] Using target from arguments: {TARGET_LAT}, {TARGET_LON}")
    except ValueError:
        print("[navigation] Invalid coordinates passed, falling back to defaults")
        TARGET_LAT = 40.7128
        TARGET_LON = -74.0060
else:
    TARGET_LAT = 40.7128  # default
    TARGET_LON = -74.0060  # default
    print(f"[navigation] Using default target: {TARGET_LAT}, {TARGET_LON}")

class GPSNavigator:
    def __init__(self, target_lat, target_lon):
        self.target_lat = target_lat
        self.target_lon = target_lon
        self.current_lat = None
        self.current_lon = None
        self.route_steps = []
        self.current_step_index = 0
        self.destination_reached = False
        
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two GPS points in meters"""
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return 6371000 * c  # Earth radius in meters
    
    def calculate_bearing(self, lat1, lon1, lat2, lon2):
        """Calculate bearing between two points (0-360 degrees)"""
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        y = sin(dlon) * cos(lat2)
        x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
        bearing = degrees(atan2(y, x))
        return (bearing + 360) % 360
    
    def get_route_from_osrm(self, start_lat, start_lon):
        """Fetch route from OSRM (Open Source Routing Machine)"""
        try:
            url = f"http://router.project-osrm.org/route/v1/foot/{start_lon},{start_lat};{self.target_lon},{self.target_lat}?steps=true&geometries=geojson"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if data['code'] == 'Ok' and data['routes']:
                steps = data['routes'][0]['legs'][0]['steps']
                self.route_steps = steps
                self.current_step_index = 0
                
                print("\n" + "="*60)
                print(f"📍 Route calculated! Total distance: {data['routes'][0]['distance']:.0f}m")
                print(f"⏱️  Estimated time: {data['routes'][0]['duration']:.0f}s ({data['routes'][0]['duration']/60:.1f} mins)")
                print("="*60 + "\n")
                return True
            else:
                print(f"❌ No route found: {data.get('message', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"❌ Error fetching route: {e}")
            return False
    
    def parse_gps_sentence(self, sentence):
        """Parse NMEA GPS sentence and extract coordinates"""
        try:
            msg = pynmea2.parse(sentence)
            if msg.sentence_type == 'GGA':
                if msg.latitude and msg.longitude:
                    lat = float(msg.latitude)
                    lon = float(msg.longitude)
                    if lat != 0 and lon != 0:  # Valid fix
                        return lat, lon
        except:
            pass
        return None, None
    
    def get_direction_name(self, bearing):
        """Convert bearing to cardinal direction"""
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                     'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        idx = round(bearing / 22.5) % 16
        return directions[idx]
    
    def print_next_instruction(self):
        """Print the next navigation instruction"""
        if self.current_step_index >= len(self.route_steps):
            self.destination_reached = True
            print("\n" + "🎉" * 20)
            print("🎉  YOU'VE ARRIVED AT YOUR DESTINATION!  🎉")
            engine.say("You have arrived at your destination")
            engine.runAndWait()
            print("🎉" * 20 + "\n")
            return
        
        step = self.route_steps[self.current_step_index]
        instruction = step.get('name', 'Continue')
        distance = step.get('distance', 0)
        maneuver = step.get('maneuver', {})
        turn_type = maneuver.get('type', 'straight')
        
        print(f"\n➡️  NEXT INSTRUCTION:")
        print(f"   {turn_type.upper()}")
        print(f"   {instruction}")
        print(f"   Distance: {distance:.0f}m\n")
        engine.say(f"{turn_type}. {instruction} in {distance:.0f} meters.")
        engine.runAndWait()
    
    def navigate_loop(self):
        """Main navigation loop"""
        print("\n" + "="*60)
        print("🗺️  GPS NAVIGATION SYSTEM - RPi + NEO-6M")
        print("="*60)
        print(f"Target: ({self.target_lat}, {self.target_lon})")
        print("Waiting for GPS fix...\n")
        
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(1)
            
            route_fetched = False
            gps_fix_count = 0
            
            while not self.destination_reached:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    
                    if line:
                        lat, lon = self.parse_gps_sentence(line)
                        
                        if lat is not None and lon is not None:
                            self.current_lat = lat
                            self.current_lon = lon
                            
                            # Get route on first GPS fix
                            if not route_fetched:
                                gps_fix_count += 1
                                print(f"📡 GPS Fix #{gps_fix_count}: {lat:.6f}, {lon:.6f}")
                                
                                if gps_fix_count >= 3:  # Wait for 3 fixes for stability
                                    print("\n✅ GPS locked! Calculating route...\n")
                                    if self.get_route_from_osrm(lat, lon):
                                        route_fetched = True
                                        self.print_next_instruction()
                                    time.sleep(2)
                            
                            # Navigation logic once route is fetched
                            elif route_fetched and self.current_step_index < len(self.route_steps):
                                step = self.route_steps[self.current_step_index]
                                
                                # Distance to next waypoint
                                dist_to_waypoint = self.haversine_distance(
                                    lat, lon,
                                    step['geometry']['coordinates'][-1][1],  # lat
                                    step['geometry']['coordinates'][-1][0]   # lon
                                )
                                
                                # Check if reached waypoint
                                if dist_to_waypoint < WAYPOINT_THRESHOLD:
                                    print(f"✅ Reached waypoint! Moving to next step...")
                                    self.current_step_index += 1
                                    self.print_next_instruction()
                                
                                # Print periodic updates
                                elif int(time.time()) % UPDATE_INTERVAL == 0:
                                    bearing = self.calculate_bearing(lat, lon,
                                        step['geometry']['coordinates'][-1][1],
                                        step['geometry']['coordinates'][-1][0])
                                    direction = self.get_direction_name(bearing)
                                    print(f"📍 Current: {lat:.6f}, {lon:.6f} | "
                                          f"Direction: {direction} | Distance: {dist_to_waypoint:.0f}m")
                    
                    time.sleep(0.1)
                
                except Exception as e:
                    print(f"Error: {e}")
                    continue
        
        except serial.SerialException as e:
            print(f"❌ Serial Error: {e}")
            print(f"Make sure:")
            print(f"  1. NEO-6M is connected to GPIO14 (TX) and GPIO15 (RX)")
            print(f"  2. Serial interface is enabled: sudo raspi-config")
            print(f"  3. You're running as root or with appropriate permissions")
        
        except KeyboardInterrupt:
            print("\n\n👋 Navigation stopped by user")
        
        finally:
            if 'ser' in locals():
                ser.close()

def main():
    navigator = GPSNavigator(TARGET_LAT, TARGET_LON)
    navigator.navigate_loop()

if __name__ == '__main__':
    main()