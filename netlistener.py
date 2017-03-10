
from __future__ import with_statement
import math
import time
import json
import socket

import weedb
import weewx.drivers
import weeutil.weeutil

DRIVER_NAME = 'NetListener'
DRIVER_VERSION = "0.1"

def loader(config_dict, engine):
    station = NetListener(**config_dict[DRIVER_NAME])
    return station
        
class NetListener(weewx.drivers.AbstractDevice):
    """

    NetListener

    Listens on a UDP port to receive JSON encoded weather data

    """
    
    def __init__(self, **config):
        """Initialize the driver
        
        NAMED ARGUMENTS:
        
        listen_address: The IP address on which to listen for weather data.
        [Optional. Default is 127.0.0.1]

        listen_port: The port on which to listen for weather data.
        [Optional. Default is 8888]
        
        """

        self.listen_address = config.get('listen_address', '127.0.0.1')
        self.listen_port = int(config.get('listen_port', '8888'))

    def genLoopPackets(self):

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(None)
        sock.bind((self.listen_address, self.listen_port))

        while True:
            message, address = sock.recvfrom(1024)
            print(message.decode().strip())
            message = json.loads(message.decode())

            packet = {}
            packet.update(message)

            # packet['dateTime'] = int(packet['dateTime'])

            packet['usUnits'] = weewx.METRIC # FIXME

            yield packet

    @property
    def hardware_name(self):
        return DRIVER_NAME
        

def confeditor_loader():
    return NetListenerConfEditor()

class NetListenerConfEditor(weewx.drivers.AbstractConfEditor):
    @property
    def default_stanza(self):
        return """
[NetListener]
    # This section is for the weewx weather station netlistener driver

    #listen_address: The IP address on which to listen for weather data.
    listen_address = 127.0.0.1

    #listen_port: The port on which to listen for weather data.
    listen_port = 8888

    # The driver to use:
    driver = weewx.drivers.netlistener
"""


if __name__ == "__main__":
    station = NetListener()
    for packet in station.genLoopPackets():
        print weeutil.weeutil.timestamp_to_string(packet['dateTime']), packet
