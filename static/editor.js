let puzzles = [];
let currentIndex = 0;
let lastSavedState = null;
let hasUnsavedChanges = false;
let _viewingPast = false;   // true while a past puzzle is displayed
let _savedDraft  = null;    // draft stashed before entering past-view

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

// Replace visible input values with ● circles when locked.
// Diagonal pattern: category N keeps word N visible, all others masked.
function _applyMaskedValues() {
  // Mask category name inputs + diagonal word inputs
  document.querySelectorAll('.category').forEach(catEl => {
    const catIdx = parseInt(catEl.dataset.categoryIndex, 10);
    const nameInput = catEl.querySelector('.category-name-input');
    if (nameInput) {
      nameInput.value = '●●●●●●●●●●●●●●';
      nameInput.classList.add('masked');
    }
    catEl.querySelectorAll('.word-input').forEach((inp, idx) => {
      if (idx !== catIdx) {
        inp.value = '●●●●●●';
        inp.classList.add('masked');
      }
    });
  });

  // Mask design notes: keep section titles ("Decoys:", "Other trick:"),
  // replace all values (words / category names / hint text) with circles
  const notesEl = document.getElementById('designNotes');
  if (notesEl && notesEl.style.display !== 'none') {
    const puzzle = puzzles.length > 0 ? puzzles[0] : null;
    if (puzzle) {
      const decoys = puzzle.decoys || [];
      const otherTrick = puzzle.other_trick || puzzle.design_notes || '';
      const parts = [];
      if (decoys.length > 0) {
        parts.push('Decoys:');
        decoys.forEach(d => {
          if (!d || !d.word) return;
          parts.push('<span class="masked">●●●●●●: ●●●●●●●●●● / ●●●●●●●●●●</span>');
        });
      }
      if (otherTrick) {
        if (parts.length > 0) parts.push('');
        parts.push('Other trick: <span class="masked">●●●●●●●●●●●●●●●●●●●●</span>');
      }
      notesEl.innerHTML = parts.join('\n');
    }
  }
}

function setReadOnly(readOnly) {
  _readOnly = readOnly;

  // When locking, exit past-view mode cleanly
  if (readOnly && _viewingPast) {
    _viewingPast = false;
    if (_savedDraft) { puzzles = [_savedDraft]; _savedDraft = null; }
    const picker = document.getElementById('publishDatePicker');
    _pickerSetPastMode(picker, false);
  }

  // disabled = locked OR currently viewing a past snapshot
  const disabled = readOnly || _viewingPast;

  // Toggle all editable inputs
  document.querySelectorAll('.word-input, .category-name-input').forEach(inp => {
    inp.disabled = disabled;
  });

  // Toggle all action buttons
  ['saveBtn', 'reloadBtn', 'generateBtn', 'exportBtn'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = disabled;
  });

  // Toggle per-category buttons
  document.querySelectorAll('.regenerate-btn, .ban-btn').forEach(btn => {
    btn.disabled = disabled;
  });

  // Update lock button appearance
  const lockBtn = document.getElementById('lockBtn');
  if (lockBtn) {
    lockBtn.textContent = readOnly ? '🔒' : '🔓';
    lockBtn.title = readOnly ? 'Unlock editor' : 'Lock editor';
    lockBtn.classList.toggle('unlocked', !readOnly);
  }

  // View-mode banner: visible only when locked
  const viewModeBanner = document.getElementById('viewModeBanner');
  if (viewModeBanner) viewModeBanner.style.display = readOnly ? '' : 'none';

  // Message area: hide when locked (no notifications in read-only view)
  const messageArea = document.getElementById('messageArea');
  if (messageArea) messageArea.style.display = readOnly ? 'none' : '';

  // Color selectors: disable interaction when locked
  document.querySelectorAll('.color-square-wrapper').forEach(w => {
    w.style.pointerEvents = readOnly ? 'none' : '';
    w.style.opacity = readOnly ? '0.6' : '';
    w.style.cursor = readOnly ? 'default' : '';
  });

  // Design notes box matches locked/unlocked word-input appearance
  const designNotes = document.getElementById('designNotes');
  if (designNotes) designNotes.classList.toggle('locked', readOnly);

  // Date row: always visible; swap picker ↔ mask based on lock state
  const dateRow = document.getElementById('dateRow');
  if (dateRow) dateRow.style.display = 'flex';
  // .flatpickr-wrapper has display:inline-block !important in CSS, so hiding the wrapper
  // doesn't work — target the visible altInput directly instead.
  const pickerVisible = (_flatpickr && _flatpickr.altInput)
    || document.getElementById('publishDatePicker');
  if (pickerVisible) pickerVisible.style.display = readOnly ? 'none' : '';
  if (readOnly && _flatpickr) _flatpickr.close();
  const dateMask = document.getElementById('dateMask');
  if (dateMask) {
    dateMask.textContent = buildDateMask();
    dateMask.style.display = readOnly ? '' : 'none';
  }

  // Hide auth panel when unlocking
  if (!readOnly) {
    const panel = document.getElementById('authPanel');
    if (panel) panel.classList.remove('show');
    const inp = document.getElementById('inlinePasswordInput');
    if (inp) inp.value = '';
  }

  // Mask category names + words 1-3; reveal word 0 only (locked view)
  if (readOnly) {
    _applyMaskedValues();
  } else {
    // Remove masked class from all inputs (values restored below by updateUI)
    document.querySelectorAll('.word-input.masked, .category-name-input.masked').forEach(inp => {
      inp.classList.remove('masked');
    });
    updateUI();
  }

  updateExportButtonState();
  updateMechanicLabels();
  renderMechanicBar();
}

