# Check Fly.io Logs

To see why machines are crashing, run:

```bash
fly logs --app grooped-editor
```

Or check in Fly.io dashboard:
- Go to your app
- Click "Monitoring" or "Logs"
- Look for Python/Flask errors

Common issues:
1. Missing .env file or environment variables
2. Flask app crashing on startup
3. Port mismatch
4. Missing dependencies

Once we see the logs, we can fix the specific error.

