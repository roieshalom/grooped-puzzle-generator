# Complete Puzzle Workflow Guide

## Overview

The puzzle editor now supports a complete workflow from generation to export, with validation and status management.

## Workflow Steps

### 1. Generate Draft Puzzles

```bash
python generate_draft_puzzles.py 7
```

This will:
- Generate 7 new puzzles with `status: "draft"`
- Auto-assign IDs and dates (but they're hidden in the editor)
- Append to `puzzles_week.json`

### 2. Review & Edit in Editor

```bash
python edit_puzzles.py
# Open http://127.0.0.1:5001
```

**Editor Features:**
- ✅ **No ID/Date fields** - These are auto-generated when exported
- ✅ **Status dropdown** - Change status: Draft → Reviewed → Approved
- ✅ **Validation warnings** - Shows duplicate words/categories in red
- ✅ **Puzzle counter** - Shows "1 / 7" etc.
- ✅ **Export button** - Exports all approved puzzles

### 3. Validation

The editor automatically validates each puzzle:
- Checks for duplicate words with published puzzles
- Checks for duplicate category names
- Shows errors in red warning box above the puzzle

**Fix errors before approving!**

### 4. Change Status

Use the status dropdown:
- **Draft** - Newly generated, being edited
- **Reviewed** - Edited and checked
- **Approved** - Ready for export

### 5. Export Approved Puzzles

Click **"Export Approved (N)"** button:
- Validates all approved puzzles
- Exports to `puzzles_approved.json`
- **Removes them from the editor** (they're now in the other repo)
- Shows success message with file location

### 6. Send to Other Repo

The exported file `puzzles_approved.json` contains:
- All approved puzzles
- Ready to be added to the other repo
- ID and date will be assigned when added there

## Key Features

### Auto ID/Date Generation
- IDs and dates are **not shown** in the editor
- They're auto-generated when puzzles are exported
- Based on existing published puzzles

### Validation
- Real-time validation against published puzzles
- Shows duplicate words/categories
- Must fix errors before export

### Status Management
- Draft → Reviewed → Approved workflow
- Only approved puzzles can be exported
- Published puzzles are hidden from editor

### Export & Removal
- Export removes puzzles from editor
- They appear in `puzzles_approved.json`
- Ready to send to other repo

## File Structure

```
puzzles_week.json          # All puzzles (draft, reviewed, approved)
puzzles_approved.json      # Exported approved puzzles (for other repo)
```

## Notes

- Published puzzles (`status: "published"`) are automatically hidden from the editor
- ID and date fields are removed - they're auto-generated on export
- Validation runs automatically when loading puzzles
- Export button shows count of approved puzzles

