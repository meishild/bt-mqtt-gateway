from bluepy.btle import Scanner, DefaultDelegate
from mqtt import MqttMessage, MqttConfigMessage

from workers.base import BaseWorker
import logger

REQUIREMENTS = ['bluepy']
monitoredAttrs = ["stat", "rssi_level", "rssi"]
_LOGGER = logger.get(__name__)


class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            _LOGGER.debug("Discovered new device: %s" % dev.addr)


class BtrssiWorker(BaseWorker):
    def _setup(self):
        _LOGGER.info("Adding %d %s devices", len(self.devices), repr(self))
        for name, mac in self.devices.items():
            _LOGGER.debug("Adding %s device '%s' (%s)", repr(self), name, mac)

    def config(self):
        ret = []
        for name, mac in self.devices.items():
            ret += self.config_device(name, mac)
        return ret

    def config_device(self, name, mac):
        ret = []
        device = {
            "identifiers": [mac, self.format_discovery_id(mac, name)],
            "manufacturer": "bluetooth",
            "model": "rssi",
            "name": self.format_discovery_name(name)
        }

        for attr in monitoredAttrs:
            payload = {
                "unique_id": self.format_discovery_id(mac, name, attr),
                "name": self.format_discovery_name(name, attr),
                "state_topic": self.format_topic(name, attr),
                "device_class": attr,
                "device": device
            }
            ret.append(MqttConfigMessage(MqttConfigMessage.SENSOR, self.format_discovery_topic(mac, name, attr), payload=payload))
        return ret

    def searchmac(self, devices, mac):
        for dev in devices:
            if dev.addr == mac.lower():
                return dev
        return None

    def status_update(self):
        scanner = Scanner().withDelegate(ScanDelegate())
        devices = scanner.scan(5.0)
        ret = []

        for name, mac in self.devices.items():
            _LOGGER.info("Updating %s device '%s' (%s)", repr(self), name, mac)
            device = self.searchmac(devices, mac)
            if device is None:
                ret.append(MqttMessage(topic=self.format_topic(name + '/state'), payload="OFF"))
            else:
                ret.append(MqttMessage(topic=self.format_topic(name + '/rssi'), payload=device.rssi))
                ret.append(MqttMessage(topic=self.format_topic(name + '/state'), payload="ON"))
        return ret
