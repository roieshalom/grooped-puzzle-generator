#!/usr/bin/env python3
"""Validation functions for puzzles."""

import json
from typing import List, Dict, Set, Tuple


def load_published_puzzles(json_path: str = None) -> List[Dict]:
    """Load published puzzles from Grooped repo's 2025_puzzles.json."""
    if json_path is None:
        # Try to find Grooped repo - check common locations
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        
        # Try ../grooped/2025_puzzles.json first (new name)
        grooped_path = os.path.join(parent_dir, 'grooped', '2025_puzzles.json')
        if os.path.exists(grooped_path):
            json_path = grooped_path
        else:
            # Fallback: try ../connections/2025_puzzles.json (old name)
            connections_path = os.path.join(parent_dir, 'connections', '2025_puzzles.json')
            if os.path.exists(connections_path):
                json_path = connections_path
            else:
                # Final fallback: try same directory
                json_path = os.path.join(current_dir, '2025_puzzles.json')
                if not os.path.exists(json_path):
                    return []
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            puzzles = json.load(f)
        # Return all puzzles from the published file
        return puzzles if isinstance(puzzles, list) else []
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Warning: Could not load published puzzles from {json_path}: {e}")
        return []


def get_all_words(puzzles: List[Dict]) -> Set[str]:
    """Extract all words from all puzzles."""
    words = set()
    for puzzle in puzzles:
        for category in puzzle.get('categories', []):
            for word in category.get('words', []):
                words.add(word.upper().strip())
    return words


def get_all_category_names(puzzles: List[Dict]) -> Set[str]:
    """Extract all category names from all puzzles."""
    names = set()
    for puzzle in puzzles:
        for category in puzzle.get('categories', []):
            name = category.get('name', '').strip()
            if name:
                names.add(name.lower())
    return names


def validate_puzzle(puzzle: Dict, published_puzzles: List[Dict] = None) -> Tuple[bool, List[str]]:
    """
    Validate a single puzzle against published puzzles.
    Returns (is_valid, list_of_errors).
    """
    errors = []
    
    if published_puzzles is None:
        published_puzzles = load_published_puzzles()
    
    published_words = get_all_words(published_puzzles)
    published_categories = get_all_category_names(published_puzzles)
    
    # Check puzzle structure
    if 'categories' not in puzzle:
        errors.append("Missing 'categories' field")
        return False, errors
    
    if len(puzzle['categories']) != 4:
        errors.append(f"Expected 4 categories, found {len(puzzle['categories'])}")
    
    # Check for duplicate words within the puzzle (only inside this 16‑word grid)
    puzzle_words = []
    for cat in puzzle['categories']:
        for word in cat.get('words', []):
            word_upper = word.upper().strip()
            if word_upper in puzzle_words:
                errors.append(f"Duplicate word '{word_upper}' within this puzzle")
            puzzle_words.append(word_upper)
    
    # NOTE: removed cross‑puzzle duplicate check so words can repeat in future puzzles
    # If you ever want to turn this back on, uncomment:
    # for word in puzzle_words:
    #     if word in published_words:
    #         errors.append(f"Word '{word}' already exists in published puzzles")
    
    # Check for duplicate category names
    puzzle_categories = []
    for cat in puzzle['categories']:
        name = cat.get('name', '').strip().lower()
        if name:
            if name in puzzle_categories:
                errors.append(f"Duplicate category name '{cat.get('name')}' within this puzzle")
            puzzle_categories.append(name)
            
            if name in published_categories:
                errors.append(f"Category name '{cat.get('name')}' already exists in published puzzles")
    
    # Check each category has 4 words
    for i, cat in enumerate(puzzle['categories']):
        words = cat.get('words', [])
        if len(words) != 4:
            errors.append(f"Category {i+1} has {len(words)} words, expected 4")
    
    return len(errors) == 0, errors


def validate_puzzles(puzzles: List[Dict]) -> Dict[str, Tuple[bool, List[str]]]:
    """
    Validate multiple puzzles.
    Returns dict mapping puzzle index to (is_valid, errors).
    """
    published = load_published_puzzles()
    results = {}
    
    for idx, puzzle in enumerate(puzzles):
        is_valid, errors = validate_puzzle(puzzle, published)
        results[str(idx)] = (is_valid, errors)
    
    return results


if __name__ == "__main__":
    # Test validation
    test_puzzle = {
        "categories": [
            {"name": "Test", "words": ["WORD1", "WORD2", "WORD3", "WORD4"], "difficulty": "yellow"}
        ]
    }
    is_valid, errors = validate_puzzle(test_puzzle)
    print(f"Valid: {is_valid}")
    if errors:
        print("Errors:", errors)
