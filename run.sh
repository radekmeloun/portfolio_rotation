#!/bin/bash
# Global Regime Rotator - Run Script
# This script sets up the virtual environment, installs dependencies, and runs the app

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔄 Global Regime Rotator - Setup & Run"
echo "======================================="

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip -q

# Install requirements
echo "📥 Installing requirements..."
pip install -r requirements.txt -q

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 Starting Streamlit app..."
echo "   Open http://localhost:8501 in your browser"
echo ""

# Run streamlit
streamlit run app.py
