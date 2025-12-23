# Grooped Puzzle Generator

A tool for generating and editing Connections-style word puzzles using OpenAI's API.

## Features

- **Puzzle Generation**: Automatically generates a week's worth of Grooped puzzles using GPT-4
- **Web Editor**: Browser-based JSON editor for manually editing puzzles
- **Flexible Difficulty**: Supports easy, medium, and hard categories with color coding

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment

Create a `.env` file in the project root with your OpenAI API key:

```
OPENAI_API_KEY=your_api_key_here
```

### 3. Generate Puzzles

Run the puzzle generator to create a week of puzzles:

```bash
python puzzle_generator.py
```

This will generate 7 puzzles and save them to `puzzles_week.json`.

### 4. Edit Puzzles (Optional)

To edit puzzles in a browser-based interface:

```bash
python edit_puzzles.py
```

Then open `http://127.0.0.1:5001` in your browser.

**Auto-commit to Git**: The editor automatically commits and pushes changes to the git repository when you save puzzles. To disable this, set the environment variable `AUTO_GIT_COMMIT=false` in your `.env` file.

## Project Structure

- `puzzle_generator.py` - Main script for generating puzzles using OpenAI
- `edit_puzzles.py` - Flask server for editing puzzles in the browser
- `puzzles_week.json` - JSON file containing puzzle data
- `templates/editor.html` - Web interface for editing puzzles
- `requirements.txt` - Python dependencies

## Puzzle Format

Each puzzle contains:
- `id`: Unique identifier
- `date`: Puzzle date (DD.MM.YYYY format)
- `language`: Language code (default: "en")
- `categories`: Array of 4 categories, each with:
  - `name`: Category name
  - `words`: Array of 4 words (uppercase)
  - `difficulty`: Color code ("yellow", "green", "blue", or "purple")

## Notes

- The editor saves changes directly to `puzzles_week.json`
- Backups are opt-in via the checkbox in the editor interface
- The server only listens on `127.0.0.1` (localhost) for security

## License

See repository for license information.

