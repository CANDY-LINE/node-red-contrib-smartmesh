/**
 * @license
 * Copyright (c) 2019 CANDY LINE INC.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

'use strict';

import 'source-map-support/register';
import fs from 'fs';
import serialport from 'serialport';
import { SmartMeshClientProxy } from './smartmesh-common';

export default function(RED) {

  let smartMeshClients = {};
  let exitHandler = () => {
    Object.keys(smartMeshClients).forEach((serialport) => {
      smartMeshClients[serialport].shutdown();
    });
  };
  process.on('exit', exitHandler);
  if (RED.settings && RED.settings.exitHandlers) {
    RED.settings.exitHandlers.push(exitHandler);
  }

  class SmartMeshManagerNode {
    constructor(n) {
      RED.nodes.createNode(this, n);
      this.serialport = n.serialport;
      if (smartMeshClients[this.serialport]) {
        throw new Error(`Duplicate serialport configuration for SmartMeshManagerNode!`);
      }
      this.identifier = n.identifier;
      this.enabled = !!n.enabled;
      this.redirectSmartMeshManagerLog = !!n.redirectSmartMeshManagerLog;
      this.nodes = {};
      ['connected', 'disconnected', 'error'].forEach(ev => {
        this.on(ev, (...params) => {
          try {
            Object.keys(this.nodes).forEach(id => {
              this.nodes[id].emit(ev, params);
            });
          } catch (e) {
            this.error(e);
          }
        });
      });
      this.on('event', (message) => {
        try {
          Object.keys(this.nodes).forEach(id => {
            if (!this.nodes[id].input) {
              return;
            }
            if (this.nodes[id].subscriptionType && this.nodes[id].subscriptionType !== 'all') {
              if (message.event !== this.nodes[id].subscriptionType) {
                return;
              }
            }
            message.managerId = this.identifier;
            this.nodes[id].send({
              payload: message
            });
          });
        } catch (e) {
          this.error(e);
        }
      });
      this.on('error-event', (message) => {
        if (message.event === 'error') {
          message.managerId = this.identifier;
          this.error(`SmartMesh error`, { payload: message });
        }
      });
      this.on('close', (done) => {
        delete smartMeshClients[this.serialport];
        this.client.shutdown().then(() => {
          done();
        }).catch((err) => {
          this.log(err);
          done();
        });
      });
      let self = this;
      this.operations = {
        register(node) {
          if (node) {
            if (self.nodes[node.id]) {
              return false;
            }
            self.nodes[node.id] = node;
            if (self.client.isConnected()) {
              node.emit('connected');
            } else {
              node.emit('disconnected');
            }
            return true;
          }
          return false;
        },
        remove(node) {
          if (node) {
            if (self.nodes[node.id]) {
              delete self.nodes[node.id];
              return true;
            }
          }
          return false;
        },
        shutdown() {
          return self.client.shutdown();
        },
        send(message) {
          return self.client.send(message);
        }
      };
      this.client = new SmartMeshClientProxy(this);
      if (this.enabled) {
        smartMeshClients[this.serialport] = this.client;
        this.client.start();
      } else {
        process.nextTick(() => {
          this.emit('disconnected');
        });
      }
    }
  }
  RED.nodes.registerType('SmartMesh manager', SmartMeshManagerNode);

  class SmartMeshInNode {
    constructor(n) {
      RED.nodes.createNode(this, n);
      this.name = n.name;
      this.input = true;
      this.subscriptionType = n.subscriptionType;
      this.smartMeshManagerNodeId = n.smartMeshManager;
      this.smartMeshManagerNode = RED.nodes.getNode(this.smartMeshManagerNodeId);
      if (this.smartMeshManagerNode) {
        this.on('connected', (n=0) => {
          this.status({fill:'green',shape:'dot',text:RED._('smartmesh.status.connected', {n:n})});
        });
        ['disconnected', 'error'].forEach(ev => {
          this.on(ev, () => {
            this.status({fill:'red',shape:'ring',text:`smartmesh.status.${ev}`});
          });
        });
        this.on('close', () => {
          if (this.smartMeshManagerNode) {
            this.smartMeshManagerNode.operations.remove(this);
          }
        });
        this.smartMeshManagerNode.operations.register(this);
      }
    }
  }
  RED.nodes.registerType('SmartMesh in', SmartMeshInNode);

  class SmartMeshOutNode {
    constructor(n) {
      RED.nodes.createNode(this, n);
      this.name = n.name;
      this.smartMeshManagerNodeId = n.smartMeshManager;
      this.smartMeshManagerNode = RED.nodes.getNode(this.smartMeshManagerNodeId);
      if (this.smartMeshManagerNode) {
        this.on('connected', (n=0) => {
          this.status({fill:'green',shape:'dot',text:RED._('smartmesh.status.connected', {n:n})});
        });
        ['disconnected', 'error'].forEach(ev => {
          this.on(ev, () => {
            this.status({fill:'red',shape:'ring',text:`smartmesh.status.${ev}`});
          });
        });
        this.on('input', (msg) => {
          let obj = msg.payload || {};
          try {
            if (typeof(obj) === 'string') {
              obj = JSON.parse(msg.payload);
            }
            this.smartMeshManagerNode.operations.send(obj);
          } catch (_) {
          }
        });
        this.on('close', () => {
          if (this.smartMeshManagerNode) {
            this.smartMeshManagerNode.operations.remove(this);
          }
        });
        this.smartMeshManagerNode.operations.register(this);
      }
    }
  }
  RED.nodes.registerType('SmartMesh out', SmartMeshOutNode);

  RED.httpAdmin.get('/smartmeshports', RED.auth.needsPermission('serial.read'), function(req,res) {
    let list = [];
    fs.stat('/dev/DC2274A-A.API', (err) => {
      if (!err) {
        list.push({
          comName: '/dev/DC2274A-A.API'
        });
      }
      serialport.list(function (_, ports) {
        res.json(list.concat(ports));
      });
    });
  });

  RED.httpAdmin.get('/smartmesh/:serialport/motes', RED.auth.needsPermission('serial.read'), function(req,res) {
    let serialport = req.params.serialport;
    if (!smartMeshClients[serialport]) {
      return res.sendStatus(404);
    }
    res.json(smartMeshClients[serialport].getActiveMotes());
  });
}
