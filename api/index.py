"""
Vercel serverless backend for Grooped Puzzle Editor.
Handles all /api/* routes. Uses Anthropic for generation, GitHub API for storage.
"""

import os
import json
import base64
import hmac
import hashlib
import random
import re
from collections import Counter
from datetime import datetime, timedelta
from functools import wraps

import google.generativeai as genai
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")
EDITOR_PASSWORD   = os.environ.get("EDITOR_PASSWORD", "")
EDITOR_SECRET     = os.environ.get("EDITOR_SECRET", "grooped-editor-secret-v1")

# GitHub repos
GROOPED_REPO    = os.environ.get("GROOPED_REPO", "roieshalom/grooped")
GENERATOR_REPO  = os.environ.get("GENERATOR_REPO", "roieshalom/grooped-puzzle-generator")

# File paths inside repos
PUZZLES_PATH  = "puzzles.json"
DRAFT_PATH    = "draft_puzzle.json"
BANNED_PATH   = "banned_categories.json"

# Anthropic models
GEN_MODEL    = os.environ.get("GEN_MODEL", "gemini-2.5-flash")
VERIFY_MODEL = os.environ.get("VERIFY_MODEL", "gemini-2.5-flash")

# ─── GitHub helpers ───────────────────────────────────────────────────────────

def _gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

def gh_read(repo, path):
    """Return (parsed_json, sha) or (None, None) if the file doesn't exist."""
    r = requests.get(
        f"https://api.github.com/repos/{repo}/contents/{path}",
        headers=_gh_headers(),
        timeout=15,
    )
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]

def gh_write(repo, path, content_obj, sha, message):
    """Create or update a file in a GitHub repo."""
    body = {
        "message": message,
        "content": base64.b64encode(
            json.dumps(content_obj, indent=2, ensure_ascii=False).encode("utf-8")
        ).decode("utf-8"),
    }
    if sha:
        body["sha"] = sha
    r = requests.put(
        f"https://api.github.com/repos/{repo}/contents/{path}",
        headers=_gh_headers(),
        json=body,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()

# ─── Auth ─────────────────────────────────────────────────────────────────────

def _compute_token(password: str) -> str:
    return hmac.new(
        EDITOR_SECRET.encode(), password.encode(), hashlib.sha256
    ).hexdigest()

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # If no password is configured, allow all requests (local dev)
        if not EDITOR_PASSWORD:
            return f(*args, **kwargs)
        token = request.headers.get("X-Editor-Token", "")
        expected = _compute_token(EDITOR_PASSWORD)
        if not hmac.compare_digest(token, expected):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/api/auth", methods=["POST"])
def auth():
    data = request.get_json(force=True) or {}
    password = data.get("password", "")
    if not EDITOR_PASSWORD or password == EDITOR_PASSWORD:
        return jsonify({"ok": True, "token": _compute_token(EDITOR_PASSWORD)})
    return jsonify({"ok": False, "error": "Wrong password"}), 401

# ─── Banned categories ────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    return (name or "").strip().lower()

def _load_banned():
    """Returns (list_of_names, sha). Safe: returns ([], None) on any error."""
    try:
        data, sha = gh_read(GENERATOR_REPO, BANNED_PATH)
        if isinstance(data, list):
            return data, sha
        return [], sha
    except Exception:
        return [], None

@app.route("/api/banned-categories", methods=["GET"])
@require_auth
def get_banned():
    banned, _ = _load_banned()
    return jsonify(banned)

@app.route("/api/banned-categories", methods=["POST"])
@require_auth
def add_banned():
    data = request.get_json(force=True) or {}
    category = data.get("category", "").strip()
    if not category:
        return jsonify({"ok": False, "error": "No category provided"}), 400

    banned, sha = _load_banned()
    norms = {_normalize(c) for c in banned}
    if _normalize(category) not in norms:
        banned.append(category)
        try:
            gh_write(GENERATOR_REPO, BANNED_PATH, banned, sha, f"Ban: {category}")
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})

# ─── Published puzzle by date ─────────────────────────────────────────────────

_DATE_FORMATS = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]

def _parse_any_date(ds: str):
    """Try several date formats and return a date object, or None."""
    if not ds:
        return None
    # Handle non-zero-padded D.M.YYYY by splitting on '.' manually
    parts = ds.split(".")
    if len(parts) == 3:
        try:
            return datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
        except (ValueError, IndexError):
            pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(ds, fmt).date()
        except ValueError:
            continue
    return None

@app.route("/api/puzzle-by-date", methods=["GET"])
@require_auth
def get_puzzle_by_date():
    date_str = request.args.get("date", "")
    if not date_str:
        return jsonify({"error": "date param required"}), 400
    try:
        target_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "use YYYY-MM-DD"}), 400
    try:
        existing, _ = gh_read(GROOPED_REPO, PUZZLES_PATH)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if not existing:
        return jsonify({"error": "no puzzles found"}), 404
    puzzles_list = (
        existing.get("puzzles", []) if isinstance(existing, dict) else (existing or [])
    )
    for p in puzzles_list:
        p_dt = _parse_any_date(p.get("date", ""))
        if p_dt and p_dt == target_dt:
            return jsonify(p)
    # Return available dates to help debug
    available = sorted(
        {str(d) for d in (_parse_any_date(p.get("date", "")) for p in puzzles_list) if d},
        reverse=True,
    )
    return jsonify({"error": f"no puzzle on {target_dt}", "available_dates": available[:10]}), 404

# ─── Draft puzzle ─────────────────────────────────────────────────────────────

@app.route("/api/puzzle", methods=["GET"])
def get_puzzle():  # public — read-only viewers can see the current draft
    try:
        draft, _ = gh_read(GENERATOR_REPO, DRAFT_PATH)
        if draft and draft.get("categories"):
            draft.pop("_vercel_draft", None)  # strip internal marker if present
            return jsonify([draft])
    except Exception:
        pass
    return jsonify([])