// Enter/exit past-puzzle snapshot mode
function setViewingPast(viewing) {
  _viewingPast = viewing;
  const picker  = document.getElementById('publishDatePicker');
  const disabled = viewing; // when exiting, setReadOnly will re-apply correct state

  const jumpBtn = document.getElementById('jumpToNextBtn');
  if (viewing) {
    document.querySelectorAll('.word-input, .category-name-input').forEach(inp => { inp.disabled = true; });
    document.querySelectorAll('.regenerate-btn, .ban-btn').forEach(btn => { btn.disabled = true; });
    ['saveBtn', 'reloadBtn', 'generateBtn', 'exportBtn'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.disabled = true;
    });
    _pickerSetPastMode(picker, true);
    if (jumpBtn) jumpBtn.style.display = '';
  } else {
    // Restore whatever the current lock state demands
    setReadOnly(_readOnly);
    _pickerSetPastMode(picker, false);
    if (jumpBtn) jumpBtn.style.display = 'none';
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
  }
}

const difficultyToColor = ['yellow', 'coral', 'mint', 'sky'];
const colorToDifficulty = {
  yellow: 'yellow',
  coral:  'green',
  mint:   'blue',
  sky:    'purple',
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
  exportBtn.disabled = _readOnly || _viewingPast || hasUnsavedChanges || puzzles.length === 0 || !puzzles[0];
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
  updateMechanicLabels();

  // Re-apply masking if still in locked view (e.g. initial load while locked)
  if (_readOnly) _applyMaskedValues();
}

// ── Mechanic labels (per-category) ──────────────────────────────────────────

function updateMechanicLabels() {
  const puzzle = puzzles.length > 0 ? puzzles[0] : null;
  const categories = puzzle ? (puzzle.categories || []) : [];
  for (let i = 0; i < 4; i++) {
    const el = document.getElementById(`mechanic-label-${i}`);
    if (!el) continue;
    const cat = categories[i];
    const mechanic = cat && cat.mechanic;
    const tier = cat && (cat.tier || null);
    if (!_readOnly && mechanic) {
      el.textContent = tier ? `${mechanic} · T${tier}` : mechanic;
      el.style.display = '';
    } else {
      el.style.display = 'none';
    }
  }
}

