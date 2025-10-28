#!/bin/bash
echo "🔧 Setting up Telegram File Downloader..."

# Create necessary directories
mkdir -p downloads

# Install dependencies
pip install -r requirements.txt

echo "✅ Setup complete!"
echo "🤖 Starting bot..."
python main.py