@app.route("/api/puzzle", methods=["POST"])
@require_auth
def save_puzzle():
    puzzle = request.get_json(force=True) or {}

    # Validate
    errors, dups = [], []
    categories = puzzle.get("categories", [])
    if len(categories) != 4:
        errors.append(f"Need exactly 4 categories, got {len(categories)}")

    all_words = []
    for cat in categories:
        for w in cat.get("words", []):
            w = w.upper().strip()
            if w:
                all_words.append(w)

    counts = Counter(all_words)
    dups = [w for w, n in counts.items() if n > 1]
    for w in dups:
        errors.append(f"Duplicate word '{w}' within this puzzle")

    puzzle["_validation"] = {
        "valid": len(errors) == 0,
        "errors": errors,
        "duplicate_words": dups,
    }

    # Ensure mechanic/tier are present in each category (lifted from thinking block if needed)
    _inject_mechanic_tier(puzzle)

    # Write a clean draft to GitHub (no thinking/language/false_decoy/etc.)
    draft_to_write = _sanitize_for_export(puzzle)
    # Re-attach _validation so the editor can highlight duplicate words
    draft_to_write["_validation"] = puzzle["_validation"]
    try:
        _, sha = gh_read(GENERATOR_REPO, DRAFT_PATH)
        gh_write(GENERATOR_REPO, DRAFT_PATH, draft_to_write, sha, "Update draft puzzle")
    except Exception as e:
        print(f"Draft save to GitHub failed (non-fatal): {e}")

    return jsonify({"ok": True, "puzzle": draft_to_write})

# ─── Export ───────────────────────────────────────────────────────────────────

