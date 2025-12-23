#!/usr/bin/env python3
"""Generate draft puzzles with status field."""

from puzzle_generator import generate_connections_puzzle, build_week_of_puzzles
from puzzle_manager import assign_ids_and_dates
import json


def generate_drafts(count: int = 7, start_date: str = None):
    """Generate draft puzzles."""
    # Generate raw puzzles
    puzzles = []
    for i in range(count):
        raw = generate_connections_puzzle()
        difficulty_map = {
            "easy": "yellow",
            "medium": "green",
            "hard": "blue",
        }
        
        categories = []
        for cat in raw["categories"]:
            diff = cat.get("difficulty", "medium")
            color = difficulty_map.get(diff, "green")
            words_upper = [w.upper() for w in cat["words"]]
            categories.append({
                "name": cat["name"],
                "words": words_upper,
                "difficulty": color,
            })
        
        puzzles.append({
            "status": "draft",
            "language": "en",
            "categories": categories,
        })
    
    # Auto-assign IDs and dates
    puzzles = assign_ids_and_dates(puzzles, start_date)
    
    return puzzles


if __name__ == "__main__":
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    start_date = sys.argv[2] if len(sys.argv) > 2 else None
    
    drafts = generate_drafts(count, start_date)
    
    # Load existing and append
    try:
        with open("puzzles_week.json", "r", encoding="utf-8") as f:
            all_puzzles = json.load(f)
    except FileNotFoundError:
        all_puzzles = []
    
    all_puzzles.extend(drafts)
    
    with open("puzzles_week.json", "w", encoding="utf-8") as f:
        json.dump(all_puzzles, f, indent=2, ensure_ascii=False)
    
    print(f"Generated {count} draft puzzles")
    print(f"Total puzzles in file: {len(all_puzzles)}")

