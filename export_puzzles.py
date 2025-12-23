#!/usr/bin/env python3
"""Export approved puzzles to another repo or file."""

import json
import sys
from puzzle_manager import get_puzzles_by_status, append_to_published
from puzzle_validator import validate_puzzles


def export_approved(output_file: str = "puzzles_approved.json", mark_published: bool = True):
    """Export approved puzzles after validation."""
    approved = get_puzzles_by_status('approved')
    
    if not approved:
        print("No approved puzzles to export.")
        return
    
    # Validate before export
    print(f"Validating {len(approved)} approved puzzles...")
    validation_results = validate_puzzles(approved)
    
    has_errors = False
    for idx, (is_valid, errors) in validation_results.items():
        if not is_valid:
            has_errors = True
            print(f"\nPuzzle {idx} has errors:")
            for error in errors:
                print(f"  - {error}")
    
    if has_errors:
        print("\n⚠️  Some puzzles have validation errors. Fix them before exporting.")
        response = input("Export anyway? (y/N): ")
        if response.lower() != 'y':
            return
    
    # Export to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(approved, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Exported {len(approved)} puzzles to {output_file}")
    
    # Mark as published if requested
    if mark_published:
        append_to_published(approved)
        print(f"✅ Marked {len(approved)} puzzles as published")
    
    # TODO: Add code here to send to other repo (GitHub API, git push, etc.)
    print("\n📤 Next step: Send to other repo")
    print(f"   File: {output_file}")


if __name__ == "__main__":
    output_file = sys.argv[1] if len(sys.argv) > 1 else "puzzles_approved.json"
    export_approved(output_file)