// ── Mechanic usage bar ───────────────────────────────────────────────────────

let _mechBarContent = null; // cache rendered HTML

const _TIER2_MECHANICS = [
  'THINGS_THAT_VERB','CAN_BE_VERBED','SHARED_HIDDEN_PROPERTY','METAPHOR_SUBSTITUTES',
  'WAYS_TO_VERB','IDIOM_COMPLETION','ORDERED_SET_MEMBER','WORKS_BY_ONE_MAKER','CHARACTERS_IN_ONE_WORK',
];
const _TIER3_MECHANICS = [
  'HIDDEN_WORD_INSIDE','HIDDEN_WORD_AT_START','HIDDEN_WORD_AT_END',
  'HOMOPHONE_OF_LETTER','HOMOPHONE_OF_NUMBER','HOMOPHONE_PAIRS',
  'COMPOUND_BOTH_WAYS','ADD_LETTER','DROP_LETTER',
  'EPONYMS','CROSS_LANGUAGE','ABBREVIATION_EXPANSION',
];

async function renderMechanicBar(forceRefresh = false) {
  const bar = document.getElementById('mechanicBar');
  if (!bar) return;

  if (_readOnly) {
    // Show bar in locked state: collapsed + grayed.
    // If content already cached, render it; otherwise fetch stats now.
    bar.style.display = '';
    bar.classList.add('mb-locked');
    if (_mechBarContent !== null) {
      bar.innerHTML = _mechBarContent;
      _applyMbCollapsed(bar, true, false);
    } else {
      // Fall through to fetch — will re-apply locked state after render
    }
  }

  if (_readOnly && _mechBarContent !== null) return;
  if (!_readOnly) bar.classList.remove('mb-locked');

  if (!forceRefresh && _mechBarContent !== null) {
    bar.innerHTML = _mechBarContent;
    bar.style.display = '';
    return;
  }

  bar.style.display = '';
  bar.innerHTML = '<span class="mb-loading">Loading mechanic stats…</span>';

  let data;
  try {
    const r = await fetch('/api/mechanic-stats');
    data = await r.json();
  } catch (e) {
    bar.innerHTML = '<span class="mb-loading">Could not load mechanic stats.</span>';
    return;
  }

  const { tagged_count, window_size, cat_mechanics, all_mechanics } = data;
  const total = cat_mechanics.length;

  // Count by tier
  const tierCounts = { 1: 0, 2: 0, 3: 0, 4: 0 };
  cat_mechanics.forEach(({ tier }) => { if (tier) tierCounts[tier] = (tierCounts[tier] || 0) + 1; });

  const tierColors = { 1: '#74bdee', 2: '#8b5cf6', 3: '#f97316', 4: '#ec4899' };
  const tierLabels = { 1: 'Tier 1', 2: 'Tier 2', 3: 'Tier 3', 4: 'Tier 4' };

  let rowHtml = '<div class="mb-row">';
  [1, 2, 3, 4].forEach(t => {
    const count = tierCounts[t] || 0;
    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
    rowHtml += `<div class="mb-tier-item">
      <span class="mb-tier-label" style="color:${tierColors[t]}">${tierLabels[t]}</span>
      <div class="mb-track"><div class="mb-fill" style="width:${pct}%;background:${tierColors[t]}"></div></div>
      <span class="mb-pct">${pct}% (${count})</span>
    </div>`;
  });
  rowHtml += '</div>';

  // Underused Tier 2 & 3 mechanics (used 0 times in window)
  const underused2 = _TIER2_MECHANICS.filter(m => !(all_mechanics[m] > 0));
  const underused3 = _TIER3_MECHANICS.filter(m => !(all_mechanics[m] > 0));
  let detailHtml = '';
  if (underused2.length > 0 || underused3.length > 0) {
    detailHtml += '<div class="mb-underused"><strong>Unused in window:</strong> ';
    const items = [
      ...underused2.map(m => `<span class="mb-tag mb-t2">${m}</span>`),
      ...underused3.map(m => `<span class="mb-tag mb-t3">${m}</span>`),
    ];
    detailHtml += items.join(' ') + '</div>';
  }
  if (tagged_count < window_size) {
    detailHtml += `<div class="mb-warmup">⚠ Only ${tagged_count} of ${window_size} window puzzles are tagged. Stats will improve as more puzzles are exported with mechanic data.</div>`;
  }

  const headingText = `Mechanic usage — last ${tagged_count} tagged puzzles (${total} categories)`;
  const html = `
    <div class="mb-toggle-row" id="mbToggleRow">
      <span class="mb-heading">${headingText}</span>
      <span class="mb-chevron" id="mbChevron">▲</span>
    </div>
    ${rowHtml}
    <div class="mb-detail" id="mbDetail">${detailHtml}</div>
  `;

  _mechBarContent = html;
  bar.innerHTML = html;

  if (_readOnly) {
    // Locked view: force collapsed + grayed, no toggle interaction
    bar.classList.add('mb-locked');
    _applyMbCollapsed(bar, true, false);
    return;
  }

  // Apply persisted collapsed state
  const collapsed = localStorage.getItem('mb-collapsed') === '1';
  if (collapsed) _applyMbCollapsed(bar, true, false);

  // Wire up toggle
  document.getElementById('mbToggleRow').addEventListener('click', () => {
    const isCollapsed = bar.classList.contains('mb-collapsed');
    _applyMbCollapsed(bar, !isCollapsed, true);
  });
}

