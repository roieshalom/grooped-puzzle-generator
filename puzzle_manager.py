#!/usr/bin/env python3
"""Puzzle management: ID/date generation, status management, export."""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional


def load_all_puzzles(json_path: str = "puzzles_week.json") -> List[Dict]:
    """Load all puzzles from JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def get_next_id(puzzles: List[Dict] = None) -> str:
    """Get the next available puzzle ID."""
    if puzzles is None:
        puzzles = load_all_puzzles()
    
    # Get all IDs (handle both string and int)
    ids = []
    for p in puzzles:
        pid = p.get('id', '0')
        try:
            ids.append(int(pid))
        except (ValueError, TypeError):
            pass
    
    if not ids:
        return "1"
    
    return str(max(ids) + 1)


def get_next_date(puzzles: List[Dict] = None, start_date: Optional[str] = None) -> str:
    """
    Get the next available puzzle date.
    If start_date provided, use that. Otherwise, find last date and add 1 day.
    """
    if puzzles is None:
        puzzles = load_all_puzzles()
    
    # Get all dates
    dates = []
    for p in puzzles:
        date_str = p.get('date', '')
        if date_str:
            try:
                dates.append(datetime.strptime(date_str, "%d.%m.%Y"))
            except ValueError:
                pass
    
    if start_date:
        try:
            next_date = datetime.strptime(start_date, "%d.%m.%Y")
        except ValueError:
            next_date = datetime.now()
    elif dates:
        next_date = max(dates) + timedelta(days=1)
    else:
        next_date = datetime.now()
    
    return next_date.strftime("%d.%m.%Y")


def assign_ids_and_dates(puzzles: List[Dict], start_date: Optional[str] = None) -> List[Dict]:
    """Assign auto-generated IDs and dates to puzzles without them."""
    all_puzzles = load_all_puzzles()
    result = []
    
    current_id = get_next_id(all_puzzles)
    current_date = get_next_date(all_puzzles, start_date)
    
    for puzzle in puzzles:
        # Only assign if missing or status is draft
        if puzzle.get('status') == 'draft' or 'id' not in puzzle:
            puzzle['id'] = current_id
            current_id = str(int(current_id) + 1)
        
        if puzzle.get('status') == 'draft' or 'date' not in puzzle:
            puzzle['date'] = current_date
            current_date_obj = datetime.strptime(current_date, "%d.%m.%Y")
            current_date = (current_date_obj + timedelta(days=1)).strftime("%d.%m.%Y")
        
        result.append(puzzle)
    
    return result


def get_puzzles_by_status(status: str, puzzles: List[Dict] = None) -> List[Dict]:
    """Get puzzles filtered by status."""
    if puzzles is None:
        puzzles = load_all_puzzles()
    
    return [p for p in puzzles if p.get('status') == status]


def update_puzzle_status(puzzle_id: str, new_status: str, json_path: str = "puzzles_week.json"):
    """Update the status of a puzzle by ID."""
    puzzles = load_all_puzzles(json_path)
    
    for puzzle in puzzles:
        if str(puzzle.get('id')) == str(puzzle_id):
            puzzle['status'] = new_status
            break
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(puzzles, f, indent=2, ensure_ascii=False)


def export_approved_puzzles(output_path: str = "puzzles_approved.json", 
                           json_path: str = "puzzles_week.json") -> List[Dict]:
    """Export approved puzzles to a separate file."""
    puzzles = load_all_puzzles(json_path)
    approved = [p for p in puzzles if p.get('status') == 'approved']
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(approved, f, indent=2, ensure_ascii=False)
    
    return approved


def append_to_published(puzzles_to_add: List[Dict], json_path: str = "puzzles_week.json"):
    """Append approved puzzles to the published list and mark as published."""
    all_puzzles = load_all_puzzles(json_path)
    
    # Mark as published
    for puzzle in puzzles_to_add:
        puzzle['status'] = 'published'
        # Ensure ID and date are set
        if 'id' not in puzzle:
            puzzle['id'] = get_next_id(all_puzzles)
        if 'date' not in puzzle:
            puzzle['date'] = get_next_date(all_puzzles)
    
    # Add to list (avoid duplicates by ID)
    existing_ids = {str(p.get('id')) for p in all_puzzles}
    for puzzle in puzzles_to_add:
        if str(puzzle.get('id')) not in existing_ids:
            all_puzzles.append(puzzle)
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_puzzles, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # Test
    print(f"Next ID: {get_next_id()}")
    print(f"Next date: {get_next_date()}")

