#!/usr/bin/env python3
"""Simple Flask app to edit puzzles_week.json with a JSON editor in-browser.

Run with:
    pip install -r requirements.txt
    python edit_puzzles.py

Open http://127.0.0.1:5000
"""

from flask import Flask, render_template, jsonify, request, abort, make_response
import json
import os
import shutil
from datetime import datetime
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

APP_DIR = os.path.dirname(__file__)
JSON_PATH = os.path.join(APP_DIR, 'puzzles_week.json')

# Add current directory to path for imports
sys.path.insert(0, APP_DIR)

try:
    from puzzle_validator import validate_puzzle, load_published_puzzles
    from puzzle_manager import get_next_id, get_next_date
except ImportError:
    # Fallback if modules not available
    def validate_puzzle(puzzle, published=None):
        return True, []
    def load_published_puzzles(path=None):
        return []
    def get_next_id(puzzles=None):
        return "1"
    def get_next_date(puzzles=None, start_date=None):
        return datetime.now().strftime("%d.%m.%Y")

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
    response = make_response(render_template('editor.html'))
    # Disable caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/api/puzzle', methods=['GET'])
def get_puzzle():
    try:
        data = _read_json()
        # Filter out published puzzles (they're in the other repo)
        data = [p for p in data if p.get('status') != 'published']
        # Add validation info with duplicate word detection
        published = load_published_puzzles()
        published_words = set()
        for p in published:
            for cat in p.get('categories', []):
                for word in cat.get('words', []):
                    published_words.add(word.upper().strip())
        
        for puzzle in data:
            is_valid, errors = validate_puzzle(puzzle, published)
            # Find duplicate words for highlighting
            duplicate_words = set()
            puzzle_words = []
            for cat in puzzle.get('categories', []):
                for word in cat.get('words', []):
                    word_upper = word.upper().strip()
                    if word_upper in published_words or word_upper in puzzle_words:
                        duplicate_words.add(word_upper)
                    puzzle_words.append(word_upper)
            
            puzzle['_validation'] = {
                'valid': is_valid, 
                'errors': errors,
                'duplicate_words': list(duplicate_words)
            }
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify(data)


@app.route('/api/puzzle', methods=['POST'])
def save_puzzle():
    # Expecting JSON body
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'error': 'Invalid or missing JSON body'}), 400
    
    # Filter out published puzzles
    data = [p for p in data if p.get('status') != 'published']
    
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


@app.route('/api/regenerate-category', methods=['GET'])
def regenerate_category():
    """Regenerate a single category."""
    try:
        # Ensure .env is loaded before importing - try multiple times
        load_dotenv()
        # Also try explicit path
        env_path = os.path.join(APP_DIR, '.env')
        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path, override=True)
        
        from regenerate_single_category import generate_single_category
        
        difficulty = request.args.get('difficulty', 'medium')
        difficulty_map = {
            "easy": "yellow",
            "medium": "green",
            "hard": "blue",
        }
        
        # Get existing categories from current puzzle to avoid duplicates
        puzzle_index = request.args.get('puzzle_index', type=int)
        existing_categories = []
        if puzzle_index is not None:
            try:
                data = _read_json()
                data = [p for p in data if p.get('status') != 'published']
                if 0 <= puzzle_index < len(data):
                    existing_categories = data[puzzle_index].get('categories', [])
            except:
                pass  # If we can't get existing, just continue
        
        # Generate single category
        raw = generate_single_category(difficulty, existing_categories)
        
        diff = raw.get("difficulty", difficulty)
        color = difficulty_map.get(diff, "green")
        words = raw.get("words", [])
        words_upper = [w.upper() for w in words] if words else []
        
        return jsonify({
            "name": raw.get("name", ""),
            "words": words_upper,
            "difficulty": color,
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/export', methods=['POST'])
def export_approved():
    """Export all puzzles and remove them from editor."""
    try:
        data = _read_json()
        # Filter out published puzzles
        data = [p for p in data if p.get('status') != 'published']
        
        if not data:
            return jsonify({'error': 'No puzzles to export'}), 400
        
        # Export all puzzles to file
        export_path = os.path.join(APP_DIR, 'puzzles_approved.json')
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Remove all from editor (they're now exported)
        _write_json([])
        
        return jsonify({
            'ok': True,
            'exported': len(data),
            'export_file': 'puzzles_approved.json'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Use 127.0.0.1 only to keep it local
    # Enable debug to prevent template caching
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(host='127.0.0.1', port=5001, debug=True)
