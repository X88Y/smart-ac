import ssl
import json
import threading
import paho.mqtt.client as mqtt
from urllib.parse import urlparse
import requests
import time

company_id = 0000
qing_uid = 0000
session_id = 'em7SEYxxxxxxxxxxxoW6670DqFH'

def get_credentials():
    urls = [
        'https://qingiot.cleargrass.com/session/unread?company_id=' + str(company_id) + '&uid=' + str(qing_uid) + '&page_size=100&page=1&time=',
        'https://qingiot.cleargrass.com/group/listAllWithLevel&time=',
        'https://qingiot.cleargrass.com/session/info/' + str(qing_uid) + '?id=' + str(qing_uid) + '&time=',
        'https://qingiot.cleargrass.com/team/getMqttConfig?company_id=' + str(company_id) + '&qing_uid=' + str(qing_uid) + '&time=',
    ]

    for url in urls:
        nowSinceEpoch = int(time.time() * 1000)
        time.sleep(1)
        response = requests.get(url + str(nowSinceEpoch), headers={
            "referer": "https://www.qingpingiot.com/",
            "session-id": session_id
        })

    data = response.json()['data']['mqtt']
    return data

# === MQTT HANDLER CLASS ===
class MqttTemperatureClient:
    """
    Self-contained MQTT client to subscribe to sensor data and
    maintain the latest temperature reading over WebSocket.
    """
    def __init__(self):
        # broker_url: e.g. 'wss://wss.cleargrass.com/mqtt'
        mqtt_config = get_credentials()
        
        self.broker_url = mqtt_config['brokerUrl']
        self.sub_topic = mqtt_config['subTopic']
        self.username = mqtt_config['options']['username']
        self.password = mqtt_config['options']['password']
        self.client_id = mqtt_config['options']['clientId']
        print(self.client_id, self.broker_url, self.sub_topic, self.username, self.password, self.client_id)

        self._latest_temperature = None
        self._lock = threading.Lock()

        # Prepare MQTT client for WebSocket transport
        self._client = mqtt.Client(client_id=self.client_id, transport="websockets")
        self._client.username_pw_set(self.username, self.password)
        self._client.tls_set(cert_reqs=ssl.CERT_NONE)
        self._client.tls_insecure_set(True)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected (rc={rc}), subscribing to {self.sub_topic}")
        client.subscribe(self.sub_topic)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            data = json.loads(payload.get("data", "{}"))
            sensor_list = data.get("sensorData", [])
            if sensor_list:
                sensor = sensor_list[0]
                temp_entry = sensor.get('temperature')
                if temp_entry:
                    temp = float(temp_entry.get('value'))
                    with self._lock:
                        self._latest_temperature = temp
        except Exception as e:
            print(f"[MQTT] Error parsing message: {e}")

    def start(self):
        """Connect using WebSocket options and start the MQTT loop."""
        # Parse broker_url
        parsed = urlparse(self.broker_url)
        host = parsed.hostname
        port = parsed.port or 443
        path = parsed.path or '/'

        # Configure WebSocket path for MQTT over WS(S)
        self._client.ws_set_options(path=path)
        print(f"[MQTT] Connecting to {host}:{port} over WebSocket path '{path}'...")
        self._client.connect(host, port)
        self._client.loop_start()

    def stop(self):
        """Stop the MQTT loop and disconnect."""
        self._client.loop_stop()
        self._client.disconnect()
        print("[MQTT] Disconnected.")

    def get_latest_temperature(self) -> float:
        """Return the most recent temperature or raise if none."""
        with self._lock:
            if self._latest_temperature is None:
                raise RuntimeError("No temperature data available yet")
            return self._latest_temperature
