#!/usr/bin/env python3
"""Simple Flask app to edit puzzles_week.json with a JSON editor in-browser.

Run with:
    pip install -r requirements.txt
    python edit_puzzles.py

Open [http://127.0.0.1:5000](http://127.0.0.1:5000)
"""

from flask import Flask, render_template, jsonify, request, abort, make_response
import json
import os
import shutil
from datetime import datetime, timedelta
import sys
import subprocess
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

APP_DIR = os.path.dirname(os.path.abspath(__file__))
# Path to puzzles.json in the grooped repository
# Can be overridden with GROOPED_REPO_DIR environment variable
grooped_repo_dir = os.getenv('GROOPED_REPO_DIR')
if grooped_repo_dir and os.path.exists(grooped_repo_dir):
    GROOPED_REPO_DIR = grooped_repo_dir
else:
    # Fallback to relative path if env var not set or path doesn't exist
    parent_dir = os.path.dirname(APP_DIR)
    GROOPED_REPO_DIR = os.path.join(parent_dir, 'grooped')
JSON_PATH = os.path.join(GROOPED_REPO_DIR, 'puzzles.json')

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

# banned categories helpers
from banned_categories import (
    load_banned_categories,
    add_banned_category,
    normalize_category,
)

app = Flask(__name__, static_folder='static')


def _read_json():
    """Read all puzzles from puzzles.json, filtering out published ones for editor."""
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as fh:
            data = json.load(fh)

        # Handle both formats: array directly or object with "puzzles" key
        if isinstance(data, list):
            all_puzzles = data
        elif isinstance(data, dict) and 'puzzles' in data:
            all_puzzles = data['puzzles']
            if not isinstance(all_puzzles, list):
                all_puzzles = []
        else:
            all_puzzles = []

        # Filter out non-dict items and published puzzles - editor only shows draft/reviewed/approved
        return [p for p in all_puzzles if isinstance(p, dict) and p.get('status') != 'published']
    except FileNotFoundError:
        return []


def _save_puzzles_to_json(updated_puzzles, make_backup=False):
    """Save puzzles to puzzles.json, updating existing or appending new ones.

    - If puzzle has an existing ID, update it in place
    - If puzzle is new (no ID or ID doesn't exist), append with auto-assigned ID/date
    - Preserves all existing puzzles including published ones
    """
    bak_path = None
    use_object_format = False

    # Load all existing puzzles (including published)
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as fh:
            data = json.load(fh)

        # Handle both formats: array directly or object with "puzzles" key
        if isinstance(data, list):
            all_existing = data
            use_object_format = False
        elif isinstance(data, dict) and 'puzzles' in data:
            all_existing = data['puzzles']
            if not isinstance(all_existing, list):
                all_existing = []
            use_object_format = True
        else:
            all_existing = []
            use_object_format = False
    except FileNotFoundError:
        all_existing = []
        use_object_format = False

    # create a backup if requested
    if make_backup and os.path.exists(JSON_PATH):
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        bak_path = JSON_PATH + f'.bak.{ts}'
        shutil.copy2(JSON_PATH, bak_path)

    # Filter out any non-dict items from all_existing (defensive)
    all_existing = [p for p in all_existing if isinstance(p, dict)]

    # Create index of existing puzzles by ID
    existing_by_id = {str(p.get('id')): i for i, p in enumerate(all_existing) if isinstance(p, dict) and p.get('id')}

    # Calculate starting IDs and dates for new puzzles
    from puzzle_manager import get_next_id, get_next_date
    next_id = get_next_id(all_existing)
    next_date = get_next_date(all_existing)

    current_id = next_id
    current_date_obj = datetime.strptime(next_date, "%d.%m.%Y") if next_date else datetime.now()

    puzzles_to_append = []

    for puzzle in updated_puzzles:
        # Skip if not a dict
        if not isinstance(puzzle, dict):
            continue
        puzzle_id = str(puzzle.get('id', ''))

        # If puzzle has an existing ID, update it
        if puzzle_id and puzzle_id in existing_by_id:
            idx = existing_by_id[puzzle_id]
            # Update existing puzzle (preserve ID and date if they exist)
            if not puzzle.get('date') and all_existing[idx].get('date'):
                puzzle['date'] = all_existing[idx]['date']
            all_existing[idx] = puzzle
        else:
            # New puzzle - assign ID and date if missing
            if not puzzle.get('id'):
                puzzle['id'] = current_id
                try:
                    current_id = str(int(current_id) + 1)
                except (ValueError, TypeError):
                    current_id = "1"

            if not puzzle.get('date'):
                puzzle['date'] = current_date_obj.strftime("%d.%m.%Y")
                current_date_obj = current_date_obj + timedelta(days=1)

            puzzles_to_append.append(puzzle)

    # Append new puzzles to existing ones
    all_existing.extend(puzzles_to_append)

    # Write back all puzzles in same format as original
    tmp_path = JSON_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as fh:
        if use_object_format:
            json.dump({'puzzles': all_existing}, fh, indent=2, ensure_ascii=False)
        else:
            json.dump(all_existing, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())

    # atomic replace
    os.replace(tmp_path, JSON_PATH)
    return bak_path


