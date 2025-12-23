#!/bin/bash
# Setup script for Grooped Puzzle Generator repository

# Initialize git if not already initialized
if [ ! -d .git ]; then
    echo "Initializing git repository..."
    git init
    git branch -M main
fi

# Add all files
echo "Adding all files..."
git add -A

# Create initial commit
echo "Creating initial commit..."
git commit -m "Initial commit: Grooped puzzle generator"

# Add remote (will fail if already exists, that's okay)
echo "Adding remote repository..."
git remote add origin https://github.com/roieshalom/grooped-puzzle-generator.git 2>/dev/null || git remote set-url origin https://github.com/roieshalom/grooped-puzzle-generator.git

echo ""
echo "✅ Git repository initialized!"
echo ""
echo "Next steps:"
echo "1. Create the GitHub repository at: https://github.com/new"
echo "   - Name it: grooped-puzzle-generator"
echo "   - Don't initialize with README"
echo ""
echo "2. Then run: git push -u origin main"
echo ""
echo "Or if the repo already exists, just run: git push -u origin main"

