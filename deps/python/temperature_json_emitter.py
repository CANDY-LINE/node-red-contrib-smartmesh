#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2018 CANDY LINE INC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import path_hack
import smsdk_install_verifier
import sys
import signal
import atexit
import logging
import logging.handlers

from SmartMeshSDK import sdk_version
from SmartMeshSDK.utils import AppUtils, FormatUtils
from SmartMeshSDK.IpMgrConnectorSerial import IpMgrConnectorSerial
from SmartMeshSDK.IpMgrConnectorMux import IpMgrSubscribe
from SmartMeshSDK.protocols.oap import OAPDispatcher, OAPNotif

DEFAULT_SERIALPORT = '/dev/ttyUSB3'
SYSLOG_ADDRESS = '/var/run/syslog' if sys.platform == "darwin" else '/dev/log'


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


logger = logging.getLogger('SmartMesh_Node')
logger.setLevel(logging.INFO)
handler = logging.handlers.SysLogHandler(address=SYSLOG_ADDRESS)
logger.addHandler(handler)
formatter = logging.Formatter('%(module)s.%(funcName)s: %(message)s')
handler.setFormatter(formatter)
AppUtils.configureLogging()


def handle_data(notifName, notifParams):
    """called when the manager generates a data notification
    """
    # have the OAP dispatcher parse the packet.
    # It will call handle_oap_data() is this data is a valid OAP data.
    oapdispatcher.dispatch_pkt(notifName, notifParams)


def handle_oap_data(mac, notif):
    """called when the OAP dispatcher can succesfully parse received data as OAP
    """
    if isinstance(notif, OAPNotif.OAPTempSample):
        print('{{"temp": {TEMP:.2f}, "address": "{MAC}"}}'.format(
            TEMP=float(notif.samples[0]) / 100,
            MAC=FormatUtils.formatMacString(mac),
        ))


# set up the OAP dispatcher (which parses OAP packets)
oapdispatcher = OAPDispatcher.OAPDispatcher()
oapdispatcher.register_notif_handler(handle_oap_data)

# ask user for serial port number
if len(sys.argv) < 1:
    print('The serial port argument is missing')
    sys.exit(1)
else:
    serialport = sys.argv[1]
if not serialport.strip():
    serialport = DEFAULT_SERIALPORT

# connect to manager
connector = IpMgrConnectorSerial.IpMgrConnectorSerial()
try:
    connector.connect({
        'port': serialport,
    })
except Exception as err:
    print('failed to connect to manager at {0}, error ({1})\n{2}'.format(
        serialport,
        type(err),
        err
    ))
    sys.exit(1)

# subscribe to data notifications
subscriber = IpMgrSubscribe.IpMgrSubscribe(connector)
subscriber.start()
subscriber.subscribe(
    notifTypes=[
        IpMgrSubscribe.IpMgrSubscribe.NOTIFDATA,
    ],
    fun=handle_data,
    isRlbl=False,
)