@app.route("/api/export", methods=["POST"])
@require_auth
def export_puzzle():
    puzzle = request.get_json(force=True) or {}
    puzzle.pop("_validation", None)

    # Load existing puzzles from grooped repo
    try:
        existing, sha = gh_read(GROOPED_REPO, PUZZLES_PATH)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not read puzzles.json: {e}"}), 500

    if existing is None:
        existing = []

    # Normalise format
    if isinstance(existing, dict):
        puzzles_list = existing.get("puzzles", [])
        use_object_format = True
    else:
        puzzles_list = existing
        use_object_format = False

    # Assign next ID
    ids = []
    for p in puzzles_list:
        try:
            ids.append(int(p.get("id", 0)))
        except (ValueError, TypeError):
            pass
    puzzle["id"] = str(max(ids) + 1) if ids else "1"

    # Assign publish date — use user-chosen date or auto next-day
    publish_date_str = puzzle.pop("publish_date", None)
    if publish_date_str:
        try:
            dt = datetime.strptime(publish_date_str, "%Y-%m-%d")
            puzzle["date"] = f"{dt.day}.{dt.month}.{dt.year}"
        except ValueError:
            puzzle["date"] = publish_date_str  # fall back to raw string
    else:
        dates = []
        for p in puzzles_list:
            ds = p.get("date", "")
            if ds:
                try:
                    dates.append(datetime.strptime(ds, "%d.%m.%Y"))
                except ValueError:
                    pass
        if dates:
            next_d = max(dates) + timedelta(days=1)
            puzzle["date"] = f"{next_d.day}.{next_d.month}.{next_d.year}"
        else:
            now = datetime.now()
            puzzle["date"] = f"{now.day}.{now.month}.{now.year}"

    puzzle = _sanitize_for_export(puzzle)
    puzzles_list.append(puzzle)

    # Write back
    to_save = ({**existing, "puzzles": puzzles_list} if use_object_format else puzzles_list)
    try:
        gh_write(
            GROOPED_REPO, PUZZLES_PATH, to_save, sha,
            f"Add puzzle {puzzle['id']} ({puzzle['date']})"
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not write puzzles.json: {e}"}), 500

    # Auto-ban exported category names
    try:
        banned, banned_sha = _load_banned()
        norms = {_normalize(c) for c in banned}
        changed = False
        for cat in puzzle.get("categories", []):
            name = cat.get("name", "").strip()
            if name and _normalize(name) not in norms:
                banned.append(name)
                norms.add(_normalize(name))
                changed = True
        if changed:
            gh_write(GENERATOR_REPO, BANNED_PATH, banned, banned_sha,
                     "Auto-ban exported categories")
    except Exception as e:
        print(f"Auto-ban failed (non-fatal): {e}")

    return jsonify({"ok": True, "id": puzzle["id"], "date": puzzle["date"]})

# ─── Export sanitisation ─────────────────────────────────────────────────────

_FIELDS_TO_STRIP = {
    "thinking", "anchors", "language", "status",
    "other_trick", "false_decoy", "_validation",
}

_TIER_LOOKUP = {
    # Tier 1
    "TAXONOMY": 1, "FOUND_IN_SCENE": 1, "PREFIX_BLANK": 1,
    "SUFFIX_BLANK": 1, "SYNONYMS": 1,
    # Tier 2
    "THINGS_THAT_VERB": 2, "CAN_BE_VERBED": 2, "SHARED_HIDDEN_PROPERTY": 2,
    "METAPHOR_SUBSTITUTES": 2, "WAYS_TO_VERB": 2, "IDIOM_COMPLETION": 2,
    "ORDERED_SET_MEMBER": 2, "WORKS_BY_ONE_MAKER": 2, "CHARACTERS_IN_ONE_WORK": 2,
    # Tier 3
    "HIDDEN_WORD_INSIDE": 3, "HIDDEN_WORD_AT_START": 3, "HIDDEN_WORD_AT_END": 3,
    "HOMOPHONE_OF_LETTER": 3, "HOMOPHONE_OF_NUMBER": 3, "HOMOPHONE_PAIRS": 3,
    "COMPOUND_BOTH_WAYS": 3, "ADD_LETTER": 3, "DROP_LETTER": 3,
    "EPONYMS": 3, "CROSS_LANGUAGE": 3, "ABBREVIATION_EXPANSION": 3,
    # Tier 4
    "ANAGRAM_OF_ONE_SOURCE": 4, "ACROSTIC_FIRST_LETTERS": 4,
    "CHAIN_THROUGH_HUB": 4, "PORTMANTEAU": 4, "ONOMATOPOEIA": 4,
}

def _inject_mechanic_tier(puzzle: dict) -> dict:
    """Lift mechanic + tier into each category from thinking block (mutates in place, returns puzzle)."""
    thinking = puzzle.get("thinking", {})
    chosen = thinking.get("mechanic_balance", {}).get("chosen_for_this_puzzle", [])
    for i, cat in enumerate(puzzle.get("categories", [])):
        if not cat.get("mechanic") and i < len(chosen):
            cat["mechanic"] = chosen[i]
        mechanic = cat.get("mechanic")
        if not cat.get("tier") and mechanic:
            cat["tier"] = _TIER_LOOKUP.get(mechanic)
    return puzzle


def _normalize_decoy(d: dict) -> dict:
    """Normalise decoy schema: home/tempts_toward → category_a/category_b."""
    if not d.get("category_a") and d.get("home"):
        d = dict(d)
        d["category_a"] = d.pop("home", "")
        d["category_b"] = d.pop("tempts_toward", "")
        if "why" in d and not d.get("reason_a"):
            d["reason_a"] = d.pop("why", "")
    return d


def _format_date(raw: str) -> str:
    """Normalise any supported date string to zero-padded DD.MM.YYYY."""
    if not raw:
        return raw
    d = _parse_any_date(raw)
    if d:
        return f"{d.day:02d}.{d.month:02d}.{d.year}"
    return raw  # unrecognised format — return as-is


def _sanitize_for_export(puzzle: dict) -> dict:
    """Strip unwanted fields, enforce field order, normalise date and decoys.

    Call order guarantee: _inject_mechanic_tier() must be called on the puzzle
    before this function so that cat.get('mechanic') / cat.get('tier') are
    already populated. _sanitize_for_export also re-derives them from the
    thinking block as a fallback, so it is safe either way.
    """
    thinking = puzzle.get("thinking", {})
    chosen = thinking.get("mechanic_balance", {}).get("chosen_for_this_puzzle", [])

    # Lift decoys from thinking if top-level array is empty
    raw_decoys = puzzle.get("decoys") or []
    if not raw_decoys:
        thinking_decoys = thinking.get("decoys", [])
        if thinking_decoys:
            print(f"_sanitize: lifting {len(thinking_decoys)} decoy(s) from thinking.decoys")
            raw_decoys = thinking_decoys
    clean_decoys = [_normalize_decoy(d) for d in raw_decoys]

    # Sanitize categories: inject mechanic + tier, enforce field order
    clean_cats = []
    for i, cat in enumerate(puzzle.get("categories", [])):
        mechanic = cat.get("mechanic") or (chosen[i] if i < len(chosen) else None)
        tier = cat.get("tier") or (_TIER_LOOKUP.get(mechanic) if mechanic else None)
        clean_cats.append({
            "tier":       tier,
            "mechanic":   mechanic,
            "difficulty": cat.get("difficulty"),
            "name":       cat.get("name"),
            "words":      cat.get("words", []),
        })

    # Enforce top-level field order: id, date, categories, decoys, attempt_log
    return {
        "id":          puzzle.get("id"),
        "date":        _format_date(puzzle.get("date", "")),
        "categories":  clean_cats,
        "decoys":      clean_decoys,
        "attempt_log": puzzle.get("attempt_log"),
    }

@app.route("/api/mechanic-stats", methods=["GET"])
def get_mechanic_stats():
    """Return mechanic usage data for the last N tagged puzzles (no auth required)."""
    window = 21  # rolling window size
    try:
        existing, _ = gh_read(GROOPED_REPO, PUZZLES_PATH)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not existing:
        return jsonify({"tagged_count": 0, "window_size": window, "cat_mechanics": [], "all_mechanics": {}})

    puzzles_list = (
        existing.get("puzzles", []) if isinstance(existing, dict) else (existing or [])
    )

    # Sort by date descending, take the last `window` tagged puzzles
    def sort_key(p):
        d = _parse_any_date(p.get("date", ""))
        return d or datetime.min.date()

    sorted_puzzles = sorted(puzzles_list, key=sort_key, reverse=True)
    tagged = [p for p in sorted_puzzles if any(c.get("mechanic") for c in p.get("categories", []))]
    recent = tagged[:window]

    # Aggregate mechanic counts across all categories in the window
    mechanic_counts: dict = {}
    cat_mechanics = []  # flat list of all (mechanic, tier) pairs in order
    for p in recent:
        for cat in p.get("categories", []):
            m = cat.get("mechanic")
            if m:
                mechanic_counts[m] = mechanic_counts.get(m, 0) + 1
                t = cat.get("tier") or _TIER_LOOKUP.get(m)
                cat_mechanics.append({"mechanic": m, "tier": t})

    return jsonify({
        "tagged_count": len(recent),
        "window_size": window,
        "cat_mechanics": cat_mechanics,
        "all_mechanics": mechanic_counts,
    })


# ─── Anthropic helpers ────────────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """Extract raw JSON from Gemini output — handles prose, code fences, any wrapping."""
    # Strip code fences first
    text = re.sub(r'```(?:json)?', '', text, flags=re.IGNORECASE).strip()
    # Scan for the first position that starts a valid JSON object
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == '{':
            try:
                obj, _ = decoder.raw_decode(text, i)
                return json.dumps(obj)
            except json.JSONDecodeError:
                continue
    return text

def _call_claude(prompt: str, max_tokens: int = 3000, model: str = None) -> dict:
    """Call Gemini and parse JSON from the response."""
    model = model or GEN_MODEL
    genai.configure(api_key=GEMINI_API_KEY)
    gmodel = genai.GenerativeModel(
        model_name=model,
        system_instruction="You are an expert Grooped puzzle generator. Return valid JSON only, no prose.",
    )
    response = gmodel.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            max_output_tokens=max_tokens,
        ),
    )
    extracted = _extract_json(response.text)
    try:
        return json.loads(extracted)
    except json.JSONDecodeError:
        raise ValueError(f"Could not parse JSON from Gemini response: {response.text[:300]}")

