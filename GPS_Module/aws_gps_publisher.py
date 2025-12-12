import time
import json
import serial
import threading
from paho.mqtt.client import Client as mqtt_client
from aws_secrets import (
    DEVICE_ID,
    AWS_ENDPOINT,
    AWS_PORT,
    MQTT_TOPIC,
    CA_CERT,
    CLIENT_CERT,
    CLIENT_KEY
)

# GPS Configuration
GPS_PORT = "/dev/ttyAMA0"
GPS_BAUD = 9600

# Global variables
gps_data = {
    "latitude": None,
    "longitude": None,
    "altitude": None,
    "satellites": 0,
    "hdop": None
}
gps_lock = threading.Lock()

def parse_gps_data(line):
    """Parse NMEA sentences and extract GPS data"""
    try:
        if not line.startswith('$'):
            return False
        
        parts = line.split(',')
        
        # Parse GGA sentence (position, altitude, fix quality)
        if parts[0] == '$GPGGA':
            try:
                fix_quality = int(parts[6]) if len(parts) > 6 else 0
                if fix_quality == 0:
                    return False
                
                # Extract latitude
                if len(parts) > 2 and parts[2]:
                    lat = float(parts[2])
                    lat_dir = parts[3]
                    latitude = int(lat / 100) + (lat % 100) / 60
                    if lat_dir == 'S':
                        latitude = -latitude
                    gps_data["latitude"] = round(latitude, 8)
                
                # Extract longitude
                if len(parts) > 4 and parts[4]:
                    lon = float(parts[4])
                    lon_dir = parts[5]
                    longitude = int(lon / 100) + (lon % 100) / 60
                    if lon_dir == 'W':
                        longitude = -longitude
                    gps_data["longitude"] = round(longitude, 8)
                
                # Extract altitude
                if len(parts) > 9 and parts[9]:
                    gps_data["altitude"] = round(float(parts[9]), 2)
                
                # Extract HDOP
                if len(parts) > 8 and parts[8]:
                    gps_data["hdop"] = round(float(parts[8]), 2)
                
                return True
            except (ValueError, IndexError):
                return False
        
        # Parse GSA sentence (satellites in use)
        elif parts[0] == '$GPGSA':
            try:
                satellites_in_use = 0
                for i in range(3, 15):
                    if len(parts) > i and parts[i]:
                        satellites_in_use += 1
                gps_data["satellites"] = satellites_in_use
                return True
            except (ValueError, IndexError):
                return False
        
        return False
    except Exception as e:
        print(f"Error parsing GPS data: {e}")
        return False

def gps_reader():
    """Read GPS data from serial port in a separate thread"""
    print(f"Opening GPS serial port {GPS_PORT}...")
    try:
        ser = serial.Serial(GPS_PORT, GPS_BAUD, timeout=2)
        print(f"✓ GPS serial port opened at {GPS_BAUD} baud")
        
        while True:
            try:
                if ser.in_waiting:
                    line = ser.readline().decode('utf-8').strip()
                    if line:
                        parse_gps_data(line)
            except Exception as e:
                print(f"GPS reader error: {e}")
                time.sleep(1)
    except Exception as e:
        print(f"✗ Failed to open GPS serial port: {e}")
    finally:
        if ser.is_open:
            ser.close()

def on_connect(client, userdata, flags, rc):
    """Callback for when client connects to broker"""
    if rc == 0:
        print("✓ Connected to AWS IoT Core!")
    else:
        print(f"✗ Connection failed with code {rc}")

def on_disconnect(client, userdata, rc):
    """Callback for when client disconnects from broker"""
    if rc != 0:
        print(f"Unexpected disconnection, code: {rc}")

def on_publish(client, userdata, mid):
    """Callback for when message is published"""
    pass

def mqtt_connect():
    """Connect to AWS IoT Core using certificates"""
    try:
        print(f"\nConnecting to AWS IoT Core at {AWS_ENDPOINT}:{AWS_PORT}...")
        
        client = mqtt_client(client_id=DEVICE_ID)
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_publish = on_publish
        
        # Set certificates and keys
        client.tls_set(
            ca_certs=CA_CERT,
            certfile=CLIENT_CERT,
            keyfile=CLIENT_KEY,
            cert_reqs=0,
            tls_version=2,
            ciphers=None
        )
        
        # Disable certificate verification (not recommended for production)
        client.tls_insecure_set(False)
        
        # Connect to AWS IoT Core
        client.connect(AWS_ENDPOINT, AWS_PORT, keepalive=60)
        
        # Start the network loop
        client.loop_start()
        
        print("✓ MQTT client initialized")
        return client
    except Exception as e:
        print(f"✗ MQTT connection error: {e}")
        return None

def mqtt_publish(client, topic, payload):
    """Publish GPS data to MQTT topic"""
    try:
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        
        result = client.publish(topic, payload, qos=1)
        return result.rc == 0
    except Exception as e:
        print(f"✗ Publish error: {e}")
        return False

def main():
    print("\n" + "="*60)
    print("🗺️  AWS IoT Core GPS Data Publisher (Raspberry Pi)")
    print("="*60)
    
    # Start GPS reader thread
    print("\nStarting GPS reader thread...")
    gps_thread = threading.Thread(target=gps_reader, daemon=True)
    gps_thread.start()
    
    # Give GPS time to get a fix
    print("Waiting for GPS fix...")
    time.sleep(5)
    
    # Connect to AWS IoT Core
    mqtt = mqtt_connect()
    if not mqtt:
        print("Failed to connect to AWS IoT Core")
        return
    
    # Wait for connection to establish
    time.sleep(2)
    
    # Main loop: publish GPS data
    print("\nStarting GPS data publication...\n")
    counter = 0
    last_publish_time = 0
    publish_interval = 5  # Publish every 5 seconds
    
    try:
        while True:
            current_time = time.time()
            
            # Publish GPS data every N seconds
            if current_time - last_publish_time >= publish_interval:
                if gps_data["latitude"] is not None and gps_data["longitude"] is not None:
                    payload = {
                        "device_id": DEVICE_ID,
                        "timestamp": int(current_time),
                        "location": {
                            "latitude": gps_data["latitude"],
                            "longitude": gps_data["longitude"],
                            "altitude": gps_data["altitude"],
                            "satellites": gps_data["satellites"],
                            "hdop": gps_data["hdop"]
                        }
                    }
                    
                    # Display
                    print(f"#{counter} | Lat: {gps_data['latitude']:10.8f} | Lon: {gps_data['longitude']:10.8f} | Alt: {gps_data['altitude']}m | Sats: {gps_data['satellites']} ", end="")
                    
                    # Publish to AWS
                    if mqtt_publish(mqtt, MQTT_TOPIC, payload):
                        print("→ ✓ published")
                    else:
                        print("→ ✗ publish failed")
                    
                    counter += 1
                    last_publish_time = current_time
                else:
                    print("Waiting for GPS fix...")
            
            time.sleep(0.5)
    
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        mqtt.loop_stop()
        mqtt.disconnect()
        print("✓ Disconnected from AWS IoT Core")

if __name__ == "__main__":
    main()
