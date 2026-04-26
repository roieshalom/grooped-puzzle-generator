let puzzles = [];
let currentIndex = 0;
let lastSavedState = null; // Store the last saved puzzle state
let hasUnsavedChanges = false;

// ── Auth helpers ────────────────────────────────────────────────────────────
// Token is stored in localStorage and sent as X-Editor-Token on every mutation.
// The page is publicly readable without any token.

function getAuthToken()      { return localStorage.getItem('editor-token') || ''; }
function setAuthToken(token) { localStorage.setItem('editor-token', token); }
function clearAuthToken()    { localStorage.removeItem('editor-token'); }

// Draft persistence in localStorage (cross-session, same device)
const DRAFT_KEY = 'grooped-draft-puzzle';
function saveDraftLocally(puzzle) {
  try { localStorage.setItem(DRAFT_KEY, JSON.stringify(puzzle)); } catch(e) {}
}
function loadDraftLocally() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch(e) { return null; }
}

// ── Read-only mode ──────────────────────────────────────────────────────────

let _readOnly = true; // default until we confirm we have a valid token

function setReadOnly(readOnly) {
  _readOnly = readOnly;

  // Toggle all editable inputs
  document.querySelectorAll('.word-input, .category-name-input').forEach(inp => {
    inp.disabled = readOnly;
  });

  // Toggle all action buttons
  ['saveBtn', 'reloadBtn', 'generateBtn', 'exportBtn'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = readOnly;
  });

  // Toggle per-category buttons
  document.querySelectorAll('.regenerate-btn, .ban-btn').forEach(btn => {
    btn.disabled = readOnly;
  });

  // Update lock button appearance
  const lockBtn = document.getElementById('lockBtn');
  if (lockBtn) {
    lockBtn.textContent = readOnly ? '🔒' : '🔓';
    lockBtn.title = readOnly ? 'Unlock editor' : 'Lock editor';
    lockBtn.classList.toggle('unlocked', !readOnly);
  }

  // Date row: always visible; swap picker ↔ mask based on lock state
  const dateRow = document.getElementById('dateRow');
  if (dateRow) dateRow.style.display = 'flex';
  const picker = document.getElementById('publishDatePicker');
  if (picker) picker.style.display = readOnly ? 'none' : '';
  const dateMask = document.getElementById('dateMask');
  if (dateMask) dateMask.style.display = readOnly ? '' : 'none';

  // Hide auth panel when unlocking
  if (!readOnly) {
    const panel = document.getElementById('authPanel');
    if (panel) panel.classList.remove('show');
    const inp = document.getElementById('inlinePasswordInput');
    if (inp) inp.value = '';
  }

  updateExportButtonState();
}

// Drop-in replacement for fetch() that:
//   1. Adds the auth token header on mutating requests
//   2. On 401: clears token, switches to read-only, shows a message
async function apiFetch(url, options = {}) {
  const token = getAuthToken();
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers['X-Editor-Token'] = token;

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    clearAuthToken();
    setReadOnly(true);
    setStatus('Session expired — unlock to edit', 'error', 5000);
    throw new Error('Not authenticated');
  }
  return response;
}

// ── Inline unlock logic ──────────────────────────────────────────────────────