# ─── Decoy verification ───────────────────────────────────────────────────────

def _verify_decoys(decoys: list, categories: list) -> list:
    if not decoys:
        return []

    cats_block = "\n".join(
        f'- "{c["name"]}": {", ".join(c.get("words", []))}'
        for c in categories
    )
    decoy_lines = "\n".join(
        f'{i}. Word: {d["word"]}\n'
        f'   Fit A — "{d["category_a"]}": {d.get("reason_a", "")}\n'
        f'   Fit B — "{d["category_b"]}": {d.get("reason_b", "")}'
        for i, d in enumerate(decoys, 1)
    )

    prompt = f"""Fact-check these decoys for a Connections puzzle.

CATEGORIES:
{cats_block}

DECOYS:
{decoy_lines}

For each decoy: does the word GENUINELY fit both claimed categories using well-known everyday meanings?
- "Fits" = a regular adult immediately recognizes the connection, no explanation needed.
- Be generous: a slightly uncommon but universally-known connection counts.
- When in doubt, keep the decoy — an empty decoy list is worse than a slightly generous one.

Return ONLY JSON:
{{"verdicts": [{{"index": 1, "keep": true, "reason": "brief reason"}}, ...]}}"""

    try:
        result = _call_claude(prompt, max_tokens=600, model=VERIFY_MODEL)
        verdicts = {v["index"]: v["keep"] for v in result.get("verdicts", [])}

        verified = []
        for i, decoy in enumerate(decoys, 1):
            if verdicts.get(i, True):
                verified.append(decoy)
            else:
                reason = next(
                    (v.get("reason", "") for v in result.get("verdicts", []) if v["index"] == i),
                    ""
                )
                print(f"Dropped decoy '{decoy['word']}': {reason}")

        print(f"Decoy verification: {len(verified)}/{len(decoys)} kept")
        return verified

    except Exception as e:
        print(f"Decoy verification failed ({e}), keeping all")
        return decoys

# ─── Puzzle generation ────────────────────────────────────────────────────────

