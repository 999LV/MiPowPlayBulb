"""
Python module to interface with MiPow PlayBulbs lamps

it requires "BluePy" to be installed. See https://github.com/IanHarvey/bluepy  - install it from source
and depending on your python version and system you might need to make a symlink such as for example:
   sudo ln -s /usr/local/lib/python3.5/dist-packages/bluepy /usr/lib/python3.5/

written by Logread based on work by Arttu Mahlakaarto and Matthew Garret,
with improved bluetooth characteristics detection

Also credits to Heckie75 (https://github.com/Heckie75/Mipow-Playbulb-BTL201)

This code is released under the terms of the MIT license. See the LICENSE
file for more details.

Version:    2018.7.15 (beta)

"""


from bluepy import btle
from datetime import datetime, timedelta
import time

# if we are running as a plugin embedded in Domoticz then we need to overwrite python's logging module with Domoticz's
# logging methods
class Logger:

    def __init__(self):
        self.error = Domoticz.Error
        self.debug = Domoticz.Debug
        self.info = Domoticz.Status
        self.debugging = Domoticz.Debugging

try:
    import Domoticz
except:
    import logging
    domoticz = False
else:
    logging = Logger()
    domoticz = True



_MANUFACTURER = "Mipow Limited"

# below are types of PlayBulb that "should" work with this code... requires user feedback to confirm
# source of info is https://github.com/Heckie75/Mipow-Playbulb-BTL201
_SERIAL = ("BTL300",    # PlayBulb Candle - tested
           "BTL200",    # PlayBulb Rainbow - untested
           "BTL201",    # Playbulb Smart - untested
           "BTL203",    # Playbulb Spot Mesh - untested
           "BTL301W",   # Playbulb Sphere - untested
           "BTL400",    # Playbulb Garden - untested
           "BTL501A",   # Playbulb Comet - untested
           "BTL505-GN", # Playbulb String - untested
           "BTL601")    # Playbulb Solar - untested

class Delegate(btle.DefaultDelegate):
    """Delegate Class."""

    def __init__(self, bulb):
        self.bulb = bulb
        btle.DefaultDelegate.__init__(self)


