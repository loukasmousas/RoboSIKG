#!/bin/bash
# This file contains bash commands that will be executed at the end of the container build process,
# after all system packages and programming language specific package have been installed.
#
# Note: This file may be removed if you don't need to use it
#!/usr/bin/env bash
set -euo pipefail

# Use python3 explicitly (Workbench images usually default to 3.10)
PY=python3
PIP="python3 -m pip"

$PIP install --upgrade pip wheel setuptools

# IMPORTANT:
# 1) FAISS wheels currently expect NumPy 1.x ABI -> pin NumPy <2
# 2) Ensure PyTorch comes from the cu128 wheel index (not cached / default PyPI)
# 3) Avoid --user in containers (installs go to site-packages cleanly)

# Clean out conflicting installs first
$PIP uninstall -y torch torchvision torchaudio numpy || true

# Clear pip cache so it won't reuse an old cu126 wheel
$PIP cache purge || true

# Install NumPy 1.x first (FAISS compatibility)
$PIP install "numpy==1.26.4"

# Install PyTorch + TorchVision from the cu128 index
$PIP install \
  --index-url https://download.pytorch.org/whl/cu128 \
  torch==2.7.1 torchvision==0.22.1

# Install the rest (FAISS after NumPy pin)
$PIP install \
  opencv-python-headless==4.10.0.84 \
  rdflib==7.0.0 \
  faiss-cpu==1.8.0 \
  PyYAML==6.0.2 \
  pydantic==2.9.2 \
  httpx==0.27.2 \
  rich==13.7.1

# Sanity checks (non-fatal printing helps debug fast)
$PY - <<'PY'
import sys
import torch
print("python:", sys.version)
print("torch:", torch.__version__)
print("torch compiled cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
PY

$PY - <<'PY'
import numpy as np
import faiss
x = np.random.rand(1000, 128).astype("float32")
idx = faiss.IndexFlatL2(128)
idx.add(x)
print("numpy:", np.__version__)
print("faiss:", faiss.__version__)
print("faiss ntotal:", idx.ntotal)
PY
