    let puzzles = [];
    let currentIndex = 0;
    let lastSavedState = null; // Store the last saved puzzle state
    let hasUnsavedChanges = false;
    
    const difficultyToColor = ['purple', 'green', 'blue', 'orange'];
    const colorToDifficulty = {
      'purple': 'yellow',
      'green': 'green', 
      'blue': 'blue',
      'orange': 'purple'
    };

    function setStatus(msg) {
      document.getElementById('status').textContent = msg;
    }


    // Get current form data as JSON string for comparison
    function getCurrentStateString() {
      const puzzle = collectData();
      // Remove _validation field for comparison
      const cleanPuzzle = {...puzzle};
      delete cleanPuzzle._validation;
      return JSON.stringify(cleanPuzzle);
    }

    // Check if there are unsaved changes
    function checkUnsavedChanges() {
      if (!lastSavedState) {
        hasUnsavedChanges = false;
        return false;
      }
      const currentState = getCurrentStateString();
      hasUnsavedChanges = currentState !== lastSavedState;
      updateExportButtonState();
      return hasUnsavedChanges;
    }

    // Update export button enabled/disabled state
    function updateExportButtonState() {
      const exportBtn = document.getElementById('exportBtn');
      exportBtn.disabled = hasUnsavedChanges || puzzles.length === 0 || !puzzles[0];
    }

function setButtonLoading(buttonId, loading) {
  const btn = document.getElementById(buttonId);
  if (!btn) return;
  if (loading) {
    btn.classList.add('loading');
    btn.classList.remove('success');
    btn.disabled = true;
  } else {
    btn.classList.remove('loading');
    btn.disabled = false;
  }
  updateExportButtonState();
}

