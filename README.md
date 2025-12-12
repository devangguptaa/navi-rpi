# NAVI - Navigational Assistant for Visually Impaired 

## This repository handles obstacle detection, NAVI Voice Assistant and GPS navigation 

### Clone this repository to run on the Raspberry Pi 


---

## File Descriptions

### GPS_Module/

#### `navigation.py`
Implements the core GPS navigation logic.  
Parses live NMEA data from the GPS module, computes distance and bearing to a target destination, and generates turn-by-turn walking instructions.

#### `diagnose_gps.py`
Standalone GPS diagnostic utility used to verify GPS lock, satellite count, and NMEA sentence validity. Useful for hardware debugging before running navigation.

#### `aws_gps_publisher.py`
Publishes real-time GPS coordinates to AWS IoT Core using MQTT over TLS. Enables live location tracking for a caregiver dashboard.

#### `aws_secrets_template.py`
Template version of `aws_secrets.py` with placeholder values. Intended for setup and deployment reference.

#### `requirements.txt`
Python dependencies required for GPS parsing, cloud communication, and supporting utilities.

---

### Root Directory

#### `voice_assistant.py`
Implements the voice-based user interface. Integrates wake-word detection, speech-to-text, LLM-based intent handling, and text-to-speech output. Allows users to set navigation destinations and receive spoken guidance.

#### `obstacle_depth.py`
Processes depth camera data to detect nearby obstacles. Generates alerts for objects within unsafe distances to complement GPS navigation.

#### `Hey-Navi_en_raspberry-pi_v3_0_0.ppn`
Porcupine wake-word model for offline detection of the phrase “Hey Navi” on Raspberry Pi.

---