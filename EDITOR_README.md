# Local JSON Editor for puzzles_week.json ✅

This repository includes a tiny local Flask app to edit `puzzles_week.json` in your browser using `jsoneditor` (tree/code view).

Quick start:

1. Install dependencies (one-time):

    pip install -r requirements.txt

2. Run the editor:

    python edit_puzzles.py

3. Open in your browser:

    http://127.0.0.1:5000

Notes:
- Saves update `puzzles_week.json` in place. By default backups are **off** — uncheck or leave unchecked **Create backup on save** (the checkbox is unchecked by default) to keep this behavior; check it if you want a timestamped backup (`puzzles_week.json.bak.YYYYMMDD_HHMMSS`) created before each save.
- The server listens on `127.0.0.1` only (local machine only).
- If you want authentication or to restrict changes, tell me and I can add a simple token or password.
