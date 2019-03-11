#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2019 CANDY LINE INC.
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
import select
import sys
import time
import logging
import logging.handlers
import binascii
import json

from SmartMeshSDK import sdk_version
from SmartMeshSDK.utils import AppUtils, FormatUtils
from SmartMeshSDK.IpMgrConnectorSerial import IpMgrConnectorSerial
from SmartMeshSDK.IpMgrConnectorMux import IpMgrSubscribe
from SmartMeshSDK.protocols.oap \
    import OAPDispatcher, OAPNotif, OAPMessage, OAPClient

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


class ProtocolUtils(object):
    @staticmethod
    def format_mac_address(mac):
        mac_address = None
        if isinstance(mac, list):
            mac_address = '-'.join([('%0.2x' % x) for x in mac])
        elif isinstance(mac, basestring):
            if ':' in mac:
                mac_address = mac.replace(':', '-').lower()
            else:
                mac_address = mac.lower()
        if not mac_address:
            raise ValueError('Unsupported mac address value [%s]' % str(mac))
        return mac_address

    @staticmethod
    def to_byte_array_mac(mac):
        mac_address = None
        if isinstance(mac, list):
            mac_address = mac
        elif isinstance(mac, basestring):
            if '-' in mac:
                mac_address = [
                    int(d, 16) for d in
                    filter(lambda p: p.strip() != '', mac.split('-'))
                ]
            elif ':' in mac:
                mac_address = [
                    int(d, 16) for d in
                    filter(lambda p: p.strip() != '', mac.split(':'))
                ]
        if not mac_address:
            raise ValueError('Unsupported mac address value [%s]' % str(mac))
        return mac_address

    @staticmethod
    def resolve_protocol_type(message):
        return message['protocol'] if 'protocol' in message else 'oap'


class OAPSupport(object):
    TLV_FORMATS = {
        'byte': 'TLVByte',
        'short': 'TLVShort',
        'long': 'TLVLong',
        'string': 'TLVString'
    }

    def __init__(self,
                 send_data_func,
                 send_message_func,
                 emit_event_func):
        self.send_data_func = send_data_func
        self.send_message_func = send_message_func
        self.emit_event_func = emit_event_func
        self.oap_dispatch = OAPDispatcher.OAPDispatcher()
        self.oap_dispatch.register_notif_handler(self.handle_oap_data)
        self.oap_clients = {}
        self.handle_packet = self.oap_dispatch.dispatch_pkt

    def is_supported(self, notif_type, data_notif):
        return data_notif.dstPort == OAPMessage.OAP_PORT

    def send(self, mac, message):
        request_id = message['id'] if 'id' in message else None

        def oap_callback(mac_address, oap_resp):
            self.emit_event_func({
                'protocol': 'oap',
                'event': 'result',
                'id': request_id,
                'mac': ProtocolUtils.format_mac_address(mac_address),
                'command': message['command'],
                'result': oap_resp['result']
            })

        if mac not in self.oap_clients:
            self.oap_clients[mac] = OAPClient.OAPClient(
                ProtocolUtils.to_byte_array_mac(mac),
                self.send_data_func,
                self.oap_dispatch
            )

        # send packet
        self.oap_clients[mac].send(
            # command
            self.to_oap_command(message),
            # address
            self.to_oap_address(message),
            # parameters
            data_tags=self.to_oap_tags(message),
            # callback
            cb=oap_callback
        )

    def handle_oap_data(self, mac, notif):
        """Called when the OAP dispatcher can succesfully parse
           received data as OAP
        """
        mac_address = ProtocolUtils.format_mac_address(mac)
        try:
            message = notif._asdict()
            message['event'] = 'data'
            message['mac'] = mac_address
            message['protocol'] = 'oap'
            self.send_message_func(message)
        except Exception as err:
            self.send_message_func({
                'event': 'error',
                'mac': mac_address,
                'protocol': 'oap',
                'message':
                    'failed to handle OAP data, error ({0})\n{1}'
                    .format(
                        type(err),
                        err
                    )
            })
            sys.exit(99)

    def to_oap_command(self, message):
        m = message['command'].upper() if 'command' in message else 'GET'
        val = OAPMessage.CmdType.__dict__[m] \
            if m in OAPMessage.CmdType.__dict__ \
            else None
        if val is None:
            raise ValueError('Command:[%s] is unknown' % m)
        else:
            return val

    def to_oap_address(self, message):
        a = message['address'].upper() if 'address' in message else None
        if not a:
            raise ValueError('`address` is missing')
        if isinstance(a, list):
            return a
        elif isinstance(a, basestring):
            return [
                int(d) for d in
                filter(lambda p: p.strip() != '', a.split('/'))
            ]
        else:
            raise ValueError('`address` value[%s] is invalid' % str(a))

    def to_oap_tags(self, message):
        tags = message['tags'] if 'tags' in message else []
        return [
            self.to_oap_tlv(tag) for tag in tags
        ]

    def to_oap_tlv(self, tag):
        format = tag['format'].lower() if 'format' in tag else 'byte'
        if format not in OAPSupport.TLV_FORMATS:
            raise ValueError('`format` value[%s] is invalid' % str(format))
        value = tag['value']
        if format != 'string' and isinstance(value, basestring):
            value = int(value, 16)
        return OAPMessage.__dict__[OAPSupport.TLV_FORMATS[format]](
            t=int(tag['tag']), v=value)


