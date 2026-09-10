#!/bin/zsh
# Double-click me to start the brain.
cd "$(dirname "$0")"
BRAIN_BIND=tailnet python3 brain/tools/serve.py
