# Puzzle Workflow Proposal

## Recommended Workflow

### 1. **Generation Phase** → Draft Status
- Generate puzzles (1-10 at a time)
- Save to `puzzles_draft.json` (separate from published)
- Status: `"status": "draft"`
- Auto-generate ID and date based on existing puzzles
- No ID/date fields shown in editor for drafts

### 2. **Review/Edit Phase** → Review Status
- Review in editor
- Edit as needed
- Status: `"status": "reviewed"` (manual or auto after save)

### 3. **Validation Phase** → Validation Checks
- Check for duplicate words across all published puzzles
- Check for duplicate category names
- Flag issues with visual indicators
- Allow fixing before approval

### 4. **Approval Phase** → Approved Status
- Mark puzzles as `"status": "approved"`
- Auto-generate final ID and date
- Ready for export

### 5. **Export Phase** → Published Status
- Export approved puzzles to other repo
- Move to `puzzles_published.json` or append to main file
- Status: `"status": "published"`
- ID and date locked

## Proposed File Structure

```
puzzles_draft.json      # Newly generated, being reviewed
puzzles_published.json   # Approved and sent to other repo
puzzles_week.json        # Current (can become published)
```

OR

```
puzzles_week.json        # All puzzles with status field
  - status: "draft" | "reviewed" | "approved" | "published"
```

## Implementation Plan

1. **Add status field to puzzles**
2. **Auto ID/Date generation** - Calculate next ID and date from published puzzles
3. **Validation system** - Check duplicates before approval
4. **Status management UI** - Buttons to change status
5. **Export functionality** - Send approved puzzles to other repo
6. **Hide ID/Date in editor** for drafts, show for published

## Next Steps

Would you like me to:
1. Implement the status system?
2. Add validation checks?
3. Create export functionality?
4. Update the editor to handle status workflow?