async function attemptUnlock(password) {
  if (!password) return;
  const btn = document.getElementById('inlineUnlockBtn');
  if (btn) btn.disabled = true;

  try {
    const r = await fetch('/api/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const res = await r.json();
    if (res.ok) {
      setAuthToken(res.token);
      setReadOnly(false);
      setStatus('Editor unlocked ✓', 'success', 3000);
    } else {
      setStatus('Wrong password', 'error', 3000);
      const inp = document.getElementById('inlinePasswordInput');
      if (inp) { inp.value = ''; inp.focus(); }
    }
  } catch (e) {
    setStatus('Login failed — check your connection', 'error', 3000);
  } finally {
    if (btn) btn.disabled = false;
  }
}

const difficultyToColor = ['purple', 'green', 'blue', 'orange'];
const colorToDifficulty = {
  purple: 'yellow',
  green: 'green',
  blue: 'blue',
  orange: 'purple',
};

// Inline status / message helper
function setStatus(text, type = 'info', duration = 3000) {
  const box = document.getElementById('messageBox');
  if (!box) return;

  box.textContent = text;
  box.style.display = 'flex';

  box.classList.remove('success', 'error', 'info');
  if (type) box.classList.add(type);

  clearTimeout(setStatus._timeout);
  if (duration > 0) {
    setStatus._timeout = setTimeout(() => {
      box.style.display = 'none';
    }, duration);
  }
}

// Full‑puzzle overlay helper
function setPuzzleLoading(loading, labelText = null) {
  const overlay = document.getElementById('puzzleOverlay');
  if (!overlay) return;
  const label = overlay.querySelector('.overlay-label');
  if (label && labelText) {
    label.textContent = labelText;
  }
  overlay.classList.toggle('show', loading);
}

// Per‑category overlay helper
function setCategoryLoading(categoryIdx, loading, labelText = null) {
  const categoryEl = document.querySelector(
    `.category[data-category-index="${categoryIdx}"]`
  );
  if (!categoryEl) return;
  const overlay = categoryEl.querySelector('.category-overlay');
  if (!overlay) return;
  const label = overlay.querySelector('.overlay-label');
  if (label && labelText) {
    label.textContent = labelText;
  }
  overlay.classList.toggle('show', loading);
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
  exportBtn.disabled = _readOnly || hasUnsavedChanges || puzzles.length === 0 || !puzzles[0];
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

  const puzzle = puzzles[0]; // Always use first puzzle
  if (!puzzle) return;

  const categories = puzzle.categories || [];

  // Map difficulty to color based on position (default mapping)
  categories.forEach((cat, idx) => {
    const diff = cat.difficulty || 'yellow';
    const defaultColor = difficultyToColor[idx] || 'purple';
    // Find which color this difficulty maps to
    const color =
      Object.keys(colorToDifficulty).find(
        (c) => colorToDifficulty[c] === diff
      ) || defaultColor;

    const categoryEl = document.querySelector(
      `.category[data-category-index="${idx}"]`
    );
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
        const wordInput = categoryEl.querySelector(
          `.word-input[data-word="${wordIdx}"]`
        );
        if (wordInput) wordInput.value = word || '';
      });
    }
  });

  // Clear categories that don't have data
  for (let i = categories.length; i < 4; i++) {
    const categoryEl = document.querySelector(
      `.category[data-category-index="${i}"]`
    );
    if (categoryEl) {
      categoryEl.querySelector('.category-name-input').value = '';
      categoryEl.querySelectorAll('.word-input').forEach(
        (inp) => (inp.value = '')
      );
    }
  }

  // Show validation errors and highlight duplicate words
  showValidationErrors(puzzle);
  highlightDuplicateWords(puzzle);

  // Show brief design notes under the categories
  const notesEl = document.getElementById('designNotes');
  if (notesEl) {
    const decoys = puzzle.decoys || [];
    const otherTrick = puzzle.other_trick || puzzle.design_notes || '';

    if (decoys.length === 0 && !otherTrick) {
      notesEl.textContent = '';
      notesEl.style.display = 'none';
    } else {
      const lines = [];

      if (decoys.length > 0) {
        lines.push('Decoys:');
        decoys.forEach((d) => {
          if (!d || !d.word) return;
          const a = d.category_a || '?';
          const b = d.category_b || '?';
          lines.push(`${d.word}: ${a} / ${b}`);
        });
      }

      if (otherTrick) {
        if (lines.length > 0) lines.push('');
        lines.push(`Other trick: ${otherTrick}`);
      }

      notesEl.textContent = lines.join('\n');
      notesEl.style.whiteSpace = 'pre-line';
      notesEl.style.display = 'block';
    }
  }

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
    errorsDiv.innerHTML =
      '<strong>⚠️ Validation Errors:</strong><ul>' +
      validation.errors.map((e) => `<li>${e}</li>`).join('') +
      '</ul>';
  } else {
    errorsDiv.style.display = 'none';
  }
}

