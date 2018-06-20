import RPi.GPIO as GPIO


class HeaterHandler:
    """MQTT Heater object"""  # __doc__ / docstring

    VERSION = '0.1a'

    # BCM pin of heater power control relay
    _gpio_heater_control_pin = -1

    # [ON] state of the relay IO
    _gpio_heater_control_active = True

    _current_state = False

    # State change callback
    # Signature on_state_change(state: bool)
    on_state_change = None

    # Logger callback
    on_log_message = None

    def __init__(self, heater_output_pin, heater_output_active=True):
        self._gpio_heater_control_pin = heater_output_pin
        self._gpio_heater_control_active = heater_output_active

        self._current_state = not self._gpio_heater_control_active

        GPIO.setmode(GPIO.BCM)

        # Set initial state to OFF (not active)
        GPIO.setup(self._gpio_heater_control_pin, GPIO.OUT, initial=int(self._current_state))

    # Callers will simply say ON, OFF; HIGH, LOW; 1, 0; True, False
    # They need no knowledge of inverted outputs
    def set_state(self, state):
        self.log('Handler: set_state called with value: ' + str(state) + ' and type ' + str(type(state)))
        # Check if new state matches current state
        # If match, exit method
        new_state = self.state_in(state)

        self.log('Handler: set_state parsed value to: ' + str(new_state) + ' and type ' + str(type(new_state)))

        if new_state == self._current_state:
            self.log('Handler: new_state == _current_state. Exiting method')
            return
        # Turn it on
        self._current_state = new_state

        GPIO.output(self._gpio_heater_control_pin, int(self._current_state))
        self.log('Handler: State updated to ' + str(self._current_state) + ' and type ' + str(type(self._current_state)))
        # Trigger callback

        if self.on_state_change is not None:
            self.on_state_change(self.state_out())

    # Callers are ignorant of inverted outputs
    # Make the conversion behind the scenes
    # All incoming states should pass through this method
    def state_in(self, state):
        if not self._gpio_heater_control_active:
            return not state
        return state

    # Callers are ignorant of inverted output
    # All outgoing states should pass through this method
    def state_out(self):
        if not self._gpio_heater_control_active:
            return not self._current_state
        return self._current_state

    def log(self, message):
        if self.on_log_message is not None:
            self.on_log_message(message)

    def cleanup(self):
        GPIO.cleanup()

