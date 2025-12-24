# Quick Start: Deploy Editor to grooped.de/editor

## Step 1: Connect to Your Server

You need to SSH into the server that hosts `grooped.de`. If you don't know how, you'll need:
- The server's IP address or hostname
- Your username and password (or SSH key)

```bash
# Connect to server (replace with your actual server details)
ssh username@your-server-ip
# or
ssh username@grooped.de
```

## Step 2: Once on the Server, Run These Commands

**Quick Option: Use the deployment script**
```bash
cd grooped-puzzle-generator
chmod +x deploy.sh
./deploy.sh
```

**Or follow manual steps below:**

### A. Check if repos are cloned
```bash
# Check where you want to install (common locations: /var/www, /home/username)
ls -la /var/www
# or
ls -la ~
```

### B. Clone repositories (if not already done)
```bash
cd /var/www  # or wherever you keep your web projects
git clone https://github.com/roieshalom/grooped.git
git clone https://github.com/roieshalom/grooped-puzzle-generator.git
```

### C. Install dependencies
```bash
cd grooped-puzzle-generator
pip3 install -r requirements.txt --user
# or use venv (recommended):
# python3 -m venv venv
# source venv/bin/activate
# pip install -r requirements.txt
```

### D. Create .env file
```bash
nano .env
```

Add:
```
OPENAI_API_KEY=your_key_here
AUTO_GIT_COMMIT=true
GROOPED_REPO_DIR=/var/www/grooped
FLASK_HOST=127.0.0.1
FLASK_PORT=5001
FLASK_DEBUG=False
```

### E. Set up systemd service

1. Copy and edit the service file:
```bash
sudo cp /var/www/grooped-puzzle-generator/editor.service /etc/systemd/system/
sudo nano /etc/systemd/system/editor.service
```

2. Update these paths in the file (replace `/var/www` with your actual path):
   - `WorkingDirectory=/var/www/grooped-puzzle-generator`
   - `ExecStart=/usr/bin/python3 /var/www/grooped-puzzle-generator/edit_puzzles.py`
   - `Environment="GROOPED_REPO_DIR=/var/www/grooped"`

3. Start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable editor.service
sudo systemctl start editor.service
sudo systemctl status editor.service
```

### F. Configure nginx

1. Find your nginx config file:
```bash
sudo find /etc/nginx -name "*.conf" | grep -i grooped
# or check common location:
sudo nano /etc/nginx/sites-available/grooped.de
# or
sudo nano /etc/nginx/nginx.conf
```

2. Add this inside your `server` block for grooped.de:
```nginx
location /editor {
    proxy_pass http://127.0.0.1:5001/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}
```

3. Test and reload nginx:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### G. Test

```bash
# Test Flask app directly
curl http://127.0.0.1:5001/editor

# If that works, test through nginx
curl http://localhost/editor
```

Then visit `https://grooped.de/editor` in your browser!

## Troubleshooting

If something doesn't work, check:

1. **Service status**: `sudo systemctl status editor.service`
2. **Service logs**: `sudo journalctl -u editor.service -n 50`
3. **Nginx errors**: `sudo tail -f /var/log/nginx/error.log`
4. **Can Flask connect?**: `curl http://127.0.0.1:5001/editor`

See `TROUBLESHOOTING.md` for more detailed help.

