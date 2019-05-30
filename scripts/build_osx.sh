#!/bin/bash

# Intended to be run from within a Travis-CI osx instance.

# Install python.
brew install python

# Use Python 3.7
PY=python3

# Clean things up.
rm -rf dist

# Install pyocd requirements.
$PY -mpip install -r dev-requirements.txt capstone

# Build the pyocd executable.
$PY -mPyInstaller -F pyocd.spec

# Simple test that pyocd executable runs.
./dist/pyocd --help


