from mqtt import MqttMessage, MqttConfigMessage
from workers.base import BaseWorker
import logger

REQUIREMENTS = ['bluepy']
monitoredAttrs = ["temperature", "humidity", "battery", "availability"]
_LOGGER = logger.get(__name__)


class MzbtirWorker(BaseWorker):
    def _setup(self):
        _LOGGER.info("Adding %d %s devices", len(self.devices), repr(self))
        for name, mac in self.devices.items():
            _LOGGER.debug("Adding %s device '%s' (%s)", repr(self), name, mac)
            self.devices[name] = {"mac": mac, "mz": MZBtIr(mac)}

    def config(self):
        ret = []
        for name, data in self.devices.items():
            ret += self.config_device(name, data["mac"])
        return ret

    def config_device(self, name, mac):
        ret = []
        device = {
            "identifiers": [mac, self.format_discovery_id(mac, name)],
            "manufacturer": "Meizu",
            "model": "btir",
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

            if attr == 'temperature':
                payload["unit_of_measurement"] = "°C"
            elif attr == 'humidity':
                payload["unit_of_measurement"] = "%"
            elif attr == 'battery':
                payload["unit_of_measurement"] = "%"

            ret.append(
                MqttConfigMessage(MqttConfigMessage.SENSOR, self.format_discovery_topic(mac, name, attr), payload=payload, retain=True))
        return ret

    def status_update(self):
        _LOGGER.info("Updating %d %s devices", len(self.devices), repr(self))
        ret = []
        for name, data in self.devices.items():
            _LOGGER.debug("Updating %s device '%s' (%s)", repr(self), name, data["mac"])
            from btlewrap import BluetoothBackendException
            try:
                ret += self.update_device_state(name, data["mz"])
                self.fail_count = 0
            except BluetoothBackendException as e:
                logger.log_exception(_LOGGER, "Error during update of %s device '%s' (%s): %s", repr(self), name, data["mac"],
                                     type(e).__name__, suppress=True)
                self.fail_count = self.fail_count + 1
            finally:
                if self.fail_count > self.max_fail_count:
                    ret.append(
                        MqttMessage(
                            self.format_topic(name, "availability"),
                            payload="offline",
                            retain=True
                        )
                    )
                return ret
        return ret

    def update_device_state(self, name, mz):
        ret = []
        for attr in monitoredAttrs:
            ret.append(MqttMessage(topic=self.format_topic(name, attr), payload=mz.parameter_value(attr), retain=True))
        return ret

    def on_command(self, topic, value):
        _LOGGER.info("Command %s %s->%s", repr(self), topic, value)
        _, _, device_name, _ = topic.split('/')

        device = self.devices[device_name]
        value = value.decode('utf-8')
        _LOGGER.debug("Setting %s on %s device '%s' (%s)", value, repr(self), device_name, device["mac"])
        v = value.split(",")
        if v[0] == "send":
            device.send_ir(v[1])
        elif v[0] == "receive":
            r_data = device.receive_ir()
            _LOGGER.info("receive:" + r_data)
        return []


from bluepy.btle import Peripheral
from binascii import a2b_hex
from threading import Lock
from datetime import datetime

SERVICE_UUID = "000016f2-0000-1000-8000-00805f9b34fb"


def get_cr2032_to_battery(v):
    if v > 3:
        return 100
    elif v > 2.98:
        return 80
    elif v > 2.95:
        return 60
    elif v > 2.9:
        return 40
    elif v > 2.78:
        return 20
    elif v > 2:
        return 1
    return 0


class MZBtIr(object):
    def __init__(self, mac, min_update_interval=300):
        """
        Initialize a Meizu for the given MAC address.
        """
        self._mac = mac
        self._lock = Lock()
        self._sequence = 0
        self._min_update_interval = min_update_interval
        if min_update_interval < 60:
            self._min_update_interval = 60
        self._last_update = None
        self._temperature = None
        self._humidity = None
        self._battery = None
        self._receive_handle = None
        self._receive_buffer = None
        self._received_packet = 0
        self._total_packet = -1

    def get_sequence(self):
        self._sequence = self._sequence + 1
        if self._sequence > 255:
            self._sequence = 0
        return self._sequence

    def temperature(self):
        return self._temperature

    def humidity(self):
        return self._humidity

    def battery(self):
        return self._battery

    def parameter_value(self, attr, read_cached=True):
        self.update(not read_cached)
        if attr == "temperature":
            return self._temperature
        elif attr == "humidity":
            return self._humidity
        elif attr == "battery":
            return self._battery
        return "online"

    def update(self, force_update=False):
        if force_update or (self._last_update is None) or (datetime.now() - self._min_update_interval > self._last_update):
            self._lock.acquire()
            p = None
            try:
                p = Peripheral(self._mac, "public")
                ch_list = p.getCharacteristics()
                for ch in ch_list:
                    if str(ch.uuid) == SERVICE_UUID:
                        if p.writeCharacteristic(ch.getHandle(), b'\x55\x03' + bytes([self.get_sequence()]) + b'\x11', True):
                            data = ch.read()
                            temp10 = int.from_bytes(data[4:6], byteorder='little')
                            humi10 = int.from_bytes(data[6:8], byteorder='little')
                            self._temperature = float(temp10) / 100.0
                            self._humidity = float(humi10) / 100.0
                            if p.writeCharacteristic(ch.getHandle(), b'\x55\x03' + bytes([self.get_sequence()]) + b'\x10', True):
                                data = ch.read()
                                self._battery = get_cr2032_to_battery(float(data[4]) / 10.0)
                        break
            except Exception as ex:
                print("Unexpected error: {}".format(ex))
            finally:
                if p is not None:
                    p.disconnect()
                self._lock.release()

    def send_ir(self, key, ir_data):
        self._lock.acquire()
        sent = False
        p = None
        try:
            p = Peripheral(self._mac, "public")
            ch_list = p.getCharacteristics()
            for ch in ch_list:
                if str(ch.uuid) == SERVICE_UUID:
                    sequence = self.get_sequence()
                    if p.writeCharacteristic(ch.getHandle(), b'\x55' + bytes(len(a2b_hex(key)) + 3, [sequence]) + b'\x03' + a2b_hex(key),
                                             True):
                        data = ch.read()
                        if len(data) == 5 and data[4] == 1:
                            sent = True
                        else:
                            send_list = []
                            packet_count = int(len(ir_data) / 30) + 1
                            if len(data) % 30 != 0:
                                packet_count = packet_count + 1
                            send_list.append(
                                b'\x55' + bytes(len(a2b_hex(key)) + 5, [sequence]) + b'\x00' + bytes([0, packet_count]) + a2b_hex(key))
                            i = 0
                            while i < packet_count - 1:
                                if len(ir_data) - i * 30 < 30:
                                    send_ir_data = ir_data[i * 30:]
                                else:
                                    send_ir_data = ir_data[i * 30:(i + 1) * 30]
                                send_list.append(
                                    b'\x55' + bytes([int(len(send_ir_data) / 2 + 4), sequence]) + b'\x00' + bytes([i + 1]) + a2b_hex(
                                        send_ir_data))
                                i = i + 1
                            error = False
                            for j in range(len(send_list)):
                                r = p.writeCharacteristic(ch.getHandle(), send_list[j], True)
                                if not r:
                                    error = True
                                    break
                            if not error:
                                sent = True
                    break
        except Exception as ex:
            print("Unexpected error: {}".format(ex))
        finally:
            if not p:
                p.disconnect()
            self._lock.release()
        return sent

    def receive_ir(self, timeout=15):
        self._lock.acquire()
        self._receive_handle = None
        self._receive_buffer = False
        self._received_packet = 0
        self._total_packet = -1
        p = None
        try:
            p = Peripheral(self._mac, "public")
            ch_list = p.getCharacteristics()
            for ch in ch_list:
                if str(ch.uuid) == SERVICE_UUID:
                    self._receive_handle = ch.getHandle()
                    sequence = self.get_sequence()
                    if p.writeCharacteristic(ch.getHandle(), b'\x55\x03' + bytes([sequence]) + b'\x05', True):
                        data = ch.read()
                        if len(data) == 4 and data[3] == 7:
                            p.withDelegate(self)
                            while self._received_packet != self._total_packet:
                                if not p.waitForNotifications(timeout):
                                    self._receive_buffer = False
                                    break
                            p.writeCharacteristic(ch.getHandle(), b'\x55\x03' + bytes([sequence]) + b'\x0b', True)
                            p.writeCharacteristic(ch.getHandle(), b'\x55\x03' + bytes([sequence]) + b'\x06', True)
                        else:
                            self._receive_buffer = False
                    break
            self._receive_handle = None
        except Exception as ex:
            print("Unexpected error: {}".format(ex))
            self._receive_handle = None
            self._receive_buffer = False
        finally:
            if not p:
                p.disconnect()
            self._lock.release()
        return self._receive_buffer

    def handleNotification(self, cHandle, data):
        if cHandle == self._receive_handle:
            if len(data) > 4 and data[3] == 9:
                if data[4] == 0:
                    self._total_packet = data[5]
                    self._receive_buffer = []
                    self._received_packet = self._received_packet + 1
                elif data[4] == self._received_packet:
                    self._receive_buffer.extend(data[5:])
                    self._received_packet = self._received_packet + 1
                else:
                    self._receive_buffer = False
                    self._total_packet = -1
