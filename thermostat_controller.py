import argparse
import logging
import heater_handler
import math
import thermometer_handler
import thermostat_config_handler
import time
import string
import sys
import traceback
import paho.mqtt.client as mqtt

from configparser import Error as ConfigError
from logging.handlers import TimedRotatingFileHandler
from os import access
from os import path
from os import mkdir
from os import R_OK

VERSION = '0.1a'

LOG_LEVEL = logging.INFO

client = None
logger = None

_is_mqtt_connected = False

_target_temperature = None
_target_temperature_upper = None
_target_temperature_lower = None


def get_timed_rotating_logger(thermo_name, log_level):
    log_file = 'thermostat.log'

    # Remove punctuation and directorize Instance Name
    translator = str.maketrans('', '', string.punctuation)

    log_dir = thermo_name.translate(translator)
    log_dir = log_dir.replace(' ', '_')
    log_dir += '/'

    # Create the directory if it doesn't exist
    if not path.exists(log_dir):
        mkdir(log_dir)

    log_obj = logging.getLogger(thermo_name)
    log_obj.setLevel(log_level)

    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')

    handler = TimedRotatingFileHandler(log_dir + log_file,
                                       when='midnight',
                                       backupCount=14)

    handler.setFormatter(formatter)

    log_obj.addHandler(handler)

    return log_obj


# Get the config file name
parser = argparse.ArgumentParser(description='Control temperature',
                                 epilog='We like it hot, but not too hot',
                                 prog='thermostat_controller.py')
parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + VERSION)
parser.add_argument('-c', '--config', type=str, default='example.config', dest='config_file',
                    help='File name of the config file used to launch the daemon.'
                         'If in the local directory (./) input only the file name.'
                         'If in another directory, input the full path.                 '
                         'The program MUST be run using a config file. If one is not '
                         'specified, the default example.config will be used. Make a '
                         'copy of example.config and modify the settings to suit your needs.')

# Get the config file name
args = parser.parse_args()

if not path.isfile(args.config_file) or not access(args.config_file, R_OK):
    print('The configuration file could not be found or read access was denied by the system.')
    sys.exit('Unable to access config file: ' + args.config_file)

# Parse the config file

try:
    config = thermostat_config_handler.ThermostatConfigurationHandler(args.config_file)
except ConfigError as e:
    print(str(e))
    sys.exit('Error parsing the config file')
except TypeError as e:
    print(str(e))
    sys.exit('Error converting config variable to correct type. Check that all configuration variables '
             'are in the correct format.')


logger = get_timed_rotating_logger(config.THERMOSTAT_NAME,
                                   LOG_LEVEL)

logger.info('Configuration file successfully loaded')
logger.info('Initializing handlers...')

# Initialize door
heater = heater_handler.HeaterHandler(config.HEATER_CONTROL_OUTPUT_PIN,
                                      config.HEATER_CONTROL_OUTPUT_ACTIVE)

logger.info('Heater handler successfully initialized')

thermo = thermometer_handler.ThermometerHandler(config.TEMPERATURE_SENSOR_ID)

logger.info('Thermometer handler successfully initialized')

logger.info('Defining definitions...')


def on_connect(client_local, userdata, flags, rc):
    global _is_mqtt_connected
    logger.info('Setting up MQTT subscriptions and publishing initial state data')
    client_local.subscribe(config.MQTT_TOPIC_SET_TEMP_TARGET)
    client_local.publish(config.MQTT_TOPIC_REPORT_HEATER_STATE,
                         heater.state_out(),
                         qos=1,
                         retain=True)
    client_local.publish(config.MQTT_TOPIC_REPORT_TEMP,
                         thermo.get_temperature(config.TEMPERATURE_UNIT),
                         qos=1,
                         retain=True)
    client_local.publish(config.MQTT_TOPIC_REPORT_TEMP_TARGET,
                         _target_temperature,
                         qos=1,
                         retain=True)
    logger.info('MQTT successfully connected on port:' + str(config.get_port()))
    _is_mqtt_connected = True


def on_disconnect(client_local, userdata, rc):
    global _is_mqtt_connected
    _is_mqtt_connected = False


def on_message(client_local, userdata, msg):
    global _target_temperature
    if msg.topic == config.MQTT_TOPIC_SET_TEMP_TARGET:
        set_target_temperature(float(msg.payload))
        client_local.publish(config.MQTT_TOPIC_REPORT_TEMP_TARGET,
                             _target_temperature,
                             qos=1,
                             retain=True)
        config.save_target_temp(str(_target_temperature))
    else:
        logger.error('Received message from non subscribed topic. This should never happen...: ' + str(msg.topic))


def on_heater_state_change(state):
    global client
    if client is not None and _is_mqtt_connected:
        client.publish(config.MQTT_TOPIC_REPORT_HEATER_STATE, state, qos=1, retain=True)
        logger.info('Reporting heater state to MQTT. Current state: ' + str(state))


def on_log_message(message):
    logger.debug(message)


def parse_bool_payload(state_payload):
    # Payloads are always 'True' or 'False' strings
    state = state_payload.lower()
    return state == 'true'


def set_target_temperature(temp):
    global _target_temperature, _target_temperature_lower, _target_temperature_upper, client
    _target_temperature = temp
    _target_temperature_lower = temp - config.TEMPERATURE_RANGE
    _target_temperature_upper = temp + config.TEMPERATURE_RANGE


heater.on_state_change = on_heater_state_change
heater.on_log_message = on_log_message
thermo.on_log_message = on_log_message

set_target_temperature(config.TEMPERATURE_TARGET_DEFAULT)

logger.info('Definitions successfully defined')
logger.info('Configuring MQTT client...')

client = mqtt.Client()
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message

if config.MQTT_USE_SSL:
    logger.info('MQTT SSL Enabled')
    client.tls_set()
else:
    logger.info('MQTT connection will not be using SSL')

if config.MQTT_USE_AUTHENTICATION:
    logger.info('Setting MQTT username and password')
    client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
else:
    logger.info('Setting MQTT to anonymous login')

logger.info('MQTT successfully configured')
logger.info('Creating MQTT connection to host: ' + config.MQTT_HOST)


try:
    client.connect(config.MQTT_HOST, port=config.get_port(), keepalive=60)
    client.loop_start()
    current_temp = 0.0
    last_temp = 0.0

    while True:
        # Get current temperature
        current_temp = thermo.get_temperature(config.TEMPERATURE_UNIT)

        # Only publish if changed more than a tenth of a degree
        # No need to flood the mqtt broker
        if not math.isclose(current_temp, last_temp, abs_tol=0.1):
            client.publish(config.MQTT_TOPIC_REPORT_TEMP, current_temp, qos=1, retain=True)
            last_temp = current_temp
            logger.debug('Got temp: ' + str(current_temp))
            logger.debug('Target  : ' + str(_target_temperature))

        if heater.state_out() is False and current_temp < _target_temperature_lower:
            logger.info("Temperature below threshold. Powering heater on.")
            heater.set_state(True)

        elif heater.state_out() is True and current_temp > _target_temperature_upper:
            logger.info("Temperature above threshold. Powering heater off.")
            heater.set_state(False)

        time.sleep(0.5)

except KeyboardInterrupt:
    client.loop_stop()
    logger.info('Thermostat controller stopped by keyboard input. Cleaning up and exiting...')
except:  # Phooey at your PEP 8 rules. I need to log everything.
    tb = traceback.format_exc()
    logger.error(tb)
    logger.error('Unhandled exception. Quitting...')
finally:
    heater.cleanup()

