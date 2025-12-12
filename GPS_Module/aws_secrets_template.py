# AWS IoT Core Configuration for Raspberry Pi
# Update these with your AWS IoT Core settings

DEVICE_ID = "DeviceID_PLACEHOLDER"

# AWS IoT Core Connection
AWS_ENDPOINT = "AWS_ENDPOINT_PLACEHOLDER"
AWS_PORT = 8883

# MQTT Topic for GPS data
MQTT_TOPIC = "$aws/things/NaviCane/gps"

# Certificate paths (full paths on Raspberry Pi)
CA_CERT = "/home/iot/GPS_Module/AmazonRootCA1.pem"
CLIENT_CERT = "CERTIFICATE_PATH_PLACEHOLDER"
CLIENT_KEY = "PRIVATE_KEY_PATH_PLACEHOLDER"