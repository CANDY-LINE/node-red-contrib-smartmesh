#!/usr/bin/env bash

SDK_VERSION=1.3.0.1
PYTHON2=python

function log {
  logger -t node-red-node-contrib-smartmesh $1
  echo [node-red-node-contrib-smartmesh] $1
}

function resolve_python2 {
  if ! which ${PYTHON2} > /dev/null 2>&1; then
    PYTHON2=python2
  elif ! ${PYTHON2} --version 2>&1 | grep 2.7 > /dev/null; then
    PYTHON2=python2
  fi
}

function test_connectivity {
  curl -s --head --fail -o /dev/null https://github.com 2>&1
  if [ "$?" != 0 ]; then
    log "[ERROR] Internet connection is required"
    exit 1
  fi
}

function assert_preconditions {
  resolve_python2
  [[ `${PYTHON2} --version 2>&1 | grep 2.7` ]] || (log "[ERROR] Python 2.7 is missing" && exit 1)
  [[ `which curl` ]] || (log "[ERROR] cURL is missing" && exit 1)
  [[ `which tar` ]] || (log "[ERROR] tar is missing" && exit 1)
}

function install_smartmeshsdk {
  DOWNLOAD=1
  if [ -f ./deps/smartmeshsdk/PKG-INFO ]; then
    if `grep ${SDK_VERSION} ./deps/smartmeshsdk/PKG-INFO > /dev/null`; then
      if [ -f ./deps/smartmeshsdk/installed_files.txt ]; then
        log "[INFO] SmartMesh SDK is alredy installed"
        exit 0
      else
        log "[INFO] SmartMesh SDK is alredy downloaded"
        DOWNLOAD=0
      fi
    else
      rm -fr ./deps/smartmeshsdk
    fi
  else
    mkdir deps
  fi
  cd deps
  if [ "${DOWNLOAD}" == "1" ]; then
    test_connectivity
    curl -sSL https://github.com/dustcloud/smartmeshsdk/archive/REL-${SDK_VERSION}.tar.gz | tar zx
    mv smartmeshsdk-REL-${SDK_VERSION} smartmeshsdk
    log "[INFO] SmartMesh SDK has been downloaded"
  fi
  cd smartmeshsdk
  echo `which ${PYTHON2}` > ./python_exec_name # Used by src/smartmesh-common.js
  ${PYTHON2} ./setup.py install --record ./installed_files.txt
}

# main
assert_preconditions
install_smartmeshsdk
