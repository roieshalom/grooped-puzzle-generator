#!/usr/bin/env python3
"""Regenerate a single category for a puzzle."""

from puzzle_generator import generate_connections_puzzle
import json
import sys

def regenerate_category(difficulty: str = "medium"):
    """Generate a single category with specified difficulty."""
    difficulty_map = {
        "easy": "yellow",
        "medium": "green",
        "hard": "blue",
    }
    
    # Generate a full puzzle but we'll only use one category
    raw = generate_connections_puzzle()
    
    # Find a category with the requested difficulty
    for cat in raw["categories"]:
        if cat.get("difficulty", "medium") == difficulty:
            diff = cat.get("difficulty", "medium")
            color = difficulty_map.get(diff, "green")
            words_upper = [w.upper() for w in cat["words"]]
            return {
                "name": cat["name"],
                "words": words_upper,
                "difficulty": color,
            }
    
    # If not found, return first category
    cat = raw["categories"][0]
    diff = cat.get("difficulty", "medium")
    color = difficulty_map.get(diff, "green")
    words_upper = [w.upper() for w in cat["words"]]
    return {
        "name": cat["name"],
        "words": words_upper,
        "difficulty": color,
    }

if __name__ == "__main__":
    difficulty = sys.argv[1] if len(sys.argv) > 1 else "medium"
    category = regenerate_category(difficulty)
    print(json.dumps(category, indent=2))