function setButtonSuccess(buttonId, duration = 1500) {
  const btn = document.getElementById(buttonId);
  if (!btn) return;
  btn.classList.remove('loading');
  btn.classList.add('success');
  btn.disabled = false;

  setTimeout(() => {
    btn.classList.remove('success');
    updateExportButtonState();
  }, duration);
}


    function updateUI() {
      if (puzzles.length === 0) {
        setStatus('No puzzles');
        lastSavedState = null;
        updateExportButtonState();
        return;
      }
      
      const puzzle = puzzles[0];  // Always use first puzzle
      if (!puzzle) return;

      const categories = puzzle.categories || [];
      
      // Map difficulty to color based on position (default mapping)
      categories.forEach((cat, idx) => {
        const diff = cat.difficulty || 'yellow';
        const defaultColor = difficultyToColor[idx] || 'purple';
        // Find which color this difficulty maps to
        const color = Object.keys(colorToDifficulty).find(c => colorToDifficulty[c] === diff) || defaultColor;
        
        const categoryEl = document.querySelector(`.category[data-category-index="${idx}"]`);
        if (categoryEl) {
          // Update the category's color
          categoryEl.dataset.color = color;
          const colorSquare = categoryEl.querySelector('.color-square');
          if (colorSquare) {
            colorSquare.className = `color-square ${color}`;
            colorSquare.dataset.currentColor = color;
          }
          
          const nameInput = categoryEl.querySelector('.category-name-input');
          if (nameInput) nameInput.value = cat.name || '';
          
          const words = cat.words || [];
          words.forEach((word, wordIdx) => {
            const wordInput = categoryEl.querySelector(`.word-input[data-word="${wordIdx}"]`);
            if (wordInput) wordInput.value = word || '';
          });
        }
      });

      // Clear categories that don't have data
      for (let i = categories.length; i < 4; i++) {
        const categoryEl = document.querySelector(`.category[data-category-index="${i}"]`);
        if (categoryEl) {
          categoryEl.querySelector('.category-name-input').value = '';
          categoryEl.querySelectorAll('.word-input').forEach(inp => inp.value = '');
        }
      }

      // Show validation errors and highlight duplicate words
      showValidationErrors(puzzle);
      highlightDuplicateWords(puzzle);
      
      // Update saved state after UI is updated
      lastSavedState = getCurrentStateString();
      hasUnsavedChanges = false;
      updateExportButtonState();
    }
    
    function showValidationErrors(puzzle) {
      const errorsDiv = document.getElementById('validationErrors');
      const validation = puzzle._validation || {valid: true, errors: []};
      
      if (!validation.valid && validation.errors.length > 0) {
        errorsDiv.style.display = 'block';
        errorsDiv.className = 'validation-errors has-errors';
        errorsDiv.innerHTML = '<strong>⚠️ Validation Errors:</strong><ul>' +
          validation.errors.map(e => `<li>${e}</li>`).join('') +
          '</ul>';
      } else {
        errorsDiv.style.display = 'none';
      }
    }
    
    function highlightDuplicateWords(puzzle) {
      const validation = puzzle._validation || {duplicate_words: []};
      const duplicateWords = new Set((validation.duplicate_words || []).map(w => w.toUpperCase()));
      
      // Clear all duplicate highlighting first
      document.querySelectorAll('.word-input').forEach(inp => {
        inp.classList.remove('duplicate');
      });
      
      // Highlight duplicate words
      document.querySelectorAll('.word-input').forEach(inp => {
        const word = inp.value.toUpperCase().trim();
        if (word && duplicateWords.has(word)) {
          inp.classList.add('duplicate');
        }
      });
    }

    function collectData() {
      // Start with existing puzzle data to preserve all fields
      const existingPuzzle = puzzles.length > 0 && puzzles[0] ? puzzles[0] : {};
      const puzzle = {
        ...existingPuzzle,  // Preserve existing fields
        language: existingPuzzle.language || 'en',
        categories: []  // Will rebuild from form
      };
      
      // Ensure ID and date are preserved
      if (existingPuzzle.id) {
        puzzle.id = existingPuzzle.id;
      }
      if (existingPuzzle.date) {
        puzzle.date = existingPuzzle.date;
      }
      
      // Remove _validation field (internal use only)
      delete puzzle._validation;

      // Collect categories in order by their index
      for (let i = 0; i < 4; i++) {
        const categoryEl = document.querySelector(`.category[data-category-index="${i}"]`);
        if (categoryEl) {
          const nameInput = categoryEl.querySelector('.category-name-input');
          const wordInputs = categoryEl.querySelectorAll('.word-input');
          const name = nameInput.value.trim();
          const words = Array.from(wordInputs).map(inp => inp.value.trim().toUpperCase()).filter(w => w);
          const currentColor = categoryEl.dataset.color || difficultyToColor[i] || 'purple';

          // Always add category if it has either name or words (or both)
          // This ensures we collect all 4 categories from the form
          if (name || words.length > 0) {
            puzzle.categories.push({
              name: name,
              words: words.length === 4 ? words : words.concat(Array(4 - words.length).fill('')),
              difficulty: colorToDifficulty[currentColor] || 'yellow'
            });
          }
        }
      }

      return puzzle;
    }

    async function load() {
      setStatus('Loading...');
      try {
        const r = await fetch('/api/puzzle');
        if (!r.ok) throw new Error('Failed to load');
        puzzles = await r.json();
        if (!Array.isArray(puzzles)) puzzles = [];
        if (puzzles.length === 0) {
          setStatus('No puzzles found');
          return;
        }
        currentIndex = 0;
        updateUI();
        setStatus('Puzzle loaded');
      } catch (e) {
        setStatus('Load failed');
        alert('Load failed: ' + e);
      }
    }

    async function save() {
      setStatus('Saving...');
      setButtonLoading('saveBtn', true);
      try {
        const puzzle = collectData();
        puzzles[0] = puzzle;

        const r = await fetch('/api/puzzle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(puzzle)  // Send single puzzle, not array
        });
        const res = await r.json();
        if (!r.ok) throw new Error(res.error || JSON.stringify(res));
        
        // Update puzzle with validation data from server response
        if (res.puzzle) {
          puzzles[0] = res.puzzle;
        }
        
        // Validate and highlight duplicates on the saved puzzle
        showValidationErrors(puzzles[0]);
        highlightDuplicateWords(puzzles[0]);
        
        // Update saved state
        lastSavedState = getCurrentStateString();
        hasUnsavedChanges = false;
        updateExportButtonState();
        
        setStatus('Saved');
        setButtonSuccess('saveBtn');

      } catch (e) {
        setStatus('Save failed');
        setButtonLoading('saveBtn', false);
        alert('Save failed: ' + e);
      }
    }

