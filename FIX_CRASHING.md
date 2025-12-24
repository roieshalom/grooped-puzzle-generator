# Fix Crashing Machines

The machines are crashing. We need to check logs and set secrets:

## 1. Check Logs

In Fly.io dashboard:
- Go to your app → Monitoring → Logs
- Or run: `fly logs --app grooped-editor`

Look for Python errors like:
- Missing modules
- File not found errors
- Port binding errors

## 2. Set Required Secrets in Fly.io

The app needs these secrets (they're in fly.toml but might need to be secrets):

```bash
fly secrets set OPENAI_API_KEY=your_key_here --app grooped-editor
```

## 3. Most Likely Issues:

1. **Missing .env file** - Flask can't find OPENAI_API_KEY
2. **Grooped repo not cloned** - Can't find puzzles.json
3. **Python dependencies missing** - Check requirements.txt is correct
4. **Port binding issue** - Flask not listening on right port

## Quick Fix - Add Secrets:

```bash
fly secrets set OPENAI_API_KEY=your_actual_key --app grooped-editor
```

Then restart machines:
```bash
fly machine restart --app grooped-editor
```

