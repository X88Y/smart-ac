#!/usr/bin/env python3
# smart_home.py

import uuid
import json
import argparse
import webbrowser
import requests
import time
from requests_oauthlib import OAuth2Session

# === Настройки OAuth ===
CLIENT_ID = 'ВАШ_CLIENT_ID'
CLIENT_SECRET = 'ВАШ_CLIENT_SECRET'
REDIRECT_URI = 'http://localhost:8080/'
SCOPES = ['iot:control', 'iot:view']
AUTHORIZATION_BASE_URL = 'https://oauth.yandex.com/authorize'
TOKEN_URL = 'https://oauth.yandex.com/token'

API_ACTIONS = 'https://api.iot.yandex.net/v1.0/devices/actions'
API_DEVICES = 'https://api.iot.yandex.net/v1.0/user/info'
token = 'y0__xDVXXXXXXXXXXXXXXXX'

def get_token():
    oauth = OAuth2Session(CLIENT_ID, scope=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = oauth.authorization_url(AUTHORIZATION_BASE_URL)
    print(f'Откройте в браузере и авторизуйтесь:\n{auth_url}')
    webbrowser.open(auth_url)
    resp_url = input('URL после авторизации: ').strip()
    token = oauth.fetch_token(
        TOKEN_URL,
        authorization_response=resp_url,
        client_secret=CLIENT_SECRET
    )
    return token['access_token']

class YandexSmartHome:
    def __init__(self, token: str):
        self.token = token

    def _post(self, body: dict):
        headers = {
            'Authorization': f'Bearer {self.token}',
            'X-Request-Id': uuid.uuid4().hex,
            'Content-Type': 'application/json'
        }
        r = requests.post(API_ACTIONS, headers=headers, json=body)
        r.raise_for_status()
        return r.json()

    def get_devices(self):
        headers = {'Authorization': f'Bearer {self.token}'}
        r = requests.get(API_DEVICES, headers=headers)
        r.raise_for_status()
        data = r.json()
        return data.get('devices', [])

    def power(self, device_id: str, on: bool):
        body = {
            "devices": [{
                "id": device_id,
                "actions": [{
                    "type": "devices.capabilities.on_off",
                    "state": {"instance": "on", "value": on}
                }]
            }]
        }
        return self._post(body)

    def set_brightness(self, device_id: str, brightness: int):
        body = {
            "devices": [{
                "id": device_id,
                "actions": [{
                    "type": "devices.capabilities.range",
                    "state": {"instance": "brightness", "value": brightness}
                }]
            }]
        }
        return self._post(body)

    def set_color(self, device_id: str, r: int, g: int, b: int):
        body = {
            "devices": [{
                "id": device_id,
                "actions": [{
                    "type": "devices.capabilities.color_setting",
                    "state": {
                        "instance": "color",
                        "value": {"r": r, "g": g, "b": b}
                    }
                }]
            }]
        }
        return self._post(body)

    def get_device_by_name(self, name: str):
        devices = self.get_devices()
        for d in devices:
          if d['name'] == name:
            return d
        return None

    def set_ac_speed(self, device_id: str, speed: str):
        if speed == 'off':
            self._post({
                "devices": [{
                    "id": device_id,
                    "actions": [
                        {"type": "devices.capabilities.on_off",
                        "state": {"instance": "on", "value": False}},
                    ]
                }]
            })
            return
                    
        self._post({
          "devices": [{
              "id": device_id,
              "actions": [
                  {"type": "devices.capabilities.on_off",
                  "state": {"instance": "on", "value": True}},
                  {"type": "devices.capabilities.mode",
                  "state": {"instance": "fan_speed", "value": speed}},  # или "high"
                  {"type": "devices.capabilities.range",
                  "state": {"instance": "temperature", "value": 17}}
              ]
          }]
      })

client = YandexSmartHome(token)
