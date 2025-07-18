import time
import threading
from yandex_api import client as yandex_client, YandexSmartHome
from temp import MqttTemperatureClient
from statistics import mean

class SmartAirConditioner:
    def __init__(self,
                 yandex_client: YandexSmartHome,
                 device_name: str = 'Кондиционер',
                 pid_gains: dict = None,
                 temp_history_len: int = 5):
        self.client = yandex_client
        self.ac = self.client.get_device_by_name(device_name)
        # PID state
        self.Kp, self.Ki, self.Kd = pid_gains or (1.0, 0.1, 0.05)
        self._integral = 0.0
        self._last_error = None
        # sensor history for smoothing
        self._temp_readings = []
        self._history_len = temp_history_len
        self._last_speed = None
        self._last_speed_update = None

        # Modes and setpoints
        self._mode = 'home'   # or 'away', 'eco'
        self._schedule = {}   # e.g. {'08:00': ('home', 24.0), '22:00': ('away', 28.0)}
        self._forecast_provider = None
        self._occupancy_provider = None

        # Control loop
        self._target_temp = None
        self._running = False
        self._thread = None

    def set_schedule(self, schedule: dict):
        """
        schedule: { 'HH:MM': (mode, target_temp), ... }
        """
        self._schedule = schedule

    def on_forecast(self, forecast_provider: callable):
        """forecast_provider() → dict with 'high_temp', 'low_temp' etc."""
        self._forecast_provider = forecast_provider

    def on_occupancy(self, occupancy_provider: callable):
        """occupancy_provider() → bool (True if someone home)"""
        self._occupancy_provider = occupancy_provider

    def set_mode(self, mode: str):
        assert mode in ('home', 'away', 'eco')
        self._mode = mode

    def _update_setpoint_from_schedule(self):
        now = time.strftime('%H:%M')
        if now in self._schedule:
            mode, temp = self._schedule[now]
            self.set_mode(mode)
            self._target_temp = temp

    def _fetch_temperature(self):
        t = self._get_temp()
        # smooth via rolling average
        self._temp_readings.append(t)
        if len(self._temp_readings) > self._history_len:
            self._temp_readings.pop(0)
        return mean(self._temp_readings)

    def _pid_control(self, current):
        # basic PID
        error = current - self._target_temp
        self._integral += error
        derivative = 0.0 if self._last_error is None else (error - self._last_error)
        self._last_error = error

        output = self.Kp*error + self.Ki*self._integral + self.Kd*derivative
        return output

    def _map_output_to_speed(self, output: float):
        """
        Map the continuous PID output to discrete fan speeds.
         - output >> + → cooling needed → higher speed
         - output << − → heating needed or idle → lower/off
        """
        if output > 2.0:
            return 'high'
        elif output > 0.5:
            return 'medium'
        elif output < -0.5:
            return 'off'
        else:
            return 'low'

    def set_speed(self, speed: str, current_temp: float = None, pid_out: float = None):
        print(f"[AC] → Setting speed: {speed}, current_temp: {current_temp}, pid_out: {pid_out}")
        if self._last_speed_update and time.time() - self._last_speed_update > 30 * 60:
            self._last_speed = None
            self._last_speed_update = None

        if self._last_speed == speed:
            return

        self._last_speed = speed
        self._last_speed_update = time.time()
        self.client.set_ac_speed(self.ac['id'], speed)

    def start(self, target_temp: float, temp_provider: callable):
        if self._running:
            raise RuntimeError("Already running")
        self._target_temp = target_temp
        self._get_temp = temp_provider
        self._running = True
        self._thread = threading.Thread(target=self._control_loop, daemon=True)
        self._thread.start()
        print(f"[AC] Control loop started. Initial setpoint: {self._target_temp}°C")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        print("[AC] Control loop stopped.")

    def _control_loop(self):
        while self._running:
            try:
                # 1) Maybe update setpoint per schedule
                self._update_setpoint_from_schedule()

                # 2) Maybe override mode if occupancy = False
                if self._occupancy_provider and not self._occupancy_provider():
                    self.set_mode('away')
                elif self._mode == 'away':
                    # in away mode, allow larger tolerance
                    self._integral = 0  # reset
                    # maybe raise setpoint 3°C to save energy
                    self._target_temp += 3

                # 3) Get smoothed temperature
                current = self._fetch_temperature()
                # 4) Compute PID output
                pid_out = self._pid_control(current)

                # 6) Map to discrete speed & send
                speed = self._map_output_to_speed(pid_out)
                self.set_speed(speed, current, pid_out)

            except Exception as e:
                print(f"[AC] ERROR in loop: {e}")

            time.sleep(60)  # 1-minute resolution




# === MAIN SCRIPT ===
def main():
    smart_ac = SmartAirConditioner(yandex_client)

    # Wait for initial temperature
    print("Waiting for temperature data...")
    
    mqtt_client = MqttTemperatureClient()
    mqtt_client.start()

    while True:
        try:
          temp = mqtt_client.get_latest_temperature()
          print(f"Initial temp: {temp}°C")
          break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

    # Get user target and start AC loop
    target = 24
    smart_ac.start(target, mqtt_client.get_latest_temperature)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        smart_ac.stop()
        mqtt_client.stop()

if __name__ == '__main__':
    main()