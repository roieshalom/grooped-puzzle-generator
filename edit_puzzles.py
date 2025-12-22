#!/usr/bin/env python3
"""Simple Flask app to edit puzzles_week.json with a JSON editor in-browser.

Run with:
    pip install -r requirements.txt
    python edit_puzzles.py

Open http://127.0.0.1:5000
"""

from flask import Flask, render_template, jsonify, request, abort
import json
import os
import shutil
from datetime import datetime

APP_DIR = os.path.dirname(__file__)
JSON_PATH = os.path.join(APP_DIR, 'puzzles_week.json')

app = Flask(__name__)


def _read_json():
    with open(JSON_PATH, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def _write_json(obj, make_backup=False):
    """Write JSON atomically. By default do NOT create backups unless explicitly requested.

    If make_backup is True and the original file exists, create a timestamped backup
    before replacing the file. Writes are done to a temporary file and renamed into
    place using os.replace() for atomicity.
    """
    bak_path = None
    # create a backup of the existing file only if requested and the file exists
    if make_backup and os.path.exists(JSON_PATH):
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        bak_path = JSON_PATH + f'.bak.{ts}'
        shutil.copy2(JSON_PATH, bak_path)

    tmp_path = JSON_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())

    # atomic replace
    os.replace(tmp_path, JSON_PATH)
    return bak_path


@app.route('/')
def index():
    return render_template('editor.html')


@app.route('/api/puzzle', methods=['GET'])
def get_puzzle():
    try:
        data = _read_json()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify(data)


@app.route('/api/puzzle', methods=['POST'])
def save_puzzle():
    # Expecting JSON body
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'error': 'Invalid or missing JSON body'}), 400
    # ensure serializable
    try:
        json.dumps(data)
    except Exception as e:
        return jsonify({'error': f'JSON serialization failed: {e}'}), 400

    # support ?backup=0 or ?backup=false to skip creating a backup
    # Default is '0' so backups are opt-in and will not be created unless requested
    backup_param = request.args.get('backup', '0').lower()
    make_backup = not (backup_param in ('0', 'false', 'no', 'off'))

    try:
        bak = _write_json(data, make_backup=make_backup)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    resp = {'ok': True}
    if bak:
        resp['backup'] = os.path.basename(bak)
    else:
        resp['backup'] = None
    return jsonify(resp)


if __name__ == '__main__':
    # Use 127.0.0.1 only to keep it local
    app.run(host='127.0.0.1', port=5000, debug=False)
