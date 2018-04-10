import argparse
import generic_mqtt_switch_config_handler
import switch_handler
import logging
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

LOG_LEVEL = logging.DEBUG

_is_mqtt_connected = False

client = None

logger = None


def get_timed_rotating_logger(switch_name, log_level):
    log_file = 'switch.log'

    # Remove punctuation and directorize Instance Name
    translator = str.maketrans('', '', string.punctuation)

    log_dir = switch_name.translate(translator)
    log_dir = log_dir.replace(' ', '_')
    log_dir += '/'

    # Create the directory if it doesn't exist
    if not path.exists(log_dir):
        mkdir(log_dir)

    log_obj = logging.getLogger(switch_name)
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
parser = argparse.ArgumentParser(description='Control a switch.',
                                 epilog='Not really a switch. Really a relay.',
                                 prog='switch_controller.py')
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
    config = generic_mqtt_switch_config_handler.GenericSwitchConfigurationHandler(args.config_file)
except ConfigError as e:
    print(str(e))
    sys.exit('Error parsing the config file')
except TypeError as e:
    print(str(e))
    sys.exit('Error converting config variable to correct type. Check that all configuration variables '
             'are in the correct format.')


logger = get_timed_rotating_logger(config.SWITCH_NAME,
                                   logging.WARNING)

logger.info('Configuration file successfully loaded')
logger.info('Initializing switch handler...')

# Initialize door
switch = switch_handler.GenericSwitchHandler(config.SWITCH_CONTROL_OUTPUT_PIN,
                                             config.SWITCH_CONTROL_OUTPUT_ACTIVE)


logger.info('Switch handler successfully initialized')
logger.info('Defining definitions...')


def on_connect(client_local, userdata, flags, rc):
    global _is_mqtt_connected
    logger.info('Setting up MQTT subscriptions and publishing initial state data')
    client_local.subscribe(config.MQTT_TOPIC_SET_SWITCH_STATE)
    client_local.publish(config.MQTT_TOPIC_REPORT_SWITCH_STATE, switch.state_out(), qos=1, retain=True)
    logger.info('MQTT successfully connected on port:' + str(config.get_port()))
    logger.info('MQTT Published initial state:' + str(switch.state_out()))
    _is_mqtt_connected = True


def on_disconnect(client_local, userdata, rc):
    global _is_mqtt_connected
    _is_mqtt_connected = False


def on_message(client_local, userdata, msg):
    # Should only get messages from subscribed topic
    # Should convert state message to bool
    # Payload strings are byte arrays. Need to decode them.
    state = parse_bool_payload(msg.payload.decode())
    logger.info('Set switch state message received. Sending command to switch handler.')
    switch.set_state(state)


def on_switch_state_change(state):
    global client
    if client is not None and _is_mqtt_connected:
        client.publish(config.MQTT_TOPIC_REPORT_SWITCH_STATE, state, qos=1, retain=True)
        logger.info('Reporting switch state to MQTT. Current state: ' + str(state))


def on_switch_handler_message(message):
    logger.debug(message)


def parse_bool_payload(state_payload):
    # Payloads are always 'True' or 'False' strings
    state = state_payload.lower()
    return state == 'true'


switch.on_state_change = on_switch_state_change
switch.on_log_message = on_switch_handler_message

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

client.connect(config.MQTT_HOST, port=config.get_port(), keepalive=60)

try:
    client.loop_forever()
except KeyboardInterrupt:
    client.loop_stop()
    logger.info('Switch controller stopped by keyboard input. Cleaning up and exiting...')
except:  # Phooey at your PEP 8 rules. I need to log everything.
    tb = traceback.format_exc()
    logger.error(tb)
    logger.error('Unhandled exception. Quitting...')
finally:
    switch.cleanup()

