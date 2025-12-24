#!/bin/bash
# Deployment script for grooped editor
# Run this on your server after SSH'ing in

set -e  # Exit on error

echo "=== Grooped Editor Deployment Script ==="
echo ""

# Get paths
echo "Step 1: Finding repository paths..."
PUZZLE_GEN_DIR=$(pwd)
if [ ! -f "edit_puzzles.py" ]; then
    echo "Error: Run this script from the grooped-puzzle-generator directory"
    exit 1
fi

# Find grooped repo
if [ -d "../grooped" ]; then
    GROOPED_DIR=$(readlink -f ../grooped)
elif [ -d "/var/www/grooped" ]; then
    GROOPED_DIR="/var/www/grooped"
elif [ -d "$HOME/grooped" ]; then
    GROOPED_DIR="$HOME/grooped"
else
    echo "Enter the full path to the grooped repository:"
    read GROOPED_DIR
fi

if [ ! -d "$GROOPED_DIR" ]; then
    echo "Error: grooped directory not found at $GROOPED_DIR"
    exit 1
fi

echo "Found grooped-puzzle-generator at: $PUZZLE_GEN_DIR"
echo "Found grooped at: $GROOPED_DIR"
echo ""

# Install dependencies
echo "Step 2: Installing dependencies..."
pip3 install -r requirements.txt --user
echo ""

# Check .env file
echo "Step 3: Checking .env file..."
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Creating template..."
    cat > .env << EOF
OPENAI_API_KEY=your_key_here
AUTO_GIT_COMMIT=true
GROOPED_REPO_DIR=$GROOPED_DIR
FLASK_HOST=127.0.0.1
FLASK_PORT=5001
FLASK_DEBUG=False
EOF
    echo "Created .env template. Please edit it with your API key."
    echo "Press Enter when done..."
    read
fi
echo ""

# Find Python path
PYTHON_PATH=$(which python3)
echo "Step 4: Python path: $PYTHON_PATH"
echo ""

# Create systemd service file
echo "Step 5: Creating systemd service file..."
SERVICE_FILE="/tmp/editor.service"
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Grooped Puzzle Editor Flask App
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=$PUZZLE_GEN_DIR
Environment="PATH=/usr/bin:/usr/local/bin"
Environment="FLASK_HOST=127.0.0.1"
Environment="FLASK_PORT=5001"
Environment="FLASK_DEBUG=False"
Environment="GROOPED_REPO_DIR=$GROOPED_DIR"
Environment="AUTO_GIT_COMMIT=true"
ExecStart=$PYTHON_PATH $PUZZLE_GEN_DIR/edit_puzzles.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Service file created at: $SERVICE_FILE"
echo ""
echo "To install the service, run:"
echo "  sudo cp $SERVICE_FILE /etc/systemd/system/editor.service"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable editor.service"
echo "  sudo systemctl start editor.service"
echo "  sudo systemctl status editor.service"
echo ""
echo "Then test with:"
echo "  curl http://127.0.0.1:5001/editor"
echo ""
echo "=== Next step: Configure nginx ==="
echo "Add the location block from nginx-editor.conf to your nginx config"
echo "Then run: sudo nginx -t && sudo systemctl reload nginx"