def _commit_and_push(message="Update puzzles", additional_files=None, git_repo_dir=None):
    """Commit and push changes to git repository.

    Args:
        message: Commit message
        additional_files: List of additional file paths to include (absolute paths)
        git_repo_dir: Directory of git repository (defaults to grooped repo)

    Returns (success: bool, output: str, error: str)
    """
    if git_repo_dir is None:
        git_repo_dir = GROOPED_REPO_DIR

    try:
        # Check if we're in a git repository
        result = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            cwd=git_repo_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False, "", "Not a git repository"

        # Add the JSON file (relative to git repo)
        json_file_rel = os.path.relpath(JSON_PATH, git_repo_dir)
        files_to_add = [json_file_rel]
        if additional_files:
            for f in additional_files:
                rel_path = os.path.relpath(f, git_repo_dir)
                files_to_add.append(rel_path)

        result = subprocess.run(
            ['git', 'add'] + files_to_add,
            cwd=git_repo_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False, result.stdout, result.stderr

        # Check if there are changes to commit
        result = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            cwd=git_repo_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # No changes to commit
            return True, "No changes to commit", ""

        # Commit
        result = subprocess.run(
            ['git', 'commit', '-m', message],
            cwd=git_repo_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False, result.stdout, result.stderr

        # Push to remote
        result = subprocess.run(
            ['git', 'push'],
            cwd=git_repo_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return False, result.stdout, result.stderr

        return True, "Committed and pushed successfully", ""

    except subprocess.TimeoutExpired:
        return False, "", "Git operation timed out"
    except Exception as e:
        return False, "", str(e)


@app.route('/')
@app.route('/editor')
def index():
    # Force template reload by checking file modification time
    template_path = os.path.join(app.template_folder, 'editor.html')
    if os.path.exists(template_path):
        # Touch the template to ensure Flask detects changes
        # This helps with template auto-reload
        pass

    response = make_response(render_template('editor.html'))
    # Disable caching aggressively
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Last-Modified'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
    return response


@app.errorhandler(404)
def catch_all(error):
    """Catch-all route to ensure Flask handles all requests."""
    # If it's not an API route, serve the editor
    if not request.path.startswith('/api/'):
        return index()
    return jsonify({'error': 'Not found'}), 404


# ---- banned categories API ----

@app.route('/api/banned-categories', methods=['GET'])
def get_banned_categories():
    """Return global banned categories list."""
    try:
        categories = load_banned_categories()
        return jsonify(categories)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/banned-categories', methods=['POST'])
def post_banned_category():
    """Add a category name to the global banned list."""
    data = request.get_json(silent=True) or {}
    name = data.get('category', '')
    if not name or not isinstance(name, str):
        return jsonify({'error': 'Missing or invalid category'}), 400
    try:
        add_banned_category(name)
        return jsonify({'ok': True, 'category': normalize_category(name)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/puzzle', methods=['GET'])
def get_puzzle():
    """Return only the first non-published puzzle (one at a time)."""
    try:
        # Read puzzles (already filters out published)
        data = _read_json()

        # Return only the first puzzle
        if not data:
            return jsonify([])

        puzzle = data[0] if data else None
        if not puzzle:
            return jsonify([])

        # Load published puzzles for validation (from same file, filter by status)
        try:
            with open(JSON_PATH, 'r', encoding='utf-8') as fh:
                file_data = json.load(fh)

            # Handle both formats: array directly or object with "puzzles" key
            if isinstance(file_data, list):
                all_puzzles = file_data
            elif isinstance(file_data, dict) and 'puzzles' in file_data:
                all_puzzles = file_data['puzzles']
                if not isinstance(all_puzzles, list):
                    all_puzzles = []
            else:
                all_puzzles = []

            published = [p for p in all_puzzles if isinstance(p, dict) and p.get('status') == 'published']
        except FileNotFoundError:
            published = []

        published_words = set()
        for p in published:
            if isinstance(p, dict):
                for cat in p.get('categories', []):
                    if isinstance(cat, dict):
                        for word in cat.get('words', []):
                            if isinstance(word, str):
                                published_words.add(word.upper().strip())

        # Validate the puzzle
        if isinstance(puzzle, dict):
            is_valid, errors = validate_puzzle(puzzle, published)
            # Find duplicate words for highlighting
            duplicate_words = set()
            puzzle_words = []
            for cat in puzzle.get('categories', []):
                if isinstance(cat, dict):
                    for word in cat.get('words', []):
                        if isinstance(word, str):
                            word_upper = word.upper().strip()
                            if word_upper in published_words or word_upper in puzzle_words:
                                duplicate_words.add(word_upper)
                            puzzle_words.append(word_upper)

            puzzle['_validation'] = {
                'valid': is_valid,
                'errors': errors,
                'duplicate_words': list(duplicate_words)
            }

        return jsonify([puzzle])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/puzzle', methods=['POST'])
def save_puzzle():
    """Save puzzle without changing puzzles.json - just validates and returns updated puzzle."""
    puzzle_data = request.get_json(silent=True)
    if puzzle_data is None:
        return jsonify({'error': 'Invalid or missing JSON body'}), 400

    # Handle both single puzzle or array (for backward compatibility)
    if isinstance(puzzle_data, list):
        if len(puzzle_data) == 0:
            return jsonify({'error': 'No puzzle to save'}), 400
        puzzle = puzzle_data[0]  # Take first puzzle
    elif isinstance(puzzle_data, dict):
        puzzle = puzzle_data
    else:
        return jsonify({'error': 'Expected puzzle object or array'}), 400

    # Ensure it's a dict and not published
    if not isinstance(puzzle, dict) or puzzle.get('status') == 'published':
        return jsonify({'error': 'Cannot save published puzzle'}), 400

    # Validate puzzle structure
    if 'categories' not in puzzle:
        puzzle['categories'] = []
    if 'language' not in puzzle:
        puzzle['language'] = 'en'

    # ensure serializable
    try:
        json.dumps(puzzle)
    except Exception as e:
        return jsonify({'error': f'JSON serialization failed: {e}'}), 400

    # Load published puzzles for validation
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as fh:
            file_data = json.load(fh)

        if isinstance(file_data, list):
            all_puzzles = file_data
        elif isinstance(file_data, dict) and 'puzzles' in file_data:
            all_puzzles = file_data['puzzles']
            if not isinstance(all_puzzles, list):
                all_puzzles = []
        else:
            all_puzzles = []

        published = [p for p in all_puzzles if isinstance(p, dict) and p.get('status') == 'published']
    except FileNotFoundError:
        published = []

    # Add validation info (same as GET endpoint)
    published_words = set()
    for p in published:
        if isinstance(p, dict):
            for cat in p.get('categories', []):
                if isinstance(cat, dict):
                    for word in cat.get('words', []):
                        if isinstance(word, str):
                            published_words.add(word.upper().strip())

    from puzzle_validator import validate_puzzle
    is_valid, errors = validate_puzzle(puzzle, published)

    # Find duplicate words for highlighting
    duplicate_words = set()
    puzzle_words = []
    for cat in puzzle.get('categories', []):
        if isinstance(cat, dict):
            for word in cat.get('words', []):
                if isinstance(word, str):
                    word_upper = word.upper().strip()
                    if word_upper in published_words or word_upper in puzzle_words:
                        duplicate_words.add(word_upper)
                    puzzle_words.append(word_upper)

    puzzle['_validation'] = {
        'valid': is_valid,
        'errors': errors,
        'duplicate_words': list(duplicate_words)
    }

    resp = {'ok': True, 'puzzle': puzzle}
    return jsonify(resp)


@app.route('/api/regenerate-category', methods=['GET'])
def regenerate_category():
    """Regenerate a single category - either completely new or words for a given category name."""
    try:
        # Ensure .env is loaded before importing - try multiple times
        load_dotenv()
        # Also try explicit path
        env_path = os.path.join(APP_DIR, '.env')
        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path, override=True)

        from regenerate_single_category import generate_single_category, generate_words_for_category

        difficulty = request.args.get('difficulty', 'medium')
        category_name = request.args.get('category_name', '').strip()  # Optional: if provided, generate words for this category

        difficulty_map = {
            "easy": "yellow",
            "medium": "green",
            "hard": "blue",
        }

        # If category_name is provided and not empty, generate words for that category
        if category_name:
            raw = generate_words_for_category(category_name, difficulty)
        else:
            # Load ALL categories from puzzles.json to avoid duplicates
            existing_category_names = set()
            try:
                with open(JSON_PATH, 'r', encoding='utf-8') as fh:
                    file_data = json.load(fh)

                # Handle both formats
                if isinstance(file_data, list):
                    all_puzzles = file_data
                elif isinstance(file_data, dict) and 'puzzles' in file_data:
                    all_puzzles = file_data['puzzles']
                    if not isinstance(all_puzzles, list):
                        all_puzzles = []
                else:
                    all_puzzles = []

                # Extract all category names from all puzzles
                for puzzle in all_puzzles:
                    if isinstance(puzzle, dict):
                        for cat in puzzle.get('categories', []):
                            if isinstance(cat, dict):
                                cat_name = cat.get('name', '').strip().lower()
                                if cat_name:
                                    existing_category_names.add(cat_name)
            except:
                all_puzzles = []
                existing_category_names = set()

            # add banned categories as "existing" so model avoids them conceptually
            banned = load_banned_categories()
            for b in banned:
                existing_category_names.add(b)

            # Convert to list format for generate_single_category
            existing_categories = [{'name': name} for name in existing_category_names]

            # Generate completely new category (not a variation)
            raw = generate_single_category(difficulty, existing_categories)

            # If model still returns a banned name, retry a few times
            max_attempts = 5
            attempt = 1
            while attempt <= max_attempts and normalize_category(raw.get("name", "")) in banned:
                raw = generate_single_category(difficulty, existing_categories)
                attempt += 1

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
    """Append current puzzle as a new published puzzle at the end of puzzles.json."""
    try:
        # Get the current puzzle from request (the one being exported)
        puzzle = request.get_json(silent=True)
        if not puzzle:
            return jsonify({'error': 'No puzzle to export'}), 400

        # Handle array format (take first)
        if isinstance(puzzle, list):
            if len(puzzle) == 0:
                return jsonify({'error': 'No puzzle to export'}), 400
            puzzle = puzzle[0]

        if not isinstance(puzzle, dict):
            return jsonify({'error': 'Invalid puzzle format'}), 400

        # Load all existing puzzles from puzzles.json
        try:
            with open(JSON_PATH, 'r', encoding='utf-8') as fh:
                file_data = json.load(fh)

            # Handle both formats
            if isinstance(file_data, list):
                all_puzzles = file_data
                use_object_format = False
            elif isinstance(file_data, dict) and 'puzzles' in file_data:
                all_puzzles = file_data['puzzles']
                if not isinstance(all_puzzles, list):
                    all_puzzles = []
                use_object_format = True
            else:
                all_puzzles = []
                use_object_format = False
        except FileNotFoundError:
            all_puzzles = []
            use_object_format = False

        # Ensure categories exist - if empty, something went wrong with collection
        if 'categories' not in puzzle or not puzzle.get('categories'):
            return jsonify({'error': 'Puzzle has no categories. Cannot export empty puzzle.'}), 400

        # Compute next ID and next date based on ALL existing puzzles
        from puzzle_manager import get_next_id, get_next_date
        next_id = get_next_id(all_puzzles)
        next_date = get_next_date(all_puzzles)

        # Build a clean puzzle object with fields in desired order
        # and WITHOUT status
        ordered_puzzle = {
            "date": next_date,
            "id": next_id,
            "language": puzzle.get("language", "en"),
            "categories": puzzle.get("categories", []),
        }

        # Append to the end without touching existing puzzles
        all_puzzles.append(ordered_puzzle)

        # Write back
        json_dir = os.path.dirname(JSON_PATH)
        if json_dir and not os.path.exists(json_dir):
            os.makedirs(json_dir, exist_ok=True)

        tmp_path = JSON_PATH + '.tmp'
        try:
            with open(tmp_path, 'w', encoding='utf-8') as fh:
                if use_object_format:
                    json.dump({'puzzles': all_puzzles}, fh, indent=2, ensure_ascii=False)
                else:
                    json.dump(all_puzzles, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())

            os.replace(tmp_path, JSON_PATH)
        except Exception as write_error:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
            raise Exception(f"Failed to write to {JSON_PATH}: {str(write_error)}")

        # Auto-commit and push to git (same as before)
        git_enabled = os.getenv('AUTO_GIT_COMMIT', 'true').lower() in ('true', '1', 'yes', 'on')
        git_status = {}
        if git_enabled:
            commit_msg = f"Export puzzle to published - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            print(f"Attempting git commit/push to {GROOPED_REPO_DIR}...")
            git_success, git_output, git_error = _commit_and_push(commit_msg, git_repo_dir=GROOPED_REPO_DIR)
            print(f"Git result: success={git_success}, output={git_output}, error={git_error}")
            git_status = {
                'success': git_success,
                'message': git_output if git_success else git_error
            }
        else:
            git_status = {
                'success': None,
                'message': 'Auto-commit disabled'
            }
            print("Git auto-commit is disabled")

        print(f"Export successful: NEW Puzzle ID {puzzle.get('id')} appended to {JSON_PATH}")
        print(f"Total puzzles after export: {len(all_puzzles)}")

        resp = {
            'ok': True,
            'exported': 1,
            'git': git_status,
            'next_puzzle': True,
            'puzzle_id': puzzle.get('id'),
            'file_path': JSON_PATH
        }
        return jsonify(resp)
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        print(f"Export error: {error_msg}")
        print(f"Traceback: {error_trace}")
        return jsonify({'error': error_msg, 'traceback': error_trace}), 500

if __name__ == "__main__":
    # Run the editor locally
    app.run(host="127.0.0.1", port=5001, debug=True)
