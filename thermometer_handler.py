import math

from w1thermsensor import W1ThermSensor


def c_to_f(temp):
    return temp * 1.8 + 32


def c_to_k(temp):
    return temp + 273.15


class ThermometerHandler:
    _sensor_id = None
    _sensor = None

    on_log_message = None

    def __init__(self, sensor_id):
        self._sensor_id = sensor_id
        self._sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, self._sensor_id)

    def get_temperature(self, unit='f'):
        # temp_reading = None
        counter = 0
        while True:
            temp_reading = self._sensor.get_temperature(W1ThermSensor.DEGREES_C)
            if -6.01 <= temp_reading <= 45.01:
                break
            counter += 1
            if self.on_log_message is not None:
                self.on_log_message("ThermometerHandler: Bad temperature reading: " + str(temp_reading))
            if counter > 30:
                raise IOError("Temperature sensor not connected or not functioning correctly")

        # Got valid reading. Give the info back
        if unit.lower() == 'f':
            return round(c_to_f(temp_reading), 2)
        if unit.lower() == 'c':
            return round(temp_reading, 2)
        if unit.lower() == 'k':
            return round(c_to_k(temp_reading), 2)
        # Bad unit. Don't know what to do with it.
        raise ValueError('Unknown temperature unit: ' + str(unit) + '\n         Check your config file.')