class RawSupport(object):
    def __init__(self,
                 send_data_func,
                 send_message_func,
                 emit_event_func):
        self.send_data_func = send_data_func
        self.send_message_func = send_message_func
        self.emit_event_func = emit_event_func

    def is_supported(self, notif_type, data_notif):
        return data_notif.dstPort != OAPMessage.OAP_PORT

    def handle_packet(self, notif_type, data_notif):
        data_notif = data_notif._asdict()
        mac_address = ProtocolUtils.format_mac_address(
            data_notif['macAddress'])
        try:
            message = {
                'event': 'data',
                'notifType': notif_type,
                'mac': mac_address,
                'protocol': 'raw',
                'timestamp': data_notif['utcSecs'],
                'srcPort': data_notif['srcPort'],
                'dstPort': data_notif['dstPort'],
                'payload': {
                    'type': 'Buffer',
                    'data': data_notif['data']
                }
            }
            self.send_message_func(message)
        except Exception as err:
            self.send_message_func({
                'event': 'error',
                'mac': mac_address,
                'protocol': 'raw',
                'message':
                    'failed to handle Raw packet data, error ({0})\n{1}'
                    .format(
                        type(err),
                        err
                    )
            })
            sys.exit(99)

    def send(self, mac, message):
        try:
            payload = message['payload']
            if 'type' in payload and payload['type'] == 'Buffer':
                # Translate a Node.js Buffer object into an int array
                payload = payload['data']
            dst_port = message['dstPort']
            priority = message['priority'] if 'priority' in message else 0
            src_port = message['srcPort'] if 'srcPort' in message else dst_port
            options = message['options'] if 'options' in message else 0
            self.send_data_func(
                # destination MAC
                ProtocolUtils.to_byte_array_mac(mac),
                # priority (0:low,1:mid:2:high)
                priority,
                # source port (2-byte int)
                src_port,
                # destination port (2-byte int)
                dst_port,
                # options (1-byte int)
                options,
                # int array to be sent
                payload
            )
        except Exception as err:
            self.send_message_func({
                'event': 'error',
                'mac': mac,
                'protocol': 'raw',
                'message':
                    'failed to send a Raw packet data, error ({0})\n{1}'
                    .format(
                        type(err),
                        err
                    )
            })


