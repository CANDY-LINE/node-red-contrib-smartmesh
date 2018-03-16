#!/usr/bin/env bash

PYTHON2=python

function log {
  logger -t node-red-node-contrib-smartmesh $1
  echo [node-red-node-contrib-smartmesh] $1
}

function uninstall_smartmeshsdk {
  INSTALLED_FILES=./deps/smartmeshsdk/installed_files.txt
  if [ -f "${INSTALLED_FILES}" ]; then
    cat "${INSTALLED_FILES}" | xargs rm -rf
    rm -f "${INSTALLED_FILES}"
    log "SmartMesh SDK has been removed"
  else
    log "SmartMesh SDK is already uninstalled"
  fi
}

# main
uninstall_smartmeshsdk