function _applyMbCollapsed(bar, collapse, persist) {
  const detail = document.getElementById('mbDetail');
  const chevron = document.getElementById('mbChevron');
  if (collapse) {
    bar.classList.add('mb-collapsed');
    if (detail) detail.style.display = 'none';
    if (chevron) chevron.textContent = '▼';
  } else {
    bar.classList.remove('mb-collapsed');
    if (detail) detail.style.display = '';
    if (chevron) chevron.textContent = '▲';
  }
  if (persist) localStorage.setItem('mb-collapsed', collapse ? '1' : '0');
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
        const existingCat = (existingPuzzle.categories || [])[i] || {};
        puzzle.categories.push({
          name: name,
          words:
            words.length === 4
              ? words
              : words.concat(Array(4 - words.length).fill('')),
          difficulty: colorToDifficulty[currentColor] || 'yellow',
          ...(existingCat.mechanic ? { mechanic: existingCat.mechanic } : {}),
          ...(existingCat.tier     ? { tier:     existingCat.tier     } : {}),
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
    setStatus('Puzzle exported — generating next…', 'success', 4000);

    refreshNextDate();
    _mechBarContent = null;
    renderMechanicBar(true);
    await generateAndSave();
  } catch (e) {
    setStatus('Export failed', 'error', 4000);
    setButtonLoading('exportBtn', false);
    alert('Export failed: ' + e);
  }
});

async function generateAndSave() {
  setButtonLoading('generateBtn', true);
  setPuzzleLoading(true, 'Generating puzzle…');
  try {
    const r = await apiFetch('/api/generate-puzzle', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error || JSON.stringify(res));
    if (!res || !res.categories) throw new Error('Invalid puzzle from generator');

    // Assign 4 unique colors in order
    const uniqueColors = ['yellow', 'coral', 'mint', 'sky'];
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
    setStatus('New puzzle generated — saving…', 'success', 3000);

    // Save immediately
    try {
      await save();
    } catch (e) {
      // ignore; errors already surfaced in save()
    }
  } catch (e) {
    setStatus('Generate failed', 'error', 4000);
    alert('Failed to generate puzzle: ' + e);
  } finally {
    setButtonLoading('generateBtn', false);
    setPuzzleLoading(false);
  }
}