def _build_prompt(banned_list: list) -> str:
    banned_norm = sorted({_normalize(n) for n in banned_list})
    recent = banned_norm[-60:] if len(banned_norm) > 60 else banned_norm
    remaining = [c for c in banned_norm if c not in set(recent)]
    sampled = random.sample(remaining, min(40, len(remaining))) if remaining else []
    preview = sorted(set(recent) | set(sampled))
    preview_text = ", ".join(preview) if preview else "none"

    return """GROOPED PUZZLE GENERATION PROMPT (v5)
=====================================

You are designing a single 4x4 NYT Connections-style puzzle for Grooped. 16 unique words, four groups of four, each tagged with a difficulty color: yellow (easiest), green, blue, purple (hardest). Output schema must match puzzles.json.

NORTH STAR
==========

A great Grooped puzzle is not four neat lists. It is four groups that bleed into each other on the board, so a solver feels multiple words could plausibly live in multiple homes. A STRONG BOARD BEATS EVERY RULE BELOW. That cross-pull tension is the puzzle. Without it, you made a quiz.

STEP 0: FETCH THE LIVE CORPUS
============================

Before drafting, fetch https://raw.githubusercontent.com/roieshalom/grooped/refs/heads/main/puzzles.json. You will use it for four things:

1. REPEAT CHECK: no category theme or individual word may repeat from the last 60 days.
2. STYLE CALIBRATION: absorb the corpus voice.
3. MECHANIC BALANCING: read the 'mechanic' field on each category and the 'attempt_log' field on each puzzle. See "MECHANIC FREQUENCY SYSTEM" below.
4. WARMUP AWARENESS: puzzles before #137 do not have 'mechanic' fields. They are untagged history. Your cooldown calculations only run on tagged puzzles.

If you cannot fetch it, say so and stop.

MECHANIC FREQUENCY SYSTEM
=========================

Mechanics live in four tiers by how often they should appear. The tiers exist because some mechanics (simple "___ X" fill-in-blank) feel fresh weekly, while others (first-letter acrostics) feel forced if used often.

HOW TO USE THE TIERS
====================

When picking the four mechanics for a new puzzle:

1. SCAN the last 21 tagged puzzles in puzzles.json. Note which mechanics appeared in their 'mechanic' fields AND in their 'attempt_log' (abandoned attempts count toward cooldown too).
2. APPLY COOLDOWNS: a mechanic that appeared inside its cooldown window is off-limits for this puzzle.
3. PREFER UNDERUSED MECHANICS: if a Tier 2 or Tier 3 mechanic has not appeared in the last 21 puzzles, it is a strong candidate.
4. DON'T FORCE RARE MECHANICS: Tier 4 should appear when a great idea naturally lands, not because the cooldown expired.

A typical strong puzzle uses 1-2 mechanics from Tier 1, 1-2 from Tier 2, optionally 1 from Tier 3, and rarely one from Tier 4.

WARMUP PERIOD (until 21 tagged puzzles exist)
==============================================

The corpus before puzzle #137 is heavily skewed toward Tier 1 (taxonomy and reference). Until there are 21 tagged puzzles to read from:

- LEAN TOWARD TIER 2 AND TIER 3 MECHANICS, since the untagged history already provides plenty of Tier 1 baseline.
- DON'T DOUBLE UP ON TIER 1 MECHANICS in the same puzzle during warmup unless the cross-pulls are exceptional.
- No more than 2 categories from the same tier in a single puzzle (warmup or not).
- Once 21 tagged puzzles exist, switch to standard cooldown logic.

TIER 1: WORKHORSES — cooldown 4 puzzles, ~40% of categories long-term
====================================================================

The reliable backbones. Repeating these every few days is fine because the content is fresh even when the mechanic is familiar.

- TAXONOMY: flat list of a category type (cheeses, currencies, dog breeds). Allowed only when at least 2 of its 4 words pull toward another group on the board. Otherwise it is filler.
- FOUND_IN_SCENE: things in a place. "At the dentist" → BRACE, CAVITY, CROWN, BRIDGE.
- PREFIX_BLANK: "___ X". "___ STONE" → CORNER, KEY, SAND, LIME.
- SUFFIX_BLANK: "X ___". "DEAD ___" → PAN, BEAT, POOL, RINGER.
- SYNONYMS: literal synonyms for one word. "Walk" → STROLL, TREAD, WANDER, MARCH.

TIER 2: REGULARS — cooldown 7 puzzles, ~35% of categories long-term
====================================================================

Slightly more lateral. These should appear every 1 to 2 weeks.

- THINGS_THAT_VERB: nouns that all do an action. "Things that RUN" → NOSE, FAUCET, CANDLE, NYLON.
- CAN_BE_VERBED: things that can all receive an action. "Can be scrambled" → EGG, TELEGRAM, CODE, LETTERS.
- SHARED_HIDDEN_PROPERTY: surprise trait. "Have teeth" → COMB, GEAR, ZIPPER, SAW.
- METAPHOR_SUBSTITUTES: figurative terms for one concept. "In trouble" → BIND, JAM, PICKLE, HOT WATER. UNDERUSED IN THE CORPUS. PREFER THIS.
- WAYS_TO_VERB: phrasal styles of an action. "Ways to say yes" → SURE, BET, DEAL, GRANTED.
- IDIOM_COMPLETION: words that finish a specific idiom. "Bite the ___" → BULLET, DUST, HAND, APPLE.
- ORDERED_SET_MEMBER: planets, Greek letters, NATO alphabet, ranks, days, months.
- WORKS_BY_ONE_MAKER: songs by an artist, films by a director.
- CHARACTERS_IN_ONE_WORK: cast of one show or book.

TIER 3: SPECIALS — cooldown 21 puzzles, ~20% of categories long-term
====================================================================

Wordplay-flavored mechanics that lose punch with overuse. Roughly once every 3 weeks each.

- HIDDEN_WORD_INSIDE: each word secretly contains an item from a hidden category, anywhere. Hidden numbers → STONE (one), OFTEN (ten), CANINE (nine), FREIGHT (eight).

HIDDEN WORD VERIFICATION (mandatory for all HIDDEN_WORD mechanics):
Before committing to any hidden-word category, spell out each word
letter by letter and confirm the hidden item appears as consecutive
letters. Example: WINTER → W-I-N-T-E-R → contains WIN, not WINE.
If you cannot find four words that each cleanly contain the hidden
item as consecutive letters, abandon this mechanic and log the attempt.
Do not approximate. Do not use the first few letters of a word as the
hidden item unless they spell the complete item (SPRING does not hide
RUM, SPRING does not hide GIN, SPRING hides nothing drinkable).

- HIDDEN_WORD_AT_START: each word starts with a hidden item. Soda brands → CRUSHWORTHY, FANTAGRAPHICS, FRESCADE, PEPSINOGEN.
- HIDDEN_WORD_AT_END: same idea, at the end.
- HOMOPHONE_OF_LETTER: sound like single letters. SEA (C), ARE (R), WHY (Y), JAY (J).
- HOMOPHONE_OF_NUMBER: sound like numbers. ATE (8), FOR (4), WON (1), TOO (2).
- HOMOPHONE_PAIRS: each has a homophone fitting a category. BARE/BEAR, FLOWER/FLOUR.
- COMPOUND_BOTH_WAYS: words that work as both prefix and suffix to one hub.
- ADD_LETTER: become other real words when you add the same letter (CARE → SCARE).
- DROP_LETTER: same in reverse.
- EPONYMS: things named after people. SANDWICH, BOYCOTT, GUILLOTINE, CARDIGAN.
- CROSS_LANGUAGE: same concept across languages. "Cheers" → SLAINTE, KAMPAI, PROST, CIN-CIN.
- ABBREVIATION_EXPANSION: common acronyms read as letters (NASA, FBI, SCUBA, RADAR).

TIER 4: TREATS — cooldown 45 puzzles, ~5% of categories long-term
==================================================================

Showpiece mechanics. Heavy when they land, exhausting if they repeat. Roughly once every 6 weeks each.

- ANAGRAM_OF_ONE_SOURCE: four anagrams of one word. From LISTEN: SILENT, TINSEL, INLETS, ENLIST.
- ACROSTIC_FIRST_LETTERS: first letters of the four words spell a hidden fifth word.
- CHAIN_THROUGH_HUB: the hub of a "___ X" group is itself a word in another group on the same board. The most elegant trick when it works.
- PORTMANTEAU: blended words. BRUNCH, SMOG, MOTEL, SPORK.
- ONOMATOPOEIA: sound-effect words. POW, BAM, ZAP, BOOM.

FALLBACK WITH LOGGING
====================

If you commit to a Tier 3 or Tier 4 mechanic and after a real attempt cannot find four words that work cleanly, you may fall back to a Tier 1 or Tier 2 mechanic. YOU MUST LOG THE ABANDONED ATTEMPT in the 'attempt_log' field of the puzzle. The cooldown system reads this log, so an abandoned attempt counts toward the cooldown the same as a shipped one. This prevents the model from retrying the same broken idea day after day.

Reasons to abandon:
- Cannot find four genuine examples without forcing obscure words
- The mechanic produces words that have no decoy potential against the rest of the board
- The mechanic technically works but feels academic rather than playful

Do not abandon for trivial reasons. The point is to attempt hard mechanics, not to default away from them.

DECOY ENGINE
============

For each puzzle, identify 2 to 3 decoy words.

A DECOY is a word in category A that solvers will be tempted to drop into category B, where category B is ALSO A REAL GROUP ON THIS EXACT BOARD. A decoy that points at a phantom category is just a hard word, not a decoy.

A FALSE DECOY is the next move: a word that looks like it should belong elsewhere but actually lives in its obvious home. The suspicion is the trap. Example: THIMBLE on a board with both Monopoly Pieces and Sewing Equipment, where THIMBLE actually goes to Monopoly.

If you cannot identify at least 2 real decoys, your puzzle has no cross-board tension. Rebuild it.

DECOYS MUST APPEAR IN THE OUTPUT JSON.
The 'decoys' array is what the editor displays to you after generation.
If you put decoy logic only in 'thinking' or 'false_decoy', it will not
appear anywhere useful. For every decoy you identify, write a full entry
in the 'decoys' array with all four fields: word, category_a, reason_a,
category_b, reason_b. A puzzle with an empty 'decoys' array will be
treated as having no decoys, regardless of what is in 'thinking'.
Minimum 2 entries. No exceptions.

DECOY IDENTIFICATION IS MANDATORY. Before finalizing the puzzle,
scan every word on the board and ask: could this word plausibly
belong to a different category that exists on this board? If yes,
it is a decoy and MUST appear in the decoys array. Do not put decoy
reasoning only in thinking. A puzzle with fewer than 2 entries in
the decoys array will be rejected. Check words like fill-in-blank
completions (CLUB could be a card suit AND a medieval weapon),
taxonomy words with double meanings (STOCK, PRESS, CROWN), and
hidden-word containers that also fit another category. Every real
cross-pull must be documented in the decoys array.

CATEGORY FRAMING
================

How you name the category changes how it reads. "Words for trouble" is dull. "Metaphors for being in trouble" implies the category is figurative and that's the trick. "Look at with awe" reads like a riddle. "Ways to gesture goodbye" beats "Goodbye gestures." Frame as a verb phrase or riddle whenever you can.

DIFFICULTY AS A SOFT PATTERN
============================

Soft guideline, not a rule. Deviate freely if the board demands it.

- YELLOW: clearest entry. Often a clean scene, taxonomy, or synonym set, with one mild decoy temptation.
- GREEN: recognizable connection that needs a small lateral step.
- BLUE: misdirection-heavy or domain-specific.
- PURPLE: usually wordplay or the trickiest semantic leap. Tier 3/4 mechanics most often live here.

HARD RULES
=========

- 16 unique words on the board (case-insensitive).
- No word repeats from any puzzle in the last 60 days.
- No category theme repeats from the last 60 days. Older repeats fine if spread out.
- No category where all four words share a surface tell (all -ISM, all start with LIM-, all Italian musical terms). Surface tells defeat the puzzle.
- NO "FAMOUS BOBS / CHARLIES / AMYS / STEVES / MIKES" or any "FAMOUS [COMMON FIRST NAME]" pattern. Permanently retired.
- No US Presidents as a category.
- No "Words that are both X and Y" as a category name.
- No standalone color list (RED, BLUE, GREEN, YELLOW). Hues-of-X is also tired.
- No back-to-back puzzles with the same cultural theme.
- No words a 12-year-old wouldn't know unless the category demands it (avoid CINNABAR, COQUELICOT, ESCUTCHEON, SINOPER).
- No word appears twice in the same puzzle.
- Decoy words must point at a category that exists on this exact board.
- Respect mechanic cooldowns from the tier system.
- Every category must have a 'mechanic' and 'tier' field. Every puzzle must have an 'attempt_log' field (can be a single entry if no fallback happened).

CROSS-DOMAIN RULE: No two categories on the same board may draw
primarily from the same real-world domain. If two groups are both
animal-heavy, both food-heavy, or both sport-heavy, rebuild one of
them. The board must feel like four different worlds, not two worlds
split in half.

THINGS_THAT_VERB QUALITY RULE: The four words must perform the action
in genuinely different contexts or senses. "Things that run" must
include words like NOSE, FAUCET, ENGINE, MASCARA — each running in a
different domain. Four animals that all run the same way is a flat
taxonomy pretending to be a verb category. If all four words share the
same real-world domain, this mechanic is being misused. Pick different
words or pick a different mechanic.

SHARED_HIDDEN_PROPERTY QUALITY RULE: The shared property must be
surprising. "Have stripes" with four striped animals is obvious and
boring. "Have stripes" with ZEBRA, TOOTHPASTE, REFEREE, BARCODE is
surprising because the words come from different domains. The aha
moment comes from the unexpected connection, not the expected one. If
a solver can guess all four words just by knowing the category name,
the property is not hidden enough.

WORKFLOW
========

1. FETCH puzzles.json.
2. RUN THE MECHANIC BALANCER: scan the last 21 tagged puzzles. For each tier, list which mechanics appeared (in 'mechanic' fields or 'attempt_log' entries). Identify Tier 2 and Tier 3 mechanics that haven't appeared. Note any Tier 4 mechanics that haven't appeared in the last 45.
3. PICK THE SPINE MECHANIC (often purple). Prefer underused candidates. If a Tier 4 idea is calling to you and the cooldown allows, go for it.
4. PLANT A DECOY SEED: a word that plausibly lives in two of your groups.
5. BUILD THE OTHER THREE GROUPS so the decoy seed pulls between them. Pick mechanics that haven't appeared recently when you have a choice.
6. ADD A SECOND DECOY.
7. LIST ALL 16 WORDS. Confirm zero duplicates.
8. STRESS-TEST: can a solver group all four words of any group by surface pattern alone? If yes, weaken the surface signal.
9. IF YOUR SPINE MECHANIC ISN'T WORKING, abandon it, log the attempt, and pick a different mechanic. Do not silently switch.
10. SELF-CRITIQUE: tricked but fair, or tricked and annoyed?

OUTPUT FORMAT
=============

Match the production schema. The 'thinking' block is your scratchpad and must come first. Note the new 'mechanic' and 'tier' fields per category, and the 'attempt_log' field on the puzzle.

EXAMPLE JSON OUTPUT (PUZZLE #137)
================================

{
  "id": "137",
  "date": "27.04.2026",
  "language": "en",
  "thinking": {
    "mechanic_balance": {
      "tagged_puzzles_available": 12,
      "warmup_active": true,
      "tier_1_recently_used": ["PREFIX_BLANK", "FOUND_IN_SCENE"],
      "tier_2_recently_used": ["SHARED_HIDDEN_PROPERTY"],
      "tier_3_recently_used": [],
      "tier_4_recently_used": [],
      "underused_candidates": ["METAPHOR_SUBSTITUTES", "HIDDEN_WORD_AT_START", "EPONYMS"],
      "chosen_for_this_puzzle": ["FOUND_IN_SCENE", "METAPHOR_SUBSTITUTES", "WAYS_TO_VERB", "SUFFIX_BLANK"],
      "cooldown_check": "PASS"
    },
    "all_16_words": "KEYS CHANGE LINT RECEIPTS BIND JAM PICKLE HOT_WATER SURE BET DEAL GRANTED PAN BEAT POOL RINGER",
    "duplicate_check": "PASS"
  },
  "categories": [
    {
      "name": "Things that jingle in your pocket",
      "difficulty": "yellow",
      "mechanic": "FOUND_IN_SCENE",
      "tier": 1,
      "words": ["KEYS", "CHANGE", "LINT", "RECEIPTS"]
    },
    {
      "name": "Metaphors for being in trouble",
      "difficulty": "green",
      "mechanic": "METAPHOR_SUBSTITUTES",
      "tier": 2,
      "words": ["BIND", "JAM", "PICKLE", "HOT WATER"]
    },
    {
      "name": "Ways to say yes",
      "difficulty": "blue",
      "mechanic": "WAYS_TO_VERB",
      "tier": 2,
      "words": ["SURE", "BET", "DEAL", "GRANTED"]
    },
    {
      "name": "DEAD ___",
      "difficulty": "purple",
      "mechanic": "SUFFIX_BLANK",
      "tier": 1,
      "words": ["PAN", "BEAT", "POOL", "RINGER"]
    }
  ],
  "decoys": [
    {
      "word": "JAM",
      "category_a": "Metaphors for being in trouble",
      "reason_a": "in a jam means in trouble",
      "category_b": "Things that jingle in your pocket",
      "reason_b": "Solvers may think of jam jars before the idiom."
    },
    {
      "word": "BET",
      "category_a": "Ways to say yes",
      "reason_a": "you bet means yes",
      "category_b": "DEAD ___",
      "reason_b": "DEAD BET isn't a phrase but the word feels gambly enough to tempt solvers."
    }
  ],
  "false_decoy": null,
  "attempt_log": [
    { "mechanic": "ACROSTIC_FIRST_LETTERS", "tier": 4, "result": "abandoned", "reason": "couldn't land four natural words spelling a fifth without forcing obscure terms" },
    { "mechanic": "SUFFIX_BLANK", "tier": 1, "result": "shipped" }
  ]
}

If no fallback happened, attempt_log contains a single entry with result: "shipped".

REFERENCE: TARGET QUALITY PUZZLE
===============================

The example above (puzzle #137) is the target. Two scenes/idioms in Tiers 1-2, one wordplay in Tier 1 purple, real cross-pulls between groups (CHANGE could be pocket or could be improvement, JAM could be food or trouble, BEAT could be drum or DEAD BEAT). Strong board, varied mechanics, no Tier 4 forced. This is what good looks like."""

