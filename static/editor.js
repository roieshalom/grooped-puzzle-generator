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

// Inline status / message helper
function setStatus(text, type = 'info', duration = 3000) {
  const box = document.getElementById('messageBox');
  if (!box) return;

  box.textContent = text;
  box.style.display = 'inline-flex';

  box.classList.remove('success', 'error', 'info');
  if (type) box.classList.add(type);

  clearTimeout(setStatus._timeout);
  if (duration > 0) {
    setStatus._timeout = setTimeout(() => {
      box.style.display = 'none';
    }, duration);
  }
}

// Get current form data as JSON string for comparison
function getCurrentStateString() {
  const puzzle = collectData();
  // Remove _validation field for comparison
  const cleanPuzzle = { ...puzzle };
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
    setStatus('No puzzles', 'info', 2000);
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
  const validation = puzzle._validation || { valid: true, errors: [] };

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
  const validation = puzzle._validation || { duplicate_words: [] };
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
    const res = await r.json();

    // Normalize: backend returns [puzzle]
    if (Array.isArray(res) && res.length > 0 && res[0]) {
      puzzles = [res[0]];
    } else {
      puzzles = [];
    }

    if (puzzles.length === 0) {
      setStatus('No puzzles found', 'info', 2000);
      updateExportButtonState();
      return;
    }

    currentIndex = 0;
    updateUI();
    setStatus('Puzzle loaded', 'info', 2000);
  } catch (e) {
    setStatus('Load failed', 'error', 4000);
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
      body: JSON.stringify(puzzle)
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error || JSON.stringify(res));

    // Normalize: backend returns { ok: true, puzzle: { ... } }
    if (res.puzzle) {
      puzzles = [res.puzzle];
    }

    showValidationErrors(puzzles[0]);
    highlightDuplicateWords(puzzles[0]);

    lastSavedState = getCurrentStateString();
    hasUnsavedChanges = false;
    updateExportButtonState();

    setButtonSuccess('saveBtn');
    setStatus('Puzzle saved', 'success', 3000);
  } catch (e) {
    setStatus('Save failed', 'error', 4000);
    setButtonLoading('saveBtn', false);
    alert('Save failed: ' + e);
  }
}

document.getElementById('reloadBtn').addEventListener('click', async () => {
  setStatus('Reloading...');
  setButtonLoading('reloadBtn', true);
  try {
    await load();
    setButtonSuccess('reloadBtn');
    setStatus('Puzzle reloaded from disk', 'info', 3000);
  } catch (e) {
    setStatus('Reload failed', 'error', 4000);
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

    setButtonSuccess('exportBtn');
    setStatus('Puzzle exported', 'success', 4000);

    await load();
  } catch (e) {
    setStatus('Export failed', 'error', 4000);
    setButtonLoading('exportBtn', false);
    alert('Export failed: ' + e);
  }
});

document.getElementById('generateBtn').addEventListener('click', async () => {
  setStatus('Generating new puzzle...');
  setButtonLoading('generateBtn', true);
  try {
    const r = await fetch('/api/generate-puzzle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const res = await r.json();
    if (!r.ok) {
      throw new Error(res.error || JSON.stringify(res));
    }

    if (!res || !res.categories) {
      throw new Error('Invalid puzzle from generator');
    }

    // Assign 4 unique colors: yellow, green, blue, purple (no duplicate greens)
    const uniqueColors = ['yellow', 'green', 'blue', 'purple'];
    res.categories.forEach((cat, index) => {
      cat.difficulty = uniqueColors[index % uniqueColors.length];
    });

    // REMOVE DUPLICATES immediately after generate
    const seen = new Set();
    res.categories = res.categories.filter(cat => {
      if (seen.has(cat.name)) return false;
      seen.add(cat.name);
      return true;
    });

    puzzles = [res];
    currentIndex = 0;
    updateUI();
    setButtonSuccess('generateBtn');
    setStatus('New puzzle generated - unique colors', 'info', 3000);
  } catch (e) {
    setStatus('Generate failed', 'error', 4000);
    setButtonLoading('generateBtn', false);
    alert('Failed to generate puzzle: ' + e);
  }
});

// Track input changes for unsaved changes detection
document.querySelectorAll('.word-input, .category-name-input').forEach(inp => {
  inp.addEventListener('input', (e) => {
    if (inp.classList.contains('word-input')) {
      e.target.value = e.target.value.toUpperCase();
      if (puzzles.length > 0 && puzzles[0]) {
        highlightDuplicateWords(puzzles[0]);
      }
    }
    checkUnsavedChanges();
  });
});

// Color square and arrow click handlers
document.querySelectorAll('.color-square-wrapper').forEach(wrapper => {
  wrapper.addEventListener('click', (e) => {
    e.stopPropagation();
    const dropdown = wrapper.querySelector('.color-dropdown');
    document.querySelectorAll('.color-dropdown').forEach(d => {
      if (d !== dropdown) d.classList.remove('show');
    });
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

    if (newColor !== oldColor) {
      const otherCategory = document.querySelector(`.category[data-color="${newColor}"]`);
      if (otherCategory) {
        otherCategory.dataset.color = oldColor;
        const otherSquare = otherCategory.querySelector('.color-square');
        otherSquare.className = `color-square ${oldColor}`;
        otherSquare.dataset.currentColor = oldColor;
      }

      categoryEl.dataset.color = newColor;
      const square = categoryEl.querySelector('.color-square');
      square.className = `color-square ${newColor}`;
      square.dataset.currentColor = newColor;
    }

    document.querySelectorAll('.color-dropdown').forEach(d => d.classList.remove('show'));
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
    await regenerateCategoryForIndex(categoryIdx, { usePromptIfEmpty: true });
  });
});

// Skip & ban buttons
document.querySelectorAll('.ban-btn').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const categoryIdx = parseInt(btn.dataset.category);
    await banAndReplaceCategory(categoryIdx);
  });
});

