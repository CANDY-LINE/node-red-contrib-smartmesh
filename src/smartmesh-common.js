/**
 * @license
 * Copyright (c) 2018 CANDY LINE INC.
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
import cproc from 'child_process';
import fs from 'fs';
import path from 'path';
import { EventEmitter } from 'events';

const DEPS_PYTHON_PATH = path.resolve(path.join(__dirname, '..', 'deps', 'python'));
const PYTHON_EXEC_NAME_PATH = path.join(DEPS_PYTHON_PATH, 'python_exec_name');
const PYTHON_EXEC = (fs.existsSync(PYTHON_EXEC_NAME_PATH) ? fs.readdirSync(PYTHON_EXEC_NAME_PATH) : 'python');

export class SmartMeshClientProxy {
  constructor(opts={}) {
    this.serialport = opts.serialport;
    this.log = opts.log ? opts.log.bind(opts) : console.log;
    this.trace = opts.trace ? opts.trace.bind(opts) : console.log;
    this.debug = opts.debug ? opts.debug.bind(opts) : console.log;
    this.error = opts.error ? opts.error.bind(opts) : console.error;
    this.redirectSmartMeshManagerLog = opts.redirectSmartMeshManagerLog;
    if (opts instanceof EventEmitter) {
      this.bus = opts;
    } else {
      this.bus = opts.bus || new EventEmitter();
    }
    this.motes = {};
  }

  isConnected() {
    return !!this.cproc;
  }

  shutdown() {
    let isConnected = this.isConnected();
    return new Promise((resolve) => {
      if (isConnected) {
        this.cproc.kill('SIGKILL');
        this.bus.once('disconnected', () => {
            return resolve(true);
        });
      } else {
        return resolve();
      }
    });
  }

  send(message) {
    if (!this.isConnected()) {
      return Promise.reject('oapclient_proxy.py is disconnected');
    }
    if (message) {
      return new Promise((resolve) => {
        let messageJson = JSON.stringify(message);
        this.trace(`<stdin> [Output Message] message => ${messageJson}`);
        this.cproc.stdin.write(messageJson + '\n');
        return resolve();
      });
    } else {
      return Promise.resolve();
    }
  }

  fireMoteConnected() {
    this.bus.emit('connected', this.getActiveMoteCount());
  }

  processEvent(message) {
    if (message.mac && message.mac !== 'N/A' && !this.motes[message.mac]) {
      this.motes[message.mac] = {
        mac: message.mac,
      };
      if (message.event !== 'notification') {
        this.motes[message.mac].joinedAt = Date.now();
        this.motes[message.mac].active = true;
        this.fireMoteConnected();
        return;
      }
    }
    switch (message.type) {
      case 'eventMoteJoin':
        if (this.motes[message.mac]) {
          this.motes[message.mac].joinedAt = Date.now();
          this.motes[message.mac].active = true;
        }
        break;
      case 'eventMoteLost':
        if (this.motes[message.mac]) {
          this.motes[message.mac].active = false;
          this.motes[message.mac].lostAt = Date.now();
        }
        break;
    }
    this.fireMoteConnected();
  }

  getActiveMoteCount() {
    return Object.values(this.motes).filter(mote => mote.active).length;
  }

  getMoteCount() {
    return Object.keys(this.motes).length;
  }

  start() {
    // This function call may throw an exception on error
    this.cproc = cproc.spawn(`${PYTHON_EXEC}`,
      [`${DEPS_PYTHON_PATH}/oapclient_proxy.py`, this.serialport],
      {
        cwd: process.cwd(),
        env: process.env,
        stdio: ['pipe', 'pipe', this.redirectSmartMeshManagerLog ? process.stderr : 'ignore']
      }
    );
    this.fireMoteConnected();
    this.cproc.on('exit', (code) => {
      let message = '';
      switch (code) {
        case 2:
          message = 'I/O Error';
          break;
        case 4:
          message = 'Installation Error. PySerial seems to be missing.';
          this.bus.emit('error-event', {
            event: 'error',
            message: message
          });
          break;
        case 16:
          message = 'Disconnected by a remote mote';
          break;
      }
      this.log(`Process Exit: pid => ${this.cproc.pid}, code => ${code}: ${message}`);
      this.cproc = null;
      if (code && code !== 16) {
        this.bus.emit('error');
      } else {
        this.bus.emit('disconnected');
      }
    });
    this.cproc.stdout.on('data', (data) => {
      let lines = data.toString().split(/[\r\n]+/).filter((line) => line.trim());
      this.trace(`<stdout> [Input Message] ${lines.length} lines, => ${lines}`);
      let procs = lines.map((line) => {
        try {
          let message = JSON.parse(line);
          if (message.event === 'error') {
            this.bus.emit('error-event', message);
          } else {
            this.bus.emit('event', message);
            this.processEvent(message);
          }
        } catch (_) {
          return;
        }
      });
      Promise.all(procs);
    });
  }
}
