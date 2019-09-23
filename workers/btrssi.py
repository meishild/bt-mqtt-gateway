from bluepy.btle import Scanner, DefaultDelegate
from mqtt import MqttMessage, MqttConfigMessage

from workers.base import BaseWorker
import logger

REQUIREMENTS = ['bluepy']
monitoredAttrs = ["rssi_level", "rssi"]
_LOGGER = logger.get(__name__)


class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            _LOGGER.debug("Discovered new device: %s" % dev.addr)


def get_rssi_level(rssi):
    if rssi > -85:
        return 4
    elif rssi > -90:
        return 3
    elif rssi > -95:
        return 2
    elif rssi > -100:
        return 1
    else:
        return 0


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
            "name": self.format_discovery_name(mac)
        }

        for attr in monitoredAttrs:
            payload = {
                "unique_id": self.format_discovery_id(mac, name, attr),
                "name": self.format_discovery_name(mac, attr),
                "state_topic": self.format_topic(name, attr),
                "device": device
            }
            if attr == 'rssi':
                payload["unit_of_measurement"] = "dBm"
            if attr == 'rssi_level':
                payload["unit_of_measurement"] = "L"
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
            for attr in monitoredAttrs:
                if attr == 'rssi' and device is not None:
                    ret.append(MqttMessage(topic=self.format_topic(name, attr), payload=device.rssi))
                if attr == 'rssi_level':
                    level = get_rssi_level(device.rssi) if device else -1
                    ret.append(MqttMessage(topic=self.format_topic(name, attr), payload=level))
        return ret
