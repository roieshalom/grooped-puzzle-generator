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
      "home": "Metaphors for being in trouble",
      "tempts_toward": "Things that jingle in your pocket",
      "why": "Solvers might think of jam jars or food in their pocket before reading JAM as 'in a jam'."
    },
    {
      "word": "BET",
      "home": "Ways to say yes",
      "tempts_toward": "DEAD ___",
      "why": "DEAD BET isn't a phrase, but the word feels gambly enough that solvers may try it there."
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

Rules:
- Words must be UPPERCASE
- No word should appear inside the category name itself

Return ONLY valid JSON:
{{"name": "{category_name}", "difficulty": "{difficulty}", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]}}"""
        else:
            prompt = f"""Create a brand-new category for a Connections-style word puzzle.

BANNED (do not reuse, even rephrased): {banned_text}

Requirements:
- Difficulty: {difficulty}
- Exactly 4 words, UPPERCASE
- Category name: sentence case (e.g. "Things in a junk drawer"), NOT all caps
- Casual register — pop culture, everyday objects, common phrases
- No academic jargon, no "words that are both X and Y"

Return ONLY valid JSON:
{{"name": "Things in a junk drawer", "difficulty": "{difficulty}", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]}}"""

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
