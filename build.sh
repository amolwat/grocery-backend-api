#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright browser
python -m playwright install chromium
