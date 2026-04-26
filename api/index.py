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

import anthropic
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
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
GEN_MODEL    = os.environ.get("GEN_MODEL", "claude-sonnet-4-5")
VERIFY_MODEL = os.environ.get("VERIFY_MODEL", "claude-haiku-4-5")

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

    # Write draft to GitHub
    try:
        _, sha = gh_read(GENERATOR_REPO, DRAFT_PATH)
        gh_write(GENERATOR_REPO, DRAFT_PATH, puzzle, sha, "Update draft puzzle")
    except Exception as e:
        print(f"Draft save to GitHub failed (non-fatal): {e}")

    return jsonify({"ok": True, "puzzle": puzzle})

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

    puzzle["status"] = "published"
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

# ─── Anthropic helpers ────────────────────────────────────────────────────────

def _anthropic_client():
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def _call_claude(prompt: str, max_tokens: int = 3000, model: str = None) -> dict:
    """Call Claude and parse JSON from the response."""
    model = model or GEN_MODEL
    ac = _anthropic_client()
    message = ac.messages.create(
        model=model,
        max_tokens=max_tokens,
        system="You are an expert Grooped puzzle generator. Return valid JSON only, no prose.",
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract first {...} block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())

    raise ValueError(f"Could not parse JSON from Claude response: {text[:300]}")

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

    return f"""ALREADY-USED CATEGORIES — AVOID THESE AND ANYTHING SIMILAR

~{len(banned_norm)} categories have been used. Do not reuse any, even rephrased.
{preview_text}

---
Design a casual 4x4 Connections-style word puzzle. Register: sitcom, not syllabus.

FOLLOW THIS DESIGN PROCESS:

STEP 1 — PICK 2-3 ANCHOR WORDS FIRST (before touching categories)
An anchor is a short, everyday word with two genuinely different common meanings.
Strong anchors: BARK (dog sound / tree skin), SPRING (season / coil / jump), COLD (illness / temperature), BASS (fish / music), TRUNK (elephant / tree / car / swimwear), CRANE (bird / machine), BOLT (lightning / lock / sprint), DIAMOND (gem / baseball field), PITCHER (jug / baseball), CHIP (snack / microchip / token), LIGHT (lamp / not heavy / pale), CLUB (nightclub / golf / suit / weapon), DRAFT (beer / wind / military / writing).

STEP 2 — ASSIGN EACH ANCHOR A SINGLE HOME CATEGORY
Each anchor goes in exactly ONE category. Its other meaning creates decoy tension. Do NOT put the anchor in two categories.
Example: BARK goes home to "Sounds animals make". There's also a "Parts of a tree" category (ROOT, SAP, BRANCH, RING) — BARK is NOT in it. The tension IS the decoy.

STEP 3 — BUILD 4 CATEGORIES AROUND YOUR ANCHORS
Best types:
- Scene: "Things in a junk drawer", "What's on a hot dog"
- Fill-in-the-blank: "BREAK ___" (DANCE, UP, FAST, EVEN), "___ STONE" (CORN, LIME, SAND, SUN)
- Pop-culture: "Sitcom Dads", "Characters named Jake", "SNL cast members"
- Wordplay: "Homophones of numbers", "Words that sound like letters"
- Phrases: "Ways to say no", "Things you do at a red light"

AVOID: Academic jargon (no "Philosophical schools", "Tempo markings", "Literary devices"). Categories where all 4 words share a surface giveaway (all -ism, all Italian, all scientific). "Words that are both X and Y" (forbidden). Long one-meaning words (SNICKERDOODLE, TIPTOE). Word inside its own category name (POP in "Things that Pop").

STEP 4 — FILL REMAINING SLOTS with short common words (prefer polysemous).

STEP 5 — UNIQUENESS CHECK: Every one of the 16 board words must be unique (case-insensitive). List all 16 in thinking.all_16_words and fix any duplicates before proceeding.

GOOD EXAMPLE:
thinking.anchors: [{{word:"ICE", home:"Things in a fridge", meaning_a:"frozen water", tempts_toward:"BREAK ___", meaning_b:"break the ice"}}, {{word:"DEAL", home:"Ways to say yes", meaning_a:"deal = I agree", tempts_toward:"BREAK ___", meaning_b:"break a deal"}}]
thinking.all_16_words: WAZOWSKI TYSON MYERS PENCE MILK EGGS LEFTOVERS ICE SURE DEAL BET GRANTED DANCE UP FAST EVEN

CHARACTERS NAMED "MIKE" — WAZOWSKI, TYSON, MYERS, PENCE (medium)
THINGS IN A FRIDGE — MILK, EGGS, LEFTOVERS, ICE (easy)
WAYS TO SAY "YES" — SURE, DEAL, BET, GRANTED (medium)
BREAK ___ — DANCE, UP, FAST, EVEN (hard)
Decoys: ICE (fridge / break the ice), DEAL (yes / break a deal)

BAD EXAMPLE (avoid): KITCHEN HERBS / PHILOSOPHICAL SCHOOLS / TEMPO MARKINGS / WORDS THAT ARE BOTH COLORS AND EMOTIONS
Why it fails: flat taxonomy, academic jargon, giveaway suffixes, forbidden pattern.

OUTPUT FORMAT — Return ONLY valid JSON:
{{
  "thinking": {{
    "anchors": [
      {{
        "word": "ANCHOR_WORD",
        "meaning_a": "what it means in its home category",
        "home_category": "name of category it lives in",
        "meaning_b": "other common meaning",
        "tempts_toward": "category name it might tempt solvers toward"
      }}
    ],
    "all_16_words": "ALL 16 BOARD WORDS space-separated — check for duplicates"
  }},
  "categories": [
    {{
      "name": "Short human-friendly name",
      "difficulty": "easy | medium | hard",
      "words": ["WORD1", "WORD2", "WORD3", "WORD4"]
    }}
  ],
  "decoys": [
    {{
      "word": "ANCHOR_WORD",
      "category_a": "Exact true home category name",
      "reason_a": "One plain sentence why this word belongs here",
      "category_b": "Exact category name it tempts toward",
      "reason_b": "One plain sentence why solvers will be tempted"
    }}
  ],
  "other_trick": "Optional: one sentence on any other misdirection."
}}"""

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

            # Strip structurally invalid decoys
            board_set = {w for w in all_words if w}
            cat_names = {cat.get("name", "").strip() for cat in data["categories"]}
            clean_decoys = [
                d for d in data.get("decoys", [])
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
            return jsonify(data)

        if last_data:
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

        if category_name:
            prompt = f"""Generate exactly 4 words for this Connections-style puzzle category.

CATEGORY: {category_name}
DIFFICULTY: {difficulty} (easy=common words, medium=light knowledge, hard=wordplay)

Return ONLY valid JSON:
{{"name": "{category_name}", "difficulty": "{difficulty}", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]}}"""
        else:
            prompt = f"""Create a brand-new category for a Connections-style word puzzle.

BANNED (do not reuse, even rephrased): {banned_text}

Requirements:
- Difficulty: {difficulty}
- Exactly 4 words, UPPERCASE
- Casual register — pop culture, everyday objects, common phrases
- No academic jargon, no "words that are both X and Y"

Return ONLY valid JSON:
{{"name": "Category name", "difficulty": "{difficulty}", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]}}"""

        data = _call_claude(prompt, max_tokens=200, model=VERIFY_MODEL)
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


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "env": {
        "anthropic": bool(ANTHROPIC_API_KEY),
        "github": bool(GITHUB_TOKEN),
        "password": bool(EDITOR_PASSWORD),
    }})

# ─── Vercel entrypoint ────────────────────────────────────────────────────────
# Vercel looks for `app` as the WSGI callable in api/index.py
