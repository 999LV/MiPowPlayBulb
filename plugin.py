"""
MiPow PlayBulbs plugin for Domoticz

Author: Logread,
        inspired by the plugin developed by zaraki673 (https://github.com/papagei9/python-mipow) that no longer seems
        to be maintained

Compatibility: Linux only

Requires:
    1) MiPowPlayBulbAPI.py module (in same github repo)
    2) BluePy: See https://github.com/IanHarvey/bluepy  - install it from source
        and depending on your python version and system you might need to make a symlink such as for example:
        sudo ln -s /usr/local/lib/python3.5/dist-packages/bluepy /usr/lib/python3.5/

Versions:   2018.11.02 (beta) - first release
            2018.11.04 (beta) - battery level can be tracked with a dedicated device showing up in the GUI:
                                this is derived from my BatteryLevel plugin (https://github.com/999LV/BatteryLevel).
                                Also some minor edits
"""
"""
<plugin key="MiPowPlayBulb" name="MiPow PlayBulb Python Plugin" author="logread" version="2018.11.04" wikilink="https://www.domoticz.com/wiki/Plugins.html" externallink="https://github.com/999LV/MiPowPlayBulb">
    <description>
MiPow PlayBulb plugin<br/><br/>
Control MiPow PlayBulb Bluetooth LE LED lamps<br/>
requires "BluePy" to be installed. See https://github.com/IanHarvey/bluepy  - install it from source<br/>
and depending on your python version and system you might need to make a symlink such as for example:<br/>
sudo ln -s /usr/local/lib/python3.5/dist-packages/bluepy /usr/lib/python3.5/<br/>
    </description>
    <params>
        <param field="Port" label="Bluetooth interface" width="75px">
            <options>
                <option label="hci0" value="0" default="true"/>
                <option label="hci1" value="1"/>
                <option label="hci2" value="2"/>
                <option label="hci3" value="3"/>
            </options>
        </param>
        <param field="Address" label="Lamp Bluetooth MAC address" width="200px" required="true" default="FF:FF:FF:FF"/>
        <param field="Mode1" label="Battery poll" width="100px">
            <options>
                <option label="1 hour" value="1"/>
                <option label="6 hours" value="6" default="true"/>
                <option label="24 hours" value="24"/>
            </options>
        </param>
        <param field="Mode2" label="Battery level device" width="50px">
            <options>
                <option label="Yes" value="1"/>
                <option label="No" value="0" default="true"/>
            </options>
        </param>
        <param field="Mode6" label="Debug" width="150px">
            <options>
                <option label="None" value="0"  default="true" />
                <option label="Python Only" value="2"/>
                <option label="Basic Debugging" value="62"/>
                <option label="Basic+Messages" value="126"/>
                <option label="Connections Only" value="16"/>
                <option label="Connections+Python" value="18"/>
                <option label="Connections+Queue" value="144"/>
                <option label="All (super verbose)" value="1"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import json
from datetime import datetime, timedelta
import time
import MiPowPlayBulbAPI as API

icons = {"mipowplaybulbfull": "mipowplaybulbfull icons.zip",
         "mipowplaybulbok": "mipowplaybulbok icons.zip",
         "mipowplaybulblow": "mipowplaybulblow icons.zip",
         "mipowplaybulbempty": "mipowplaybulbempty icons.zip"}

class BasePlugin:


    def __init__(self):
        self.lamp = None
        self.levelWhite = 0
        self.levelRed = 0
        self.levelGreen = 0
        self.levelBlue = 0
        self.effect = 255  # effects are Off)
        self.speed = 1 # fastest effects speed
        self.battery = 255
        self.nextpoll = datetime.now()  # battery polling heartbeat counter


    def onStart(self):

        Domoticz.Debugging(int(Parameters["Mode6"]))

        # load custom battery images
        for key, value in icons.items():
            if key not in Images:
                Domoticz.Status("Icon with key '{}' does not exist... Creating".format(key))
                Domoticz.Image(value).Create()
            else:
                Domoticz.Debug("Icon {} - {} with key '{}' already exists".format(
                    Images[key].ID, Images[key].Name, key))

        # set up the devices for the plugin
        if 1 not in Devices:
            Domoticz.Device(Name="Switch", Unit=1, Type=241, Subtype=1, Switchtype=7, Used=1).Create()
        else:
            Domoticz.Debug(
                "Color dictionnary = {}, LastLevel = {}".format(Devices[1].Color, Devices[1].LastLevel))
            try:
                ColorDict = json.loads(Devices[1].Color)
                self.levelWhite = int(ColorDict["cw"] * Devices[1].LastLevel / 100)
                self.levelRed = int(ColorDict["r"] * Devices[1].LastLevel / 100)
                self.levelGreen = int(ColorDict["g"] * Devices[1].LastLevel / 100)
                self.levelBlue = int(ColorDict["b"] * Devices[1].LastLevel / 100)
            except:
                Domoticz.Error("Warning: No color data in Switch device")

        if 2 not in Devices:
            Options = {"LevelActions": "|||||",
                       "LevelNames": "Off|Flash|Pulse|Hard|Soft|Candle",
                       "LevelOffHidden": "false",
                       "SelectorStyle": "0"}
            Domoticz.Device(Name="Effects", Unit=2, TypeName="Selector Switch", Switchtype=18, Image=14,
                            Options=Options, Used=1).Create()
        else:
            self.effect = 255 if Devices[2].sValue == "" else int(float(Devices[2].sValue) / 10) - 1

        if 3 not in Devices:
            Domoticz.Device(Name="Speed", Unit=3, Type=244, Subtype=73, Switchtype=7, Image=14, Used=1).Create()
        else:
            self.speed = max(int((100 - Devices[3].LastLevel) / 100 * 255), 1)  # speed 1 = Fastest, speed 255 = Slowest

        self.lamp = API.MiPowLamp(int(Parameters["Port"]), Parameters["Address"], int(Parameters["Mode6"]))
        if self.lamp:
            self.lamp.timeout = 5  # we set 5 seconds for first discovery of the bluetooth device
            self.lamp.connect()
        if self.lamp.connected:
            self.lamp.timeout = 2  # connect went well, so we can afford a shorter timeout (to be tested)
            self._ResetLamp()

        if Parameters["Mode2"] == "1":
            if 4 not in Devices:
                Domoticz.Device(Name="Battery", Unit=4, TypeName="Custom", Options={"Custom": "1;%"}).Create()
            else:
                # should we delete existing device if it is no longer wanted ?
                pass  # for now


    def onStop(self):

        Domoticz.Log("onStop - Plugin is stopping.")
        self.lamp.disconnect()


    def onCommand(self, Unit, Command, Level, Color):

        Domoticz.Debug(
            "onCommand called for Unit {}: Command '{}', Level: {}, Color: {}".format(Unit, Command, Level, Color))

        if Unit == 1:  # Main switch
            if Command == "On":
                if self.lamp.set_rgbw(self.levelRed, self.levelGreen, self.levelBlue, self.levelWhite):
                    self._updateDevice(Unit, nValue=1, TimedOut=0)
                    # resend effect and speed as these are lost when lamp is switched off
                    time.sleep(1)
                    self.lamp.set_effect(self.effect)
                    self.lamp.set_speed(self.speed)
                else:
                    self._updateDevice(Unit, TimedOut=1)

            elif Command == "Off":
                if self.lamp.off():
                    self._updateDevice(Unit, nValue=0, TimedOut=0)
                else:
                    self._updateDevice(Unit, TimedOut=1)

            elif Command == "Set Color":
                ColorDict = json.loads(Color)
                Domoticz.Debug("Color dictionnary = {}, LastLevel = {}".format(Devices[1].Color, Devices[1].LastLevel))
                if ColorDict["m"] == 1 or ColorDict["m"] == 3:
                    self.levelRed = int(ColorDict["r"] * Level / 100)
                    self.levelGreen = int(ColorDict["g"] * Level / 100)
                    self.levelBlue = int(ColorDict["b"] * Level / 100)
                    self.levelWhite = int(ColorDict["ww"] * Level / 100)
                    if self.lamp.set_rgbw(self.levelRed, self.levelGreen, self.levelBlue, self.levelWhite):
                        self._updateDevice(Unit, nValue=1, sValue=str(Level), Color=Color, TimedOut=0)
                    else:
                        self._updateDevice(Unit, TimedOut=1)
                else:
                    Domoticz.Error("Invalid 'Set Color' m-value: {}".format(ColorDict["m"]))

            elif Command == "Set Level":
                LastLevel = 100 if Devices[1].LastLevel == 0 else Devices[1].LastLevel
                self.levelRed = int(self.levelRed / LastLevel * Level)
                self.levelGreen = int(self.levelGreen / LastLevel * Level)
                self.levelBlue = int(self.levelBlue / LastLevel * Level)
                self.levelWhite = int(self.levelWhite / LastLevel * Level)
                if self.lamp.set_rgbw(self.levelRed, self.levelGreen, self.levelBlue, self.levelWhite):
                    self._updateDevice(Unit, nValue=1, sValue=str(Level), Color=Color, TimedOut=0)
                else:
                    self._updateDevice(Unit, TimedOut=1)
            else:
                Domoticz.Error("Device {} has sent an unknown command: {}".format(Devices[Unit].Name, Command))

        elif Unit == 2:  # Effects selector switch
            self.effect = 255 if Level == 0 else int(float(Level) / 10) -1
            if self.lamp.set_effect(self.effect):
                self._updateDevice(Unit,
                                   nValue=0 if self.effect == 255 else 1,
                                   sValue="" if self.effect == 255 else str((self.effect + 1) * 10),
                                   TimedOut=0)
            else:
                self._updateDevice(Unit, TimedOut=1)

        elif Unit == 3:  # Speed dimmer switch
            self.speed = max(int((100 - Level) / 100 * 255), 1)
            if self.lamp.set_speed(self.speed):
                self._updateDevice(Unit, nValue=0 if self.speed == 0 else 1, sValue=str(Level), TimedOut=0)
            else:
                self._updateDevice(Unit, TimedOut=1)


    def onHeartbeat(self):

        now = datetime.now()
        if self.nextpoll <= now:
            self.nextpoll = now + timedelta(hours=int(Parameters["Mode1"]))
            Domoticz.Debug("next poll will be{}".format(self.nextpoll))
            if self.lamp.get_state():
                self.battery = int(self.lamp.battery)
                self._updateDevice(1, BatteryLevel=self.battery)
                # we update the battery level device if the user wants to see it
                if Parameters["Mode2"] == "1" and not self.battery == 255:
                    if self.battery >= 75:
                        icon = "mipowplaybulbfull"
                    elif self.battery >= 50:
                        icon = "mipowplaybulbok"
                    elif self.battery >= 25:
                        icon = "mipowplaybulblow"
                    else:
                        icon = "mipowplaybulbempty"
                    try:
                        self._updateDevice(4, nValue=0, sValue=str(self.battery), Image=Images[icon].ID)
                    except Exception as error:
                        Domoticz.Error("Failed to update battery level device due to: {}".format(error))


    @staticmethod
    def _updateDevice(Unit, **kwargs):
        if Unit in Devices:
            #if Parameters["Mode6"] != "0":
            #    DumpDeviceAttribs(Unit)

            # check if kwargs contain an update for nValue or sValue... if not, use the existing one(s)
            if "nValue" in kwargs:
                nValue = kwargs["nValue"]
            else:
                nValue = Devices[Unit].nValue
            if "sValue" in kwargs:
                sValue = kwargs["sValue"]
            else:
                sValue = Devices[Unit].sValue

            # build the arguments for the call to Device.Update
            update_args = {"nValue": nValue, "sValue": sValue}
            change = False
            if nValue != Devices[Unit].nValue or sValue != Devices[Unit].sValue:
                change = True
            for arg in kwargs:
                if arg == "TimedOut":
                    if kwargs[arg] != Devices[Unit].TimedOut:
                        change = True
                        update_args[arg] = kwargs[arg]
                    Domoticz.Debug("TimedOut = {}".format(kwargs[arg]))
                if arg == "BatteryLevel":
                    if kwargs[arg] != Devices[Unit].BatteryLevel:
                        change = True
                        update_args[arg] = kwargs[arg]
                    Domoticz.Debug("BatteryLevel = {}".format(kwargs[arg]))
                if arg == "Color":
                    try:
                        if kwargs[arg] != Devices[Unit].Color:
                            change = True
                    except:
                        change = True
                    finally:
                        if change:
                            update_args[arg] = kwargs[arg]
                    Domoticz.Debug("Color = {}".format(kwargs[arg]))
                if arg == "Image":
                        if kwargs[arg] != Devices[Unit].Image:
                            change = True
                            update_args[arg] = kwargs[arg]
            Domoticz.Debug("Change in device {} = {}".format(Unit, change))
            if change:
                Devices[Unit].Update(**update_args)


    def _ResetLamp(self):
        # switch what needs to be switched
        if Devices[1].nValue == 1:  # lamp should be on
            self.lamp.set_rgbw(self.levelRed, self.levelGreen, self.levelBlue, self.levelWhite)
        else:
            self.lamp.off()

        # update effects
        self.lamp.set_effect(self.effect)

        # update speed
        self.lamp.set_speed(self.speed)

        # get battery level
        self.lamp.get_state()
        self.battery = int(self.lamp.battery)


global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()


# Generic helper functions

def DumpDeviceAttribs(Unit):
    Domoticz.Debug("Device {}.nValue = {}".format(Unit, Devices[Unit].nValue))
    Domoticz.Debug("Device {}.sValue = {}".format(Unit, Devices[Unit].sValue))
    Domoticz.Debug("Device {}.LastLevel = {}".format(Unit, Devices[Unit].LastLevel))
    Domoticz.Debug("Device {}.Color = {}".format(Unit, Devices[Unit].Color))
    Domoticz.Debug("Device {}.TimedOut = {}".format(Unit, Devices[Unit].TimedOut))
    Domoticz.Debug("Device {}.BatteryLevel = {}".format(Unit, Devices[Unit].BatteryLevel))


def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return
