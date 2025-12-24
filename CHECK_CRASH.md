# App is Crashing - Need to Check Logs

The app builds successfully but crashes on startup. To see the actual error:

## Option 1: Fly.io Dashboard
1. Go to https://fly.io/apps/grooped-editor
2. Click "Monitoring" or "Logs"
3. Look for Python traceback/error messages

## Option 2: CLI (if you have fly command)
```bash
fly logs --app grooped-editor
```

## Common Crash Causes:
1. **Missing Python modules** - puzzle_validator.py or puzzle_manager.py not found
2. **Missing .env file** - but we set secrets, so this should be fine
3. **Import errors** - Python can't import required modules
4. **Port binding** - Flask not starting correctly
5. **Missing files** - templates/editor.html not found

The build shows everything copied correctly, so likely it's a runtime Python error.

Please check the logs in Fly.io dashboard and share the error message!