class MiPowLamp:

    def __init__(self, interface, mac, debug):
        global domoticz
        if domoticz:
            logging.debugging = debug
            logging.debug("this is a test of the debugging...")
        self.timeout = 2 # seconds timeout for bluetooth connection
        self.interface = interface
        self.mac = mac
        self.device = None
        self.manufacturer = None
        self.serial = None
        self.name = None
        self.battery = 255
        self.power = False
        self.handlename = None
        self.handlebattery = None
        self.handleWRGB = None
        self.handleWRGBES = None
        self.connected = False
        self.white = 0
        self.red = 0
        self.green = 0
        self.blue = 0
        self.effect = 0
        self.speed = 0
        self.errmsg = ""


    def connect(self):
        self.errmsg = ""
        timeout_time = datetime.now() + timedelta(seconds=self.timeout)
        while datetime.now() < timeout_time:
            logging.debug("I am in the connect loop")
            try:
                self.device = btle.Peripheral(self.mac, addrType=btle.ADDR_TYPE_PUBLIC, iface=self.interface)
                self.connected = True
                characteristics = self.device.getCharacteristics()
                for characteristic in characteristics:
                    hook = characteristic.uuid.getCommonName()
                    handle = characteristic.getHandle()
                    if hook == "Manufacturer Name String":
                        self.handlename = handle
                        self.manufacturer = self.device.readCharacteristic(handle).decode('utf-8')
                    if hook == "Serial Number String":
                        self.handlename = handle
                        self.serial = self.device.readCharacteristic(handle).decode('utf-8')
                    if hook == "Device Name":
                        self.handlename = handle
                        self.name = self.device.readCharacteristic(handle).decode('utf-8')
                    elif hook == "Battery Level":
                        self.handlebattery = handle
                    elif hook == "fffc":
                        self.handleWRGB = handle
                    elif hook == "fffb":
                        self.handleWRGBES = handle
                if self.manufacturer != _MANUFACTURER and not self.serial in _SERIAL:
                    logging.error("Device found is not supported: Manufacturer = '{}', Serial = '{}' !".format(
                        self.name, self.manufacturer, self.serial))
                else:
                    logging.info("Connected to device: Name = '{}', Manufacturer = '{}', Serial = '{}'".format(
                        self.name, self.manufacturer, self.serial))
                    logging.debug("Bluetooth Color Handle = {}".format(hex(self.handleWRGB)))
                    logging.debug("Bluetooth Effects Handle = {}".format(hex(self.handleWRGBES)))
                    self.get_state()
                return True
            except btle.BTLEException as error:
                self.connected = False
                self.errmsg = "MiPowPlayBulbAPI connection error: {}".format(error)
                logging.error(self.errmsg)
                time.sleep(0.1)  # sleep a little bit before trying to reconnect
        return False


    def disconnect(self):
        logging.debug("Disconnecting device '{}'".format(self.name))
        self.connected = False
        self.device.disconnect()


    def _send_packet(self, handleId, data):
        self.errmsg = ""
        if not self.connected:
            self.connect()
        if self.connected:
            try:
                self.device.writeCharacteristic(handleId, data)
                return True
            except btle.BTLEException as error:
                self.errmsg = "MiPowPlayBulbAPI packet send error: {}".format(error)
                logging.error(self.errmsg)
        return False


    def off(self):
        self.power = False
        self.white = 0
        self.red = 0
        self.green = 0
        self.blue = 0
        packet = bytearray([0x00, 0x00, 0x00, 0x00])
        return self._send_packet(self.handleWRGB, packet)


    def set_white(self, level):
        self.power = True
        self.white = level
        self.red = 0
        self.green = 0
        self.blue = 0
        packet = bytearray([self.white, self.red, self.green, self.blue])
        return self._send_packet(self.handleWRGB, packet)


    def set_rgb(self, red, green, blue):
        self.white = 0
        self.red = red
        self.green = green
        self.blue = blue
        packet = bytearray([self.white, self.red, self.green, self.blue])
        return self._send_packet(self.handleWRGB, packet)


    def set_rgbw(self, red, green, blue, white):
        self.white = white
        self.red = red
        self.green = green
        self.blue = blue
        logging.info("function set_rgb: red={}, green={}, blue={}, white={}".format(red, green, blue, white))
        packet = bytearray([self.white, self.red, self.green, self.blue])
        return self._send_packet(self.handleWRGB, packet)


    def set_effect(self, effect):
        self.effect = effect
        packet = bytearray([self.white, self.red, self.green, self.blue, self.effect, 0x00, self.speed, self.speed])
        return self._send_packet(self.handleWRGBES, packet)


    def set_speed(self, speed):
        self.speed = speed
        packet = bytearray([self.white, self.red, self.green, self.blue, self.effect, 0x00, self.speed, self.speed])
        return self._send_packet(self.handleWRGBES, packet)


    def get_state(self):
        errmsg = None
        if not self.connected:
            self.connect()
        if self.connected:
            try:
                status = self.device.readCharacteristic(self.handleWRGB)
                if bytearray(status) != bytearray([0, 0, 0, 0]):
                    self.power = True
                else:
                    self.power = False
                self.white = status[0]
                self.red = status[1]
                self.green = status[2]
                self.blue = status[3]
                # get effect and speed
                # note that handleWRGBES also provides actual real-time color data based on current effect and speed
                status = self.device.readCharacteristic(self.handleWRGBES)
                self.effect = status[4]
                self.speed = status[6]
                # let's update the battery level
                self.battery = int.from_bytes(self.device.readCharacteristic(self.handlebattery), byteorder='big')
                return True
            except btle.BTLEException as error:
                errmsg = "MiPowPlayBulbAPI status read error: {}".format(error)
                logging.error(errmsg)
        return False
