node-red-contrib-smartmesh
===

A Node-RED node for SmartMesh® USB Manager.

# Prerequisites

1. Python 2.7 (Python 2.6/3.x are NOT supported)
1. PySerial 3.4+

# How to install

For Windows users, use Docker or other Linux box VM to start Node-RED in order to install this node.

## Node-RED users

Run the following commands:
```
sudo pip install pyserial
cd ~/.node-red
npm install node-red-contrib-smartmesh
```

Then restart Node-RED process.

When you have trouble with connecting your BLE devices, reset your HCI socket by the following command.

```
# STOP Node-RED first!!
```
And restart Node-RED.

## CANDY RED users

Run the following commands:
```
sudo pip install pyserial
cd $(npm -g root)/candy-red
sudo npm install --unsafe-perm node-red-contrib-smartmesh
```

Then restart `candy-red` service.

```
sudo systemctl restart candy-red
```

# Appendix

## How to build

```
# build
$ NODE_ENV=development npm run build
# package
$ NODE_ENV=development npm pack
```

### Shrinkwrap

```
$ rm -fr node_modules; \
  rm -f npm-shrinkwrap.json; \
  nodenv local 8.10.0; \
  npm install;npm run freeze
```

# Revision History

* 0.1.0
  - Initial Release (alpha)
  - `node-red` keyword is not yet added
