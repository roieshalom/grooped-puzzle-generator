#!/bin/bash
# Quick test script - run on server to check if everything is working

echo "=== Testing Grooped Editor Deployment ==="
echo ""

echo "1. Checking if Flask service is running..."
if systemctl is-active --quiet editor.service; then
    echo "   ✓ Service is running"
else
    echo "   ✗ Service is NOT running"
    echo "   Run: sudo systemctl status editor.service"
fi
echo ""

echo "2. Checking if Flask is listening on port 5001..."
if curl -s http://127.0.0.1:5001/editor > /dev/null; then
    echo "   ✓ Flask app is responding"
else
    echo "   ✗ Flask app is NOT responding"
    echo "   Check: curl http://127.0.0.1:5001/editor"
fi
echo ""

echo "3. Checking nginx config for /editor location..."
if grep -q "location /editor" /etc/nginx/sites-available/* 2>/dev/null || grep -q "location /editor" /etc/nginx/nginx.conf 2>/dev/null; then
    echo "   ✓ Nginx config found"
else
    echo "   ✗ Nginx config for /editor NOT found"
    echo "   Add location block from nginx-editor.conf"
fi
echo ""

echo "4. Testing nginx..."
if sudo nginx -t 2>&1 | grep -q "successful"; then
    echo "   ✓ Nginx config is valid"
else
    echo "   ✗ Nginx config has errors"
    echo "   Run: sudo nginx -t"
fi
echo ""

echo "5. Checking if nginx can reach Flask..."
if curl -s -H "Host: grooped.de" http://localhost/editor > /dev/null; then
    echo "   ✓ Nginx can proxy to Flask"
else
    echo "   ✗ Nginx cannot reach Flask"
fi
echo ""

echo "=== Test Complete ==="
echo ""
echo "If everything passes, visit: https://grooped.de/editor"

