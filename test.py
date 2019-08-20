# -*- coding:utf8 -*-

# author          :haiyang.song
# email           :meishild@gmail.com
# datetime        :2019-08-19
# version         :1.0
# python_version  :3.4.3
# description     :
# ==============================================================================
from btlewrap import GatttoolBackend


def scan(backend, timeout=10):
    """Scan for mithermometer devices.

    Note: this must be run as root!
    """
    result = []
    for (mac, name) in backend.scan_for_devices(timeout):
        print(mac + " " + name)
    return result


scan(GatttoolBackend)
