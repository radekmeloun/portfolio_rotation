#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/venv"
REPORT_DIR="$PROJECT_DIR/reports/tests"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Virtualenv not found at $VENV_DIR. Run ./scripts/bootstrap.sh first." >&2
  exit 2
fi

mkdir -p "$REPORT_DIR"

TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
RUN_LOG="$REPORT_DIR/pytest_${TIMESTAMP}.log"
RUN_XML="$REPORT_DIR/pytest_${TIMESTAMP}.junit.xml"
LATEST_LOG="$REPORT_DIR/latest.log"
LATEST_XML="$REPORT_DIR/latest.junit.xml"

cd "$PROJECT_DIR"

echo "Running tests and writing report files..."
echo "  Log: $RUN_LOG"
echo "  JUnit XML: $RUN_XML"

set +e
"$VENV_DIR/bin/python" -m pytest tests -q --tb=short --junitxml "$RUN_XML" 2>&1 | tee "$RUN_LOG"
TEST_EXIT="${PIPESTATUS[0]}"
set -e

cp "$RUN_LOG" "$LATEST_LOG"
cp "$RUN_XML" "$LATEST_XML"

echo ""
echo "Latest reports updated:"
echo "  $LATEST_LOG"
echo "  $LATEST_XML"

exit "$TEST_EXIT"