function highlightDuplicateWords(puzzle) {
  const validation = puzzle._validation || { duplicate_words: [] };
  const duplicateWords = new Set(
    (validation.duplicate_words || []).map((w) => w.toUpperCase())
  );

  // Clear all duplicate highlighting first
  document.querySelectorAll('.word-input').forEach((inp) => {
    inp.classList.remove('duplicate');
  });

  // Highlight duplicate words
  document.querySelectorAll('.word-input').forEach((inp) => {
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
    ...existingPuzzle, // Preserve existing fields
    language: existingPuzzle.language || 'en',
    categories: [], // Will rebuild from form
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
    const categoryEl = document.querySelector(
      `.category[data-category-index="${i}"]`
    );
    if (categoryEl) {
      const nameInput = categoryEl.querySelector('.category-name-input');
      const wordInputs = categoryEl.querySelectorAll('.word-input');
      const name = nameInput.value.trim();
      const words = Array.from(wordInputs)
        .map((inp) => inp.value.trim().toUpperCase())
        .filter((w) => w);
      const currentColor =
        categoryEl.dataset.color || difficultyToColor[i] || 'purple';

      // Always add category if it has either name or words (or both)
      if (name || words.length > 0) {
        puzzle.categories.push({
          name: name,
          words:
            words.length === 4
              ? words
              : words.concat(Array(4 - words.length).fill('')),
          difficulty: colorToDifficulty[currentColor] || 'yellow',
        });
      }
    }
  }

  return puzzle;
}

function hasWithinPuzzleDuplicates(puzzle) {
  const seen = new Set();
  const dups = new Set();
  (puzzle.categories || []).forEach((cat) => {
    (cat.words || []).forEach((w) => {
      const word = (w || '').toUpperCase().trim();
      if (!word) return;
      if (seen.has(word)) dups.add(word);
      seen.add(word);
    });
  });
  return Array.from(dups);
}

async function load() {
  setStatus('Loading...');
  try {
    // GET /api/puzzle is public — no auth token needed
    const r = await fetch('/api/puzzle');
    if (!r.ok) throw new Error('Failed to load');
    const res = await r.json();

    if (Array.isArray(res) && res.length > 0 && res[0]) {
      puzzles = [res[0]];
    } else {
      // Server has no draft — fall back to localStorage
      const local = loadDraftLocally();
      puzzles = local ? [local] : [];
    }

    if (puzzles.length === 0) {
      setStatus('No puzzle yet — hit Generate', 'info', 3000);
      updateExportButtonState();
      return;
    }

    currentIndex = 0;
    updateUI();
    setStatus('Puzzle loaded', 'info', 2000);
  } catch (e) {
    setStatus('Load failed', 'error', 4000);
  }
}

async function save() {
  setStatus('Saving...');
  setButtonLoading('saveBtn', true);
  try {
    const puzzle = collectData();
    puzzles[0] = puzzle;

    const r = await apiFetch('/api/puzzle', {
      method: 'POST',
      body: JSON.stringify(puzzle),
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error || JSON.stringify(res));

    // Normalize: backend returns { ok: true, puzzle: { ... } }
    if (res.puzzle) {
      puzzles = [res.puzzle];
    }

    showValidationErrors(puzzles[0]);
    highlightDuplicateWords(puzzles[0]);

    // Persist locally so Revert can restore this exact state
    saveDraftLocally(puzzles[0]);

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

    const picker = document.getElementById('publishDatePicker');
    if (picker && picker.value) puzzle.publish_date = picker.value; // YYYY-MM-DD

    const r = await apiFetch('/api/export', {
      method: 'POST',
      body: JSON.stringify(puzzle),
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error || JSON.stringify(res));

    setButtonSuccess('exportBtn');
    setStatus('Puzzle exported', 'success', 4000);

    await load();
    refreshNextDate();
  } catch (e) {
    setStatus('Export failed', 'error', 4000);
    setButtonLoading('exportBtn', false);
    alert('Export failed: ' + e);
  }
});

document.getElementById('generateBtn').addEventListener('click', async () => {
  console.log('GENERATE CLICKED');
  setButtonLoading('generateBtn', true);
  setPuzzleLoading(true, 'Generating puzzle…'); // show full‑puzzle overlay
  try {
    const r = await apiFetch('/api/generate-puzzle', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    const res = await r.json();
    if (!r.ok) {
      throw new Error(res.error || JSON.stringify(res));
    }

    if (!res || !res.categories) {
      throw new Error('Invalid puzzle from generator');
    }

    // Assign 4 unique colors: yellow, green, blue, purple
    const uniqueColors = ['yellow', 'green', 'blue', 'purple'];
    res.categories.forEach((cat, index) => {
      cat.difficulty = uniqueColors[index % uniqueColors.length];
    });

    // Remove duplicate category names
    const seenNames = new Set();
    res.categories = res.categories.filter((cat) => {
      const name = cat.name || '';
      if (seenNames.has(name)) return false;
      seenNames.add(name);
      return true;
    });

    // Show puzzle in UI
    puzzles = [res];
    currentIndex = 0;
    updateUI();
    setButtonSuccess('generateBtn');
    setStatus('New puzzle generated', 'success', 3000);

    // Trigger backend validation so duplicate words show right away
    try {
      await save();
    } catch (e) {
      // ignore here; errors already surfaced in save()
    }
  } catch (e) {
    setStatus('Generate failed', 'error', 4000);
    alert('Failed to generate puzzle: ' + e);
  } finally {
    setButtonLoading('generateBtn', false);
    setPuzzleLoading(false); // hide full‑puzzle overlay
  }
});

// Track input changes for unsaved changes detection
document
  .querySelectorAll('.word-input, .category-name-input')
  .forEach((inp) => {
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
document.querySelectorAll('.color-square-wrapper').forEach((wrapper) => {
  wrapper.addEventListener('click', (e) => {
    e.stopPropagation();
    const dropdown = wrapper.querySelector('.color-dropdown');
    document.querySelectorAll('.color-dropdown').forEach((d) => {
      if (d !== dropdown) d.classList.remove('show');
    });
    dropdown.classList.toggle('show');
  });
});

// Color option selection handlers
document.querySelectorAll('.color-option').forEach((option) => {
  option.addEventListener('click', (e) => {
    e.stopPropagation();
    const newColor = option.dataset.color;
    const categoryEl = option.closest('.category');
    const oldColor = categoryEl.dataset.color;

    if (newColor !== oldColor) {
      const otherCategory = document.querySelector(
        `.category[data-color="${newColor}"]`
      );
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

    document.querySelectorAll('.color-dropdown').forEach((d) =>
      d.classList.remove('show')
    );
    checkUnsavedChanges();
  });
});

// Close dropdowns when clicking outside
document.addEventListener('click', () => {
  document
    .querySelectorAll('.color-dropdown')
    .forEach((d) => d.classList.remove('show'));
});

// Regenerate category buttons
document.querySelectorAll('.regenerate-btn').forEach((btn) => {
  btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const categoryIdx = parseInt(btn.dataset.category);
    await regenerateCategoryForIndex(categoryIdx, { usePromptIfEmpty: true });
  });
});

// Skip & ban buttons
document.querySelectorAll('.ban-btn').forEach((btn) => {
  btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const categoryIdx = parseInt(btn.dataset.category);
    await banAndReplaceCategory(categoryIdx);
  });
});

async function regenerateCategoryForIndex(categoryIdx, options = {}) {
  const { usePromptIfEmpty } = options;
  const categoryEl = document.querySelector(
    `.category[data-category-index="${categoryIdx}"]`
  );
  if (!categoryEl) return;

  const currentColor = categoryEl.dataset.color;
  const difficultyMap = {
    purple: 'easy',
    green: 'medium',
    blue: 'medium',
    orange: 'hard',
  };
  const difficulty = difficultyMap[currentColor] || 'medium';

  const nameInput = categoryEl.querySelector('.category-name-input');
  const wordInputs = categoryEl.querySelectorAll('.word-input');

  const allWordsEmpty = Array.from(wordInputs).every(
    (inp) => !inp.value.trim()
  );
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

  // Overlay label + show overlay (no in‑progress banner)
  const labelText =
    allWordsEmpty && categoryName && usePromptIfEmpty
      ? 'Generating words…'
      : 'Regenerating…';
  setCategoryLoading(categoryIdx, true, labelText);

  try {
    const r = await apiFetch(apiUrl, { method: 'GET' });
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

      // fire input events so validation / dirty state updates
      wordInputs.forEach((inp) => {
        inp.dispatchEvent(new Event('input'));
      });
      nameInput.dispatchEvent(new Event('input'));
    } else {
      const error = await r.json();
      alert(
        'Failed to regenerate category: ' +
          (error.error || 'Unknown error')
      );
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
    setCategoryLoading(categoryIdx, false);
  }
}

async function banAndReplaceCategory(categoryIdx) {
  const categoryEl = document.querySelector(
    `.category[data-category-index="${categoryIdx}"]`
  );
  if (!categoryEl) return;

  const nameInput = categoryEl.querySelector('.category-name-input');
  const categoryName = (nameInput && nameInput.value.trim()) || '';

  if (!categoryName) {
    alert('No category name to ban.');
    return;
  }

  // Show overlay with banning text
  setCategoryLoading(categoryIdx, true, 'Banning & regenerating…');

  try {
    const r = await apiFetch('/api/banned-categories', {
      method: 'POST',
      body: JSON.stringify({ category: categoryName }),
    });
    const res = await r.json();
    if (!r.ok || !res.ok) {
      throw new Error(res.error || 'Failed to ban category');
    }
    // No noisy info status here; overlay communicates progress
    await regenerateCategoryForIndex(categoryIdx, { usePromptIfEmpty: false });
  } catch (e) {
    alert('Failed to ban category: ' + e);
    setStatus('Failed to ban category', 'error', 4000);
  } finally {
    // regenerateCategoryForIndex hides overlay in its finally,
    // but ensure it is not stuck if regenerate fails early
    setCategoryLoading(categoryIdx, false);
  }
}

document.getElementById('saveBtn').addEventListener('click', () => {
  save();
});

// Initialize export button state
updateExportButtonState();

// ── Lock button wiring ──────────────────────────────────────────────────────

document.getElementById('lockBtn').addEventListener('click', () => {
  if (!_readOnly) {
    // Currently unlocked → lock
    clearAuthToken();
    setReadOnly(true);
    setStatus('Editor locked', 'info', 2000);
  } else {
    // Currently locked → toggle password panel
    const panel = document.getElementById('authPanel');
    const isOpen = panel.classList.contains('show');
    panel.classList.toggle('show', !isOpen);
    if (!isOpen) {
      const inp = document.getElementById('inlinePasswordInput');
      if (inp) setTimeout(() => inp.focus(), 50);
    }
  }
});

document.getElementById('inlineUnlockBtn').addEventListener('click', () => {
  const inp = document.getElementById('inlinePasswordInput');
  if (inp) attemptUnlock(inp.value);
});

document.getElementById('inlinePasswordInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    attemptUnlock(e.target.value);
  } else if (e.key === 'Escape') {
    document.getElementById('authPanel').classList.remove('show');
  }
});

