#!/usr/bin/env python3
"""
GPS Hardware Diagnostic Tool
Tests serial connection and detects GPS module
"""

import serial
import time
import sys

def check_serial_port():
    """Check if serial port is accessible"""
    print("=" * 60)
    print("1. CHECKING SERIAL PORT ACCESS")
    print("=" * 60)
    
    try:
        ser = serial.Serial('/dev/ttyAMA0', 9600, timeout=2)
        print("✅ Serial port /dev/ttyAMA0 opened successfully")
        print(f"   Port: {ser.port}")
        print(f"   Baud: {ser.baudrate}")
        print(f"   Timeout: {ser.timeout}")
        return ser
    except PermissionError:
        print("❌ Permission denied! Run with: sudo python3 diagnose_gps.py")
        return None
    except serial.SerialException as e:
        print(f"❌ Failed to open serial port: {e}")
        return None

def test_data_reception(ser):
    """Test if any data is coming from GPS"""
    print("\n" + "=" * 60)
    print("2. READING GPS DATA (30 seconds)")
    print("=" * 60)
    print("Waiting for data...\n")
    
    data_received = False
    start_time = time.time()
    line_count = 0
    
    try:
        while time.time() - start_time < 30:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"[{line_count + 1}] {line}")
                    data_received = True
                    line_count += 1
            time.sleep(0.1)
        
        if data_received:
            print(f"\n✅ Data received! Got {line_count} lines")
            return True
        else:
            print("\n❌ NO DATA received in 30 seconds")
            return False
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return data_received

def troubleshoot():
    """Troubleshooting guide"""
    print("\n" + "=" * 60)
    print("3. TROUBLESHOOTING GUIDE")
    print("=" * 60)
    
    print("\n📋 Check these:")
    print("  1. HARDWARE CONNECTIONS:")
    print("     - NEO-6M TX (white/yellow) → RPi Pin 10 (GPIO15 RX)")
    print("     - NEO-6M RX (green)        → RPi Pin 8  (GPIO14 TX)")
    print("     - NEO-6M GND (black)       → RPi Pin 6  (GND)")
    print("     - NEO-6M VCC (red)         → RPi Pin 2  (5V) or Pin 4")
    print("     - GPS ANTENNA connected to NEO-6M")
    
    print("\n  2. ENABLE UART ON RPi 5:")
    print("     sudo raspi-config")
    print("     → Interface Options → Serial Port → Enable")
    print("     → Do NOT enable Serial Login Shell")
    print("     → Reboot: sudo reboot")
    
    print("\n  3. VERIFY UART:")
    print("     ls -la /dev/ttyAMA0  (should exist)")
    
    print("\n  4. GPS STARTUP TIME:")
    print("     - Cold start: 30-60 seconds (needs satellite fix)")
    print("     - Warm start: 5-10 seconds")
    print("     - Keep antenna in open area with sky view")
    
    print("\n  5. TEST BASIC CONNECTION:")
    print("     sudo timeout 30 cat /dev/ttyAMA0")
    print("     Should show NMEA sentences like:")
    print("     $GPGGA,092750.000,5321.6802,N,...")
    
    print("\n  6. ALTERNATIVE PORTS:")
    print("     ls /dev/tty* | grep -E 'AMA|USB|ACM'")
    print("     GPS might be on different port")

def main():
    print("\n🔍 GPS HARDWARE DIAGNOSTIC TOOL\n")
    
    # Check port access
    ser = check_serial_port()
    if not ser:
        print("\n❌ Cannot proceed without serial port access")
        troubleshoot()
        return
    
    # Test data reception
    has_data = test_data_reception(ser)
    ser.close()
    
    # Troubleshooting
    if not has_data:
        troubleshoot()
    else:
        print("\n✅ GPS is working! You can run: sudo python3 gps_navigation.py")

if __name__ == '__main__':
    main()