class ProtocolClientProxy(object):
    def __init__(self, serialport=DEFAULT_SERIALPORT):
        # connect to manager
        self.connector = IpMgrConnectorSerial.IpMgrConnectorSerial()
        try:
            self.connector.connect({
                'port': serialport,
            })
        except Exception as err:
            self.send_message({
                'event': 'error',
                'message':
                    'failed to connect to manager at {0}, error ({1})\n{2}'
                    .format(
                        serialport,
                        type(err),
                        err
                    )
            })
            sys.exit(1)

        self.subscriber = IpMgrSubscribe.IpMgrSubscribe(self.connector)
        self.subscriber.start()
        self.subscriber.subscribe(
            notifTypes=[
                IpMgrSubscribe.IpMgrSubscribe.NOTIFEVENT,
                IpMgrSubscribe.IpMgrSubscribe.NOTIFHEALTHREPORT,
            ],
            fun=self.on_notification_event,
            isRlbl=True,
        )
        self.subscriber.subscribe(
            notifTypes=[
                IpMgrSubscribe.IpMgrSubscribe.ERROR,
                IpMgrSubscribe.IpMgrSubscribe.FINISH,
            ],
            fun=self.on_disconnected,
            isRlbl=True,
        )
        self.subscriber.subscribe(
            notifTypes=[
               IpMgrSubscribe.IpMgrSubscribe.NOTIFDATA,
            ],
            fun=self.dispatch_pkt,
            isRlbl=False,
        )
        self.supported_protocols = {
            'oap': OAPSupport(self.connector.dn_sendData,
                              self.send_message,
                              self.emit_event),
            'raw': RawSupport(self.connector.dn_sendData,
                              self.send_message,
                              self.emit_event),
        }

    def dispatch_pkt(self, notif_type, data_notif):
        """A callback function invoked by a subscriber
           on receiving a packet data.
        """
        for p in self.supported_protocols.values():
            if p.is_supported(notif_type, data_notif):
                p.handle_packet(notif_type, data_notif)
                break

    def send_message(self, message):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('** send_message ** message:%s' % (
                json.dumps(message)))
        # The message object will be processed
        # by SmartMeshClientProxy.processEvent().
        print(json.dumps(message))
        sys.stdout.flush()

    def emit_event(self, event):
        try:
            self.send_message(event)
        except Exception as err:
            self.send_message({
                'event': 'error',
                'protocol': 'system',
                'message':
                    'failed to emit an event at {0}, error ({1})\n{2}'
                    .format(
                        serialport,
                        type(err),
                        err
                    )
            })
            sys.exit(1)

    def process_message(self, message_json):
        """Expected message_json structure:
            {
                # Protocol => oap, raw
                "protocol": "oap",
                # destination device mac address (required for send)
                # either : or - can be a deimiter
                "mac": "11:22:33:44:55:66",
                # OAP command for oap protocol
                "command": "PUT",
                # OAP Object Addresses (string or array) for oap protocol
                "address": "/3/2",
                "address": [2,3],
                # OAP Value for oap protocol
                "tags": [
                    {
                        "tag": 0,
                        "format": "byte", # or short, long, string
                        "value": "00bb11" # int array or hex string (numeric)
                    },
                    ...
                ],
                # Raw
                "notifType": "notifData",
                # Raw
                "srcPort": 60000,
                # Raw
                "dstPort": 60000,
                # Raw
                "payload": {
                    "type": "Buffer",
                    "data": []
                },
            }
        """
        message = None
        try:
            message = json.loads(message_json)
        except Exception as err:
            self.send_message({
                'event': 'error',
                'protocol': 'system',
                'message':
                    'failed to parse the message:"{0}", error ({1})\n{2}'
                    .format(
                        message_json,
                        type(err),
                        err
                    )
            })
        if not message:
            return

        mac = ''
        try:
            mac = ProtocolUtils.format_mac_address(message['mac'])
            self.supported_protocols[
                ProtocolUtils.resolve_protocol_type(message)
            ].send(mac, message)
        except Exception as err:
            self.send_message({
                'event': 'error',
                'mac': mac,
                'protocol': 'system',
                'message':
                    'failed to send the message:"{0}", error ({1})\n{2}'
                    .format(
                        message_json,
                        type(err),
                        err
                    )
            })

    def start(self):
        while True:
            time.sleep(0.1)
            message_lines = ''
            while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.readline()
                if line:
                    message_lines += line
                else:  # an empty line means stdin has been closed
                    sys.exit(2)
            if message_lines:
                self.process_message(message_lines)

    def on_notification_event(self, notifName, notifParams):
        """Called when a mote event is issued.
        """
        message = {
            'event': 'notification',
            'type': notifName,
            'protocol': 'system',
        }
        try:
            message['mac'] = ProtocolUtils.format_mac_address(
                             notifParams.macAddress)
        except Exception:
            pass
        self.emit_event(message)

    def on_disconnected(self, notifName, notifParams):
        """Called when the connectionFrame has disconnected.
        """
        # delete the connector
        if self.connector:
            self.connector.disconnect()
        self.connector = None

        # exit with error code 16=>disconnected
        sys.exit(16)


if __name__ == "__main__":
    # ask user for serial port number
    if len(sys.argv) < 2:
        print(json.dumps({
            'event': 'error',
            'message':
                'The serial port argument and/or MAC address is/are missing'
        }))
        sys.stdout.flush()
        sys.exit(1)
    else:
        serialport = sys.argv[1]

    ProtocolClientProxy(serialport).start()
