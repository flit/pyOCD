#!/bin/bash

# Get path to the scripts dir, under the assumption this script is in the scripts dir.
SCRIPTS_DIR=$(dirname $0)
REPO_ROOT=$SCRIPTS_DIR/..

# Change to the repo root before building.
cd $REPO_ROOT

# For a final release we'd use -F instead of -D... once it works.
pyinstaller -D -n pyocd --additional-hooks-dir=$SCRIPTS_DIR/hooks $SCRIPTS_DIR/pyocd.spec

