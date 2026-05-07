#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TODAY=$(date +%Y-%m-%d)
SUMMARY="$SCRIPT_DIR/summaries/$TODAY.md"

if [ -f "$SUMMARY" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Briefing für $TODAY bereits vorhanden – überspringe."
    exit 0
fi

if [ -d "venv" ]; then
    source venv/bin/activate
fi

python3 main.py