document.getElementById('reloadBtn').addEventListener('click', async () => {
  if (!confirm('Reload from disk? Unsaved changes will be lost.')) return;

  setStatus('Reloading...');
  setButtonLoading('reloadBtn', true);
  try {
    await load();
    setStatus('Reloaded');
    setButtonSuccess('reloadBtn');
  } catch (e) {
    setStatus('Reload failed');
    alert('Reload failed: ' + e);
  } finally {
    setButtonLoading('reloadBtn', false);
  }
});

    
    document.getElementById('exportBtn').addEventListener('click', async () => {
      if (puzzles.length === 0 || !puzzles[0]) {
        alert('No puzzle to export');
        return;
      }
      
      if (hasUnsavedChanges) {
        alert('Please save the puzzle before exporting.');
        return;
      }
      
      setStatus('Exporting...');
      setButtonLoading('exportBtn', true);
      try {
        const puzzle = collectData();
        
        const r = await fetch('/api/export', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(puzzle)
        });
        const res = await r.json();
        if (!r.ok) throw new Error(res.error || JSON.stringify(res));
        
        setStatus('Exported! Loading next puzzle...');
        setButtonSuccess('exportBtn');
        
        // Load next puzzle
        await load();
      } catch (e) {
        setStatus('Export failed');
        setButtonLoading('exportBtn', false);
        alert('Export failed: ' + e);
      }
    });

    // Track input changes for unsaved changes detection
    document.querySelectorAll('.word-input, .category-name-input').forEach(inp => {
      inp.addEventListener('input', (e) => {
        if (inp.classList.contains('word-input')) {
          e.target.value = e.target.value.toUpperCase();
          // Update duplicate highlighting after input
          if (puzzles.length > 0 && puzzles[0]) {
            highlightDuplicateWords(puzzles[0]);
          }
        }
        // Check for unsaved changes
        checkUnsavedChanges();
      });
    });

    // Color square and arrow click handlers
    document.querySelectorAll('.color-square-wrapper').forEach(wrapper => {
      wrapper.addEventListener('click', (e) => {
        e.stopPropagation();
        const dropdown = wrapper.querySelector('.color-dropdown');
        // Close all other dropdowns
        document.querySelectorAll('.color-dropdown').forEach(d => {
          if (d !== dropdown) d.classList.remove('show');
        });
        // Toggle this dropdown
        dropdown.classList.toggle('show');
      });
    });

    // Color option selection handlers
    document.querySelectorAll('.color-option').forEach(option => {
      option.addEventListener('click', (e) => {
        e.stopPropagation();
        const newColor = option.dataset.color;
        const categoryEl = option.closest('.category');
        const oldColor = categoryEl.dataset.color;
        
        // If selecting a color that's already used by another category, swap them
        if (newColor !== oldColor) {
          const otherCategory = document.querySelector(`.category[data-color="${newColor}"]`);
          if (otherCategory) {
            // Swap colors
            otherCategory.dataset.color = oldColor;
            const otherSquare = otherCategory.querySelector('.color-square');
            otherSquare.className = `color-square ${oldColor}`;
            otherSquare.dataset.currentColor = oldColor;
          }
          
          // Update this category's color
          categoryEl.dataset.color = newColor;
          const square = categoryEl.querySelector('.color-square');
          square.className = `color-square ${newColor}`;
          square.dataset.currentColor = newColor;
        }
        
        // Close all dropdowns
        document.querySelectorAll('.color-dropdown').forEach(d => d.classList.remove('show'));
        
        // Check for unsaved changes after color change
        checkUnsavedChanges();
      });
    });

    // Close dropdowns when clicking outside
    document.addEventListener('click', () => {
      document.querySelectorAll('.color-dropdown').forEach(d => d.classList.remove('show'));
    });

    // Regenerate category buttons
    document.querySelectorAll('.regenerate-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const categoryIdx = parseInt(btn.dataset.category);
        const categoryEl = document.querySelector(`.category[data-category-index="${categoryIdx}"]`);
        const currentColor = categoryEl.dataset.color;
        const difficultyMap = {
          'purple': 'easy',
          'green': 'medium',
          'blue': 'medium',
          'orange': 'hard'
        };
        const difficulty = difficultyMap[currentColor] || 'medium';
        
        const nameInput = categoryEl.querySelector('.category-name-input');
        const wordInputs = categoryEl.querySelectorAll('.word-input');
        
        // Check if all words are empty
        const allWordsEmpty = Array.from(wordInputs).every(inp => !inp.value.trim());
        const categoryName = nameInput.value.trim();
        
        // If all words are empty and category name is provided, use category name as prompt
        let apiUrl = `/api/regenerate-category?difficulty=${difficulty}`;
        if (allWordsEmpty && categoryName) {
          apiUrl += `&category_name=${encodeURIComponent(categoryName)}`;
        }
        
        btn.disabled = true;
        btn.textContent = '...';
        setStatus(allWordsEmpty && categoryName ? 'Generating words for category...' : 'Regenerating category...');
        
        try {
          const r = await fetch(apiUrl, {
            method: 'GET'
          });
          if (r.ok) {
            const category = await r.json();
            
            // Only update category name if it wasn't provided by user (or was empty)
            if (!allWordsEmpty || !categoryName) {
              nameInput.value = category.name;
            }
            
            // Update all 4 words
            category.words.forEach((word, idx) => {
              if (wordInputs[idx]) {
                wordInputs[idx].value = word;
              }
            });
            
            setStatus('Category regenerated');
            // Trigger input events to update highlighting and check unsaved changes
            wordInputs.forEach(inp => {
              inp.dispatchEvent(new Event('input'));
            });
            nameInput.dispatchEvent(new Event('input'));
          } else {
            const error = await r.json();
            alert('Failed to regenerate category: ' + (error.error || 'Unknown error'));
          }
        } catch (e) {
          alert('Error regenerating category: ' + e);
        } finally {
          btn.disabled = false;
          btn.textContent = '🔄';
        }
      });
    });

    // Initialize export button state
    updateExportButtonState();
    
    // Load on page load
    load();