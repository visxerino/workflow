#!/bin/bash
# Convenience script for running the YouTube research pipeline

set -e

echo "YouTube Breakthrough Research Pipeline"
echo "======================================="
echo ""

# Check for API key
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please create .env from .env.example and add your YouTube API key."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
if [ ! -f "venv/.installed" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
    touch venv/.installed
fi

# Run the pipeline
echo ""
echo "Running full pipeline..."
echo ""

python main.py run_all

echo ""
echo "Pipeline complete! Check ./out for CSV exports."