@app.route("/api/generate-puzzle", methods=["POST"])
@require_auth
def generate_puzzle():
    try:
        banned, _ = _load_banned()
        prompt = _build_prompt(banned)

        max_attempts = 5
        last_data = None
        banned_norms = {_normalize(n) for n in banned}

        for attempt in range(1, max_attempts + 1):
            print(f"Generation attempt {attempt}")

            try:
                data = _call_claude(prompt, max_tokens=3000)
            except Exception as e:
                print(f"Claude call failed on attempt {attempt}: {e}")
                continue

            if "categories" not in data or len(data["categories"]) != 4:
                print("Invalid categories structure")
                continue

            # Reject banned categories
            has_banned = any(
                _normalize(cat.get("name", "")) in banned_norms
                for cat in data["categories"]
            )
            if has_banned:
                print("Rejected: contains banned category")
                continue

            # Collect all board words
            all_words = [
                w.upper().strip()
                for cat in data["categories"]
                for w in cat.get("words", [])
            ]

            # Reject circular words (word inside own category name)
            has_circular = False
            for cat in data["categories"]:
                cat_upper = cat.get("name", "").upper()
                for w in cat.get("words", []):
                    if w.upper().strip() in cat_upper.split():
                        print(f"Rejected: '{w}' in category name '{cat['name']}'")
                        has_circular = True
                        break
                if has_circular:
                    break
            if has_circular:
                continue

            # Normalise decoy schema: model sometimes uses home/tempts_toward instead of category_a/b
            def _norm_decoy(d):
                if not d.get("category_a") and d.get("home"):
                    d = {**d, "category_a": d["home"], "category_b": d.get("tempts_toward", "")}
                return d

            raw_decoys = data.get("decoys") or []
            # Fallback: lift from thinking.decoys if top-level array is empty
            if not raw_decoys:
                thinking_decoys = data.get("thinking", {}).get("decoys", [])
                if thinking_decoys:
                    print(f"Lifting {len(thinking_decoys)} decoy(s) from thinking.decoys")
                    raw_decoys = thinking_decoys
            raw_decoys = [_norm_decoy(d) for d in raw_decoys]

            # Strip structurally invalid decoys
            board_set = {w for w in all_words if w}
            cat_names = {cat.get("name", "").strip() for cat in data["categories"]}
            clean_decoys = [
                d for d in raw_decoys
                if (d.get("word", "").upper().strip() in board_set
                    and d.get("category_a", "").strip() in cat_names
                    and d.get("category_b", "").strip() in cat_names
                    and d.get("category_a") != d.get("category_b"))
            ]

            # Semantic decoy verification
            if clean_decoys:
                clean_decoys = _verify_decoys(clean_decoys, data["categories"])
            data["decoys"] = clean_decoys

            # Check 16 unique words
            counts = Counter(all_words)
            dups = [w for w, n in counts.items() if n > 1 and w]
            if dups or len([w for w in all_words if w]) != 16:
                print(f"Duplicate words {dups} or wrong count, retrying…")
                last_data = data
                continue

            print(f"Puzzle accepted on attempt {attempt}")
            _inject_mechanic_tier(data)
            return jsonify(data)

        if last_data:
            _inject_mechanic_tier(last_data)
            return jsonify(last_data)

        return jsonify({"error": "Could not generate a valid puzzle after several attempts. Please try again."}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ─── Regenerate single category ───────────────────────────────────────────────

@app.route("/api/regenerate-category", methods=["GET"])
@require_auth
def regenerate_category():
    difficulty    = request.args.get("difficulty", "medium")
    category_name = request.args.get("category_name", "").strip()

    try:
        banned, _ = _load_banned()
        banned_text = ", ".join(sorted({_normalize(n) for n in banned})) or "none"

        mechanic_list = ", ".join(sorted(_TIER_LOOKUP.keys()))

        if category_name:
            prompt = f"""Generate exactly 4 words for this Connections-style puzzle category.

CATEGORY: {category_name}
DIFFICULTY: {difficulty} (easy=common words, medium=light knowledge, hard=wordplay)

Rules:
- Words must be UPPERCASE
- No word should appear inside the category name itself
- Choose the mechanic from this list that best describes the category: {mechanic_list}

Return ONLY valid JSON:
{{"name": "{category_name}", "difficulty": "{difficulty}", "mechanic": "MECHANIC_NAME", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]}}"""
        else:
            prompt = f"""Create a brand-new category for a Connections-style word puzzle.

BANNED (do not reuse, even rephrased): {banned_text}

Requirements:
- Difficulty: {difficulty}
- Exactly 4 words, UPPERCASE
- Category name: sentence case (e.g. "Things in a junk drawer"), NOT all caps
- Casual register — pop culture, everyday objects, common phrases
- No academic jargon, no "words that are both X and Y"
- Choose the mechanic from this list that best describes the category: {mechanic_list}

Return ONLY valid JSON:
{{"name": "Things in a junk drawer", "difficulty": "{difficulty}", "mechanic": "MECHANIC_NAME", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]}}"""

        data = _call_claude(prompt, max_tokens=300, model=VERIFY_MODEL)

        # Inject tier from lookup; clear any stale mechanic if not in the list
        mechanic = data.get("mechanic")
        if mechanic and mechanic in _TIER_LOOKUP:
            data["tier"] = _TIER_LOOKUP[mechanic]
        else:
            data.pop("mechanic", None)
            data.pop("tier", None)

        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── Health check ─────────────────────────────────────────────────────────────

@app.route("/api/next-date", methods=["GET"])
def next_date():  # public
    """Return the date the next exported puzzle will receive."""
    try:
        existing, _ = gh_read(GROOPED_REPO, PUZZLES_PATH)
        puzzles_list = (
            existing.get("puzzles", []) if isinstance(existing, dict)
            else (existing or [])
        )
        dates = []
        for p in puzzles_list:
            ds = p.get("date", "")
            if ds:
                try:
                    dates.append(datetime.strptime(ds, "%d.%m.%Y"))
                except ValueError:
                    pass
        next_d = (max(dates) + timedelta(days=1)) if dates else datetime.now()
        # No leading zeros: 3.5.2026 not 03.05.2026
        return jsonify({"date": f"{next_d.day}.{next_d.month}.{next_d.year}"})
    except Exception as e:
        return jsonify({"date": None, "error": str(e)}), 500


@app.route("/api/published-dates", methods=["GET"])
def published_dates():
    """Return all published puzzle dates as YYYY-MM-DD strings. Public, no auth."""
    try:
        existing, _ = gh_read(GROOPED_REPO, PUZZLES_PATH)
        puzzles_list = (
            existing.get("puzzles", []) if isinstance(existing, dict)
            else (existing or [])
        )
        dates = []
        for p in puzzles_list:
            d = _parse_any_date(p.get("date", ""))
            if d:
                dates.append(d.strftime("%Y-%m-%d"))
        return jsonify({"dates": sorted(dates)})
    except Exception as e:
        return jsonify({"dates": [], "error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "env": {
        "gemini": bool(GEMINI_API_KEY),
        "github": bool(GITHUB_TOKEN),
        "password": bool(EDITOR_PASSWORD),
    }})

# ─── Vercel entrypoint ────────────────────────────────────────────────────────
# Vercel looks for `app` as the WSGI callable in api/index.py