async function regenerateCategoryForIndex(categoryIdx, options = {}) {
  const { usePromptIfEmpty } = options;
  const categoryEl = document.querySelector(`.category[data-category-index="${categoryIdx}"]`);
  if (!categoryEl) return;

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

  const allWordsEmpty = Array.from(wordInputs).every(inp => !inp.value.trim());
  const categoryName = nameInput.value.trim();

  let apiUrl = `/api/regenerate-category?difficulty=${difficulty}`;
  if (usePromptIfEmpty && allWordsEmpty && categoryName) {
    apiUrl += `&category_name=${encodeURIComponent(categoryName)}`;
  }

  const regenBtn = categoryEl.querySelector('.regenerate-btn');
  if (regenBtn) {
    regenBtn.disabled = true;
    regenBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
  }
  setStatus(allWordsEmpty && categoryName && usePromptIfEmpty ? 'Generating words for category...' : 'Regenerating category...');

  try {
    const r = await fetch(apiUrl, { method: 'GET' });
    if (r.ok) {
      const category = await r.json();

      if (!allWordsEmpty || !categoryName || !usePromptIfEmpty) {
        nameInput.value = category.name;
      }

      category.words.forEach((word, idx) => {
        if (wordInputs[idx]) {
          wordInputs[idx].value = word;
        }
      });

      setStatus('Category regenerated', 'info', 3000);
      wordInputs.forEach(inp => {
        inp.dispatchEvent(new Event('input'));
      });
      nameInput.dispatchEvent(new Event('input'));
    } else {
      const error = await r.json();
      alert('Failed to regenerate category: ' + (error.error || 'Unknown error'));
      setStatus('Category regeneration failed', 'error', 4000);
    }
  } catch (e) {
    alert('Error regenerating category: ' + e);
    setStatus('Category regeneration failed', 'error', 4000);
  } finally {
    if (regenBtn) {
      regenBtn.disabled = false;
      regenBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
    }
  }
}

async function banAndReplaceCategory(categoryIdx) {
  const categoryEl = document.querySelector(`.category[data-category-index="${categoryIdx}"]`);
  if (!categoryEl) return;

  const nameInput = categoryEl.querySelector('.category-name-input');
  const categoryName = (nameInput && nameInput.value.trim()) || '';

  if (!categoryName) {
    alert('No category name to ban.');
    return;
  }

  try {
    const r = await fetch('/api/banned-categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category: categoryName })
    });
    const res = await r.json();
    if (!r.ok || !res.ok) {
      throw new Error(res.error || 'Failed to ban category');
    }
    setStatus(`Category banned: "${categoryName}"`, 'info', 3000);
    await regenerateCategoryForIndex(categoryIdx, { usePromptIfEmpty: false });
  } catch (e) {
    alert('Failed to ban category: ' + e);
    setStatus('Failed to ban category', 'error', 4000);
  }
}

document.getElementById('saveBtn').addEventListener('click', () => {
  save();
});

// Initialize export button state
updateExportButtonState();

// Load on page load
setStatus('Ready', 'info', 2000);
load();
