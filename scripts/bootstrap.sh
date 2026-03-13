#!/bin/bash
# ============================================================================
# Global Regime Rotator - Bootstrap Script
# ============================================================================
# Sets up the development environment and optionally runs tests and app.
#
# Usage:
#   ./scripts/bootstrap.sh              # Full setup: venv, deps, tests, app
#   SKIP_TESTS=1 ./scripts/bootstrap.sh # Skip tests
#   SKIP_APP=1 ./scripts/bootstrap.sh   # Skip starting Streamlit
#   SKIP_TESTS=1 SKIP_APP=1 ./scripts/bootstrap.sh  # Just setup
#
# ============================================================================

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/venv"

echo "============================================"
echo "Global Regime Rotator - Bootstrap"
echo "============================================"
echo ""

# Change to project directory
cd "$PROJECT_DIR"

# Step 1: Create virtual environment if missing
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment exists"
fi

# Step 2: Activate venv
echo "🔌 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Step 3: Install/upgrade dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Dependencies installed"

# Step 4: Run tests (unless SKIP_TESTS=1)
if [ "${SKIP_TESTS:-0}" != "1" ]; then
    echo ""
    echo "🧪 Running tests..."
    python -m pytest tests/ -v --tb=short
    echo "✅ Tests passed"
else
    echo ""
    echo "⏭️ Skipping tests (SKIP_TESTS=1)"
fi

# Step 5: Start Streamlit app (unless SKIP_APP=1)
if [ "${SKIP_APP:-0}" != "1" ]; then
    echo ""
    echo "🚀 Starting Streamlit app..."
    echo "   Access at: http://localhost:8501"
    echo "   Press Ctrl+C to stop"
    echo ""
    streamlit run app.py
else
    echo ""
    echo "⏭️ Skipping app start (SKIP_APP=1)"
    echo ""
    echo "✅ Bootstrap complete! To start the app manually:"
    echo "   source venv/bin/activate"
    echo "   streamlit run app.py"
fi
