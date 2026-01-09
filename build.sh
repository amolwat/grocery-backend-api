#!/usr/bin/env bash
set -e

echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🌐 Installing Playwright Chromium..."
python -m playwright install chromium

echo "✅ Build finished"
