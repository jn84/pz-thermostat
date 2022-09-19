import math

import board
import adafruit_dht
import time

def c_to_f(temp):
    return temp * 1.8 + 32

def c_to_k(temp):
    return temp + 273.15


class ThermometerHandler:
    _sensor_pin = None
    _sensor = None

    on_log_message = None

    def __init__(self, sensor_pin):
        self._sensor_pin = sensor_pin
        self._sensor = adafruit_dht.DHT22(self._sensor_pin)

    def get_humidity(self):
        # try... handle errors TBC
        return self._sensor.humidity

    def get_temperature(self, unit='f'):
        temp_reading = None
        while True:
            try:
                temp_reading = self._sensor.temperature
            except RuntimeError as error:
                time.sleep(1.0)
                continue
            except Exception as error:
                # Unknown error?
                self._sensor.exit()
                raise error
            if -6.01 <= temp_reading <= 45.01:
                break

        # Got valid reading. Give the info back
        if unit.lower() == 'f':
            return round(c_to_f(temp_reading), 2)
        if unit.lower() == 'c':
            return round(temp_reading, 2)
        if unit.lower() == 'k':
            return round(c_to_k(temp_reading), 2)
        # Bad unit. Don't know what to do with it.
        raise ValueError('Unknown temperature unit: ' + str(unit) + '\n         Check your config file.')