document.getElementById('generateBtn').addEventListener('click', () => {
  console.log('GENERATE CLICKED');
  generateAndSave();
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
    if (_readOnly) return;
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
    if (_readOnly) return;
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
    yellow: 'easy',
    coral:  'medium',
    mint:   'medium',
    sky:    'hard',
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

      // Update mechanic + tier on the in-memory puzzle so labels refresh
      if (puzzles.length > 0 && puzzles[0] && puzzles[0].categories) {
        const memCat = puzzles[0].categories[categoryIdx];
        if (memCat) {
          if (category.mechanic) {
            memCat.mechanic = category.mechanic;
            memCat.tier     = category.tier || null;
          } else {
            delete memCat.mechanic;
            delete memCat.tier;
          }
        }
      }
      updateMechanicLabels();

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

// Build the masked date string shown when locked: ●●/●●/2026
function buildDateMask() {
  return '●●/●●/2026';
}

// ── Flatpickr date picker ─────────────────────────────────────────────────────

let _flatpickr      = null;
let _publishedDates = new Set(); // YYYY-MM-DD strings fetched from /api/published-dates
let _nextFreeDate   = null;      // YYYY-MM-DD string — the next unpublished slot

// Apply/remove past-mode class to the visible picker input (altInput when available)
function _pickerSetPastMode(picker, on) {
  const visible = (_flatpickr && _flatpickr.altInput) || picker;
  if (visible) visible.classList.toggle('past-mode', on);
}

function initDatePicker() {
  const pickerEl = document.getElementById('publishDatePicker');
  if (!pickerEl || typeof flatpickr === 'undefined') return;

  // Use local date, not UTC — toISOString() shifts midnight-local back by one
  // day for any timezone east of UTC, causing all calendar dots to land on
  // the wrong cell.
  const localIso = d => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };
  const todayIso = localIso(new Date());

  _flatpickr = flatpickr(pickerEl, {
    dateFormat:    'Y-m-d',
    altInput:      true,
    altFormat:     'd/m/Y',           // display format: DD/MM/YYYY
    altInputClass: 'publish-date-picker', // inherits all our input styles
    minDate:       `${new Date().getFullYear()}-01-01`,
    disableMobile: true,

    onDayCreate(dObj, dStr, fp, dayElem) {
      // Leave prev/next-month overflow days unstyled
      if (dayElem.classList.contains('prevMonthDay') ||
          dayElem.classList.contains('nextMonthDay')) return;

      const iso       = localIso(dayElem.dateObj);
      const hasPuzzle = _publishedDates.has(iso);

      if (hasPuzzle && iso < todayIso) {
        dayElem.classList.add('fp-past-published');
      } else if (hasPuzzle) {
        dayElem.classList.add('fp-upcoming');
      }
      // else: no puzzle — white (default)

      // Orange dot marks the next free slot regardless of selection state
      if (_nextFreeDate && iso === _nextFreeDate) {
        dayElem.classList.add('fp-next-free');
      }
    },

    onChange(selectedDates, dateStr) {
      if (dateStr) handleDatePickerChange(dateStr);
    },
  });
}

// Fetch published dates in the background; re-render picker if open.
async function loadPublishedDates() {
  try {
    const r = await fetch('/api/published-dates');
    const data = await r.json();
    _publishedDates = new Set(data.dates || []);
    // Re-render the calendar so day colours and orange dot are up to date
    if (_flatpickr && _flatpickr.isOpen) _flatpickr.changeMonth(0, false);
  } catch (e) { /* silently ignore */ }
}

// ── Date picker change handler (shared by flatpickr onChange) ────────────────
async function handleDatePickerChange(selected) {
  if (_readOnly) return; // only available when unlocked

  const today      = new Date().toISOString().split('T')[0];
  const hasPuzzle  = _publishedDates.has(selected);

  if (selected < today || hasPuzzle) {
    // ── Date with a puzzle (past or future scheduled) — load it ──────────
    if (!_viewingPast) {
      _savedDraft = puzzles.length > 0 && puzzles[0] ? { ...puzzles[0] } : null;
    }
    setStatus('Loading puzzle…', 'info', 0);
    try {
      const r = await apiFetch(`/api/puzzle-by-date?date=${selected}`);
      if (r.ok) {
        const snapshot = await r.json();
        puzzles = [snapshot];
        currentIndex = 0;
        updateUI();
        setViewingPast(true);
        const [y, m, d] = selected.split('-');
        setStatus(`Viewing snapshot: ${parseInt(d)}.${parseInt(m)}.${y}`, 'info', 3000);
      } else {
        setStatus('No puzzle found for that date', 'error', 3000);
        if (!_viewingPast) _savedDraft = null;
        else setViewingPast(false);
        await refreshNextDate();
      }
    } catch (err) {
      setStatus('Failed to load puzzle', 'error', 3000);
    }
  } else {
    // ── Future date with no puzzle — restore draft ────────────────────────
    if (_viewingPast) {
      if (_savedDraft) {
        puzzles = [_savedDraft];
        _savedDraft = null;
        currentIndex = 0;
        updateUI();
      } else {
        puzzles = [];
        updateUI();
      }
      setViewingPast(false);
      setStatus('Ready', 'info', 2000);
    }
  }
}

// ── Next puzzle date ─────────────────────────────────────────────────────────
async function refreshNextDate() {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      if (attempt > 0) await new Promise(r => setTimeout(r, 2000));
      const r = await fetch('/api/next-date');
      if (!r.ok) continue;
      const { date } = await r.json();
      if (!date) continue;
      const iso     = puzzleDateToIso(date);
      const minDate = `${new Date().getFullYear()}-01-01`;
      const picker  = document.getElementById('publishDatePicker');

      // Track next free date so onDayCreate can paint the orange dot
      _nextFreeDate = iso;

      if (_flatpickr) {
        _flatpickr.set('minDate', minDate);
        if (!_viewingPast && (!picker?.value || picker.value < iso)) {
          _flatpickr.setDate(iso, false); // false = don't trigger onChange
        }
        // Re-render current month so the orange dot appears immediately
        if (_flatpickr.isOpen) _flatpickr.changeMonth(0, false);
      } else if (picker) {
        picker.min = minDate;
        if (!_viewingPast && (!picker.value || picker.value < iso)) picker.value = iso;
      }
      const dateMask = document.getElementById('dateMask');
      if (dateMask) dateMask.textContent = buildDateMask();
      return;
    } catch (e) { /* retry */ }
  }
}

// ── Jump-to-next-date button ─────────────────────────────────────────────────
document.getElementById('jumpToNextBtn').addEventListener('click', async () => {
  if (!_viewingPast) return;
  if (_savedDraft) {
    puzzles    = [_savedDraft];
    _savedDraft = null;
    currentIndex = 0;
    updateUI();
  } else {
    await load();
  }
  setViewingPast(false);
  await refreshNextDate();
  setStatus('Ready', 'info', 2000);
});

// ── Startup ─────────────────────────────────────────────────────────────────
// The page is publicly viewable — load the puzzle without auth.
// If a token is already stored, start in edit mode; otherwise read-only.
// Run sequentially so load() warms the Vercel function before the date fetch.
async function startup() {
  setStatus('Ready', 'info', 2000);
  // Init flatpickr FIRST so the native browser date UI never appears
  initDatePicker();
  setReadOnly(!getAuthToken());
  // Run in parallel — date label and puzzle content load concurrently
  await Promise.all([load(), refreshNextDate()]);
  // Fetch published dates in the background for calendar day coloring
  loadPublishedDates();
  // Fetch mechanic stats after initial load (only shown when unlocked)
  renderMechanicBar(true);
}
startup();