// ── Publish date helpers ──────────────────────────────────────────────────────
// Convert "26.4.2026" (server format) → "2026-04-26" (date input value)
function puzzleDateToIso(d) {
  const [day, month, year] = d.split('.');
  return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
}

// ── Next puzzle date ─────────────────────────────────────────────────────────
async function refreshNextDate() {
  // Retry once after a short delay in case of a cold-start timeout
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      if (attempt > 0) await new Promise(r => setTimeout(r, 2000));
      // GET /api/next-date is public — no auth token needed
      const r = await fetch('/api/next-date');
      if (!r.ok) continue;
      const { date } = await r.json();
      if (!date) continue;
      const iso = puzzleDateToIso(date);
      const picker = document.getElementById('publishDatePicker');
      if (picker) {
        picker.min = iso;
        // Only set default if nothing selected yet or current value is in the past
        if (!picker.value || picker.value < iso) picker.value = iso;
      }
      return;
    } catch (e) {
      // try again on next iteration
    }
  }
}

// ── Startup ─────────────────────────────────────────────────────────────────
// The page is publicly viewable — load the puzzle without auth.
// If a token is already stored, start in edit mode; otherwise read-only.
// Run sequentially so load() warms the Vercel function before the date fetch.
async function startup() {
  setStatus('Ready', 'info', 2000);
  setReadOnly(!getAuthToken());
  // Run in parallel — date label and puzzle content load concurrently
  await Promise.all([load(), refreshNextDate()]);
}
startup();
