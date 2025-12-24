# Deployment Guide for Grooped Editor

This guide explains how to deploy the puzzle editor to `grooped.de/editor`.

## Prerequisites

- A server with:
  - Python 3.7+
  - nginx (or another reverse proxy)
  - Git
  - Systemd (for service management)
- Access to the `grooped` repository
- SSH access to the server

## Step 1: Clone Repositories on Server

```bash
# Choose a location for your projects (e.g., /var/www or /home/user)
cd /var/www
git clone https://github.com/roieshalom/grooped.git
git clone https://github.com/roieshalom/grooped-puzzle-generator.git
```

## Step 2: Install Dependencies

```bash
cd grooped-puzzle-generator
pip3 install -r requirements.txt --user
# Or use a virtual environment:
# python3 -m venv venv
# source venv/bin/activate
# pip install -r requirements.txt
```

## Step 3: Set Up Environment Variables

Create a `.env` file in `grooped-puzzle-generator`:

```bash
cd grooped-puzzle-generator
nano .env
```

Add:
```
OPENAI_API_KEY=your_api_key_here
AUTO_GIT_COMMIT=true
GROOPED_REPO_DIR=/var/www/grooped
FLASK_HOST=127.0.0.1
FLASK_PORT=5001
FLASK_DEBUG=False
```

## Step 4: Set Up Git Authentication

The editor needs to push to the `grooped` repository. Set up authentication:

```bash
cd /var/www/grooped
# Option 1: Use SSH keys (recommended)
# Make sure your SSH key is added to GitHub

# Option 2: Use GitHub token
git remote set-url origin https://YOUR_TOKEN@github.com/roieshalom/grooped.git

# Test it works:
git pull
```

## Step 5: Configure Systemd Service

1. Copy the service file:
```bash
sudo cp editor.service /etc/systemd/system/
```

2. Edit the service file to match your paths:
```bash
sudo nano /etc/systemd/system/editor.service
```

Update these paths:
- `WorkingDirectory=/var/www/grooped-puzzle-generator`
- `ExecStart=/usr/bin/python3 /var/www/grooped-puzzle-generator/edit_puzzles.py`
- `Environment="GROOPED_REPO_DIR=/var/www/grooped"`

3. Reload systemd and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable editor.service
sudo systemctl start editor.service
sudo systemctl status editor.service
```

## Step 6: Configure Nginx

1. Add the editor location to your nginx config. The config snippet is in `nginx-editor.conf`.

2. Add it to your main nginx config (usually `/etc/nginx/sites-available/grooped.de`):

```bash
sudo nano /etc/nginx/sites-available/grooped.de
```

Add the location block from `nginx-editor.conf` inside your `server` block.

3. Test and reload nginx:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Step 7: Test

1. Check the service is running:
```bash
sudo systemctl status editor.service
```

2. Check it's listening:
```bash
curl http://127.0.0.1:5001/
```

3. Test from the web:
Visit `http://grooped.de/editor` in your browser.

## Troubleshooting

### Service won't start
- Check logs: `sudo journalctl -u editor.service -n 50`
- Verify Python path: `which python3`
- Check file permissions: `ls -la /var/www/grooped-puzzle-generator/edit_puzzles.py`

### 502 Bad Gateway
- Check if Flask is running: `curl http://127.0.0.1:5001/`
- Check nginx error log: `sudo tail -f /var/log/nginx/error.log`
- Verify firewall allows localhost connections

### Git push fails
- Check git config in grooped repo: `cd /var/www/grooped && git remote -v`
- Test git push manually: `cd /var/www/grooped && git push`
- Check SSH keys or token permissions

### Path errors
- Verify `GROOPED_REPO_DIR` is set correctly in the service file
- Check that `puzzles.json` exists: `ls -la /var/www/grooped/puzzles.json`

## Updating the Editor

After making changes:

```bash
cd /var/www/grooped-puzzle-generator
git pull
sudo systemctl restart editor.service
```

## Security Notes

- The Flask app only listens on `127.0.0.1` (localhost) for security
- Access is controlled through nginx
- Consider adding authentication in nginx if needed
- Keep your `.env` file secure and never commit it

