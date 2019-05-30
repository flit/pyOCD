#!/bin/bash

# This build script is expected to be run in the manylinux1 docker image.

# Use Python 3.7
PY=/opt/python/cp37-cp37m/bin/python

pushd /io

# Clean things up.
rm -rf /io/dist

# Install requirements.
$PY -mpip install -r dev-requirements.txt capstone

# Build the pyocd executable.
$PY -mPyInstaller -F pyocd.spec

# Simple test that pyocd executable runs.
/io/dist/pyocd --help


