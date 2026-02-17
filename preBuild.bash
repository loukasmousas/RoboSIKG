#!/bin/bash
# This file contains bash commands that will be executed at the beginning of the container build process,
# before any system packages or programming language specific package have been installed.
#
# Note: This file may be removed if you don't need to use it
#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  ffmpeg \
  libgl1 \
  libglib2.0-0 \
  ca-certificates \
  curl \
  git \
  build-essential \
  python3-dev \
  python3-venv

rm -rf /var/lib/apt/lists/*
