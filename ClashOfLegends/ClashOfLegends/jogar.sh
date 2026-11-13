#!/bin/sh
cd "$(dirname "$0")"
python3 -m pip install --user pygame-ce
python3 clash_of_legends.py
