#!/bin/bash
# Script to run the editor with visible output

echo "Stopping any existing Flask processes..."
pkill -9 -f "python.*edit_puzzles" 2>/dev/null
sleep 1

echo "Starting Flask editor on http://127.0.0.1:5001/editor"
echo "Press Ctrl+C to stop"
echo ""
python3 edit_puzzles.py

