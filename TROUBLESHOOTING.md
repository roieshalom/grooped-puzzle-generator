# Troubleshooting: Editor not accessible at grooped.de/editor

## Quick Diagnostic Checklist

### 1. Is the Flask app running?

```bash
# Check if the service is running
sudo systemctl status editor.service

# Check if it's listening on port 5001
sudo netstat -tlnp | grep 5001
# Or
sudo ss -tlnp | grep 5001

# Check logs for errors
sudo journalctl -u editor.service -n 50 --no-pager
```

**If service is not running:**
```bash
# Try starting it
sudo systemctl start editor.service

# Check what's wrong
sudo journalctl -u editor.service -n 50
```

**Common issues:**
- Python path wrong: `which python3` vs what's in service file
- Paths wrong: Check `WorkingDirectory` and `ExecStart` in service file
- Permissions: Make sure files are readable
- Missing dependencies: Check if all Python packages are installed

### 2. Can you access it locally on the server?

```bash
# Test from the server itself
curl http://127.0.0.1:5001/
curl http://127.0.0.1:5001/editor
```

**If this fails:**
- The Flask app isn't running or has errors
- Check the service logs (see step 1)
- Try running manually: `python3 /path/to/grooped-puzzle-generator/edit_puzzles.py`

### 3. Is nginx configured correctly?

```bash
# Check if nginx config has the /editor location
sudo grep -A 20 "location /editor" /etc/nginx/sites-available/grooped.de
# Or wherever your main nginx config is

# Check nginx config for syntax errors
sudo nginx -t

# Check if nginx is running
sudo systemctl status nginx
```

**If nginx config is missing:**
- Add the location block from `nginx-editor.conf` to your nginx config
- Make sure it's inside the `server` block for grooped.de
- Reload nginx: `sudo systemctl reload nginx`

**If nginx config looks wrong:**
- Make sure `proxy_pass` points to `http://127.0.0.1:5001/` (note the trailing slash)
- Make sure it's inside the correct `server` block

### 4. Check nginx error logs

```bash
# Check for proxy errors
sudo tail -f /var/log/nginx/error.log

# While tailing, try accessing grooped.de/editor in browser
# Look for connection refused or other errors
```

**Common nginx errors:**
- `502 Bad Gateway` - Flask app not running or not listening on 5001
- `Connection refused` - Flask app not running
- `Permission denied` - SELinux or file permission issues

### 5. Verify paths and permissions

```bash
# Check if the service file paths are correct
cat /etc/systemd/system/editor.service

# Verify the directories exist
ls -la /path/to/grooped-puzzle-generator/edit_puzzles.py
ls -la /path/to/grooped/puzzles.json

# Check file permissions
# The service runs as www-data (or another user)
# Make sure that user can read/write the files
sudo -u www-data test -r /path/to/grooped-puzzle-generator/edit_puzzles.py
sudo -u www-data test -r /path/to/grooped/puzzles.json
sudo -u www-data test -w /path/to/grooped/puzzles.json
```

### 6. Test manual startup

```bash
# Stop the service first
sudo systemctl stop editor.service

# Run manually to see errors
cd /path/to/grooped-puzzle-generator
export FLASK_HOST=127.0.0.1
export FLASK_PORT=5001
export GROOPED_REPO_DIR=/path/to/grooped
python3 edit_puzzles.py
```

**If manual startup works:**
- The issue is with the service configuration
- Check environment variables in service file
- Check the user/group permissions

**If manual startup fails:**
- Look at the error message
- Check if all dependencies are installed
- Check if paths are correct

### 7. Common fixes

**Fix 1: Update service file paths**
```bash
sudo nano /etc/systemd/system/editor.service
# Update all /path/to/ references to actual paths
sudo systemctl daemon-reload
sudo systemctl restart editor.service
```

**Fix 2: Fix nginx proxy_pass**
The proxy_pass should have a trailing slash:
```nginx
proxy_pass http://127.0.0.1:5001/;  # ← trailing slash
```

**Fix 3: Reload nginx after changes**
```bash
sudo nginx -t  # Test config first
sudo systemctl reload nginx
```

**Fix 4: Check firewall**
```bash
# The app should only listen on localhost (127.0.0.1)
# So firewall shouldn't matter, but check anyway
sudo ufw status
```

### 8. Quick test sequence

```bash
# 1. Test Flask app directly
curl http://127.0.0.1:5001/editor
# Should return HTML

# 2. Test through nginx (from server)
curl -H "Host: grooped.de" http://127.0.0.1/editor
# Should return HTML

# 3. Check what nginx sees
sudo tail -f /var/log/nginx/access.log
# Then visit grooped.de/editor in browser
# Check if request appears in log
```

## Still not working?

Share the output of:
1. `sudo systemctl status editor.service`
2. `sudo journalctl -u editor.service -n 50`
3. `curl http://127.0.0.1:5001/editor` (from server)
4. Relevant nginx error log entries
5. Your nginx config (the server block for grooped.de)

