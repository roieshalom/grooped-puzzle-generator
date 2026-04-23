import os
import json
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv
from banned_categories import (
    load_banned_categories,
    load_banned_embeddings,
    find_semantically_banned,
    normalize_category,
)

load_dotenv()  # This loads the .env file

# API key comes from environment (set OPENAI_API_KEY in GitHub secrets / local env)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _verify_decoys_semantically(decoys, categories, client):
    """
    Ask a second LLM call to fact-check each decoy's claimed connections.
    Returns only the decoys that pass the check.
    """
    if not decoys:
        return decoys

    # Build a compact description of the puzzle categories for context
    cat_lines = []
    for cat in categories:
        words_str = ", ".join(cat.get("words", []))
        cat_lines.append(f'- "{cat["name"]}": {words_str}')
    cats_block = "\n".join(cat_lines)

    # Build the list of decoys to check
    decoy_lines = []
    for i, d in enumerate(decoys, 1):
        reason_a = d.get("reason_a", "")
        reason_b = d.get("reason_b", "")
        decoy_lines.append(
            f'{i}. Word: {d["word"]}\n'
            f'   Claimed fit A — "{d["category_a"]}": {reason_a}\n'
            f'   Claimed fit B — "{d["category_b"]}": {reason_b}'
        )
    decoys_block = "\n".join(decoy_lines)

    verify_prompt = f"""You are a fact-checker for a Connections-style word puzzle.

PUZZLE CATEGORIES:
{cats_block}

DECOYS TO VERIFY:
{decoys_block}

For each numbered decoy, decide: does the word GENUINELY fit BOTH claimed categories using well-known everyday meanings?

Rules:
- "Fits" means a regular adult would immediately recognize the connection — no obscure trivia, no creative stretching.
- A word CAN fit a category even if it's not the most typical member, as long as the connection is universally understood (e.g. ICE fits "Things in a fridge" even though it's in the freezer compartment — everyone gets it).
- INVALID: "SLIDE fits Household Chores because you slide a mop" — sliding is not a chore.
- INVALID: "PUN fits Things you do to food" — a pun is not something you do to food.
- VALID: "BARK fits Sounds animals make" + "BARK fits Parts of a tree" — both meanings are universally known.
- When in doubt, lean toward keeping the decoy. A decoy that is slightly generous is better than an empty decoy list.

Return ONLY a JSON object with this structure:
{{
  "verdicts": [
    {{"index": 1, "keep": true, "reason": "one line explaining why both fits are genuine"}},
    {{"index": 2, "keep": false, "reason": "one line explaining which fit is false and why"}}
  ]
}}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a strict fact-checker. Return only valid JSON."},
                {"role": "user", "content": verify_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        verdicts = {v["index"]: v["keep"] for v in result.get("verdicts", [])}

        verified = []
        for i, decoy in enumerate(decoys, 1):
            keep = verdicts.get(i, True)  # default keep if verdict missing
            if keep:
                verified.append(decoy)
            else:
                reason = next(
                    (v.get("reason", "") for v in result.get("verdicts", []) if v["index"] == i),
                    ""
                )
                print(f"Dropped decoy '{decoy['word']}' (semantic check failed): {reason}")

        print(f"Semantic decoy check: {len(verified)}/{len(decoys)} passed")
        return verified

    except Exception as e:
        # If verification fails for any reason, return originals rather than losing all decoys
        print(f"Decoy semantic check failed ({e}), keeping all structurally valid decoys")
        return decoys


def generate_connections_puzzle():
    import random

    # Load banned categories and normalize them once
    banned = load_banned_categories()
    banned_norm = sorted({normalize_category(name) for name in banned})

    # Load (or recompute) embedding vectors for semantic similarity checks
    banned_embeddings = load_banned_embeddings(client)

    # Build a SAMPLED banned list for the prompt. The full list (1000+) is too
    # large to include in every prompt and the model can't meaningfully scan
    # it all anyway — the semantic embedding check on the Python side is what
    # actually enforces the ban. Include the 60 most recently added (to catch
    # near-duplicates of recent puzzles) plus 40 random samples (to show the
    # ban breadth to the model).
    recent = banned_norm[-60:] if len(banned_norm) > 60 else banned_norm
    remaining = [c for c in banned_norm if c not in set(recent)]
    sample_size = min(40, len(remaining))
    sampled = random.sample(remaining, sample_size) if remaining else []
    banned_preview = sorted(set(recent) | set(sampled))
    banned_preview_text = ", ".join(banned_preview) if banned_preview else "none"

    banned_block = f"""
ALREADY-USED CATEGORIES — AVOID THESE AND ANYTHING SIMILAR

We have a database of ~{len(banned_norm)} categories that have been used in past puzzles. Below is a representative sample. Do not reuse any of these ideas, even rephrased, narrower, broader, or from a different angle.

{banned_preview_text}

A system check will also catch paraphrases using semantic similarity — so aim for genuinely fresh ideas, not clever reskins.
"""

    # PORTFOLIO_START — do not remove: used by roiesh.com/grooped.html to display this prompt live
    # Main prompt is a plain triple-quoted string (NOT an f-string),
    # so the JSON braces remain literal
    prompt = banned_block + """
Design a casual 4x4 Connections-style word puzzle. Register: sitcom, not syllabus. A teenager and their grandparent should both get it.

============================
FOLLOW THIS DESIGN PROCESS
============================

STEP 1 — PICK 2-3 ANCHOR WORDS FIRST (before touching categories)
An anchor is a short, everyday word with two genuinely different common meanings.
Pick ones where both meanings are so obvious that a stranger wouldn't need an explanation.

Strong anchors: BARK (dog sound / tree skin), SPRING (season / coil / to jump), COLD (illness / temperature), BASS (fish / music), TRUNK (elephant / tree / car / swimwear), CRANE (bird / machine), BOLT (lightning / door lock / sprint), DIAMOND (gem / baseball field), PITCHER (jug / baseball), CHIP (snack / microchip / casino token), LIGHT (lamp / not heavy / pale), CLUB (nightclub / golf / suit / weapon), DRAFT (beer / wind / military / writing).

STEP 2 — ASSIGN EACH ANCHOR A SINGLE HOME CATEGORY
Each anchor goes in exactly ONE category. Its other meaning creates decoy tension — solvers will be tempted to file it in the wrong category. That temptation IS the decoy. You do NOT put the anchor in two categories.

Example: BARK goes home to "Sounds animals make". There is also a "Parts of a tree" category, but BARK is not in it — ROOT, SAP, BRANCH, RING are. The decoy: solvers see BARK and want to put it in the tree category. One word, one home, one beautiful trap.

STEP 3 — BUILD 4 CATEGORIES AROUND YOUR ANCHORS
Mix category types. Best types:
- Things in a specific scene: "Things in a junk drawer", "What's on a hotdog"
- Fill-in-the-blank: "BREAK ___" (DANCE, UP, FAST, EVEN), "___ STONE" (CORN, LIME, SAND, SUN)
- Pop-culture set: "Sitcom Dads", "Characters named Jake", "Saturday Night Live cast members"
- Wordplay: "Homophones of numbers", "___ + HOUSE", "Words that sound like letters"
- Everyday phrases: "Ways to say no", "Things you do at a red light"

AVOID:
- Academic or jargon categories (no "Philosophical schools", "Tempo markings", "Literary devices", "Logical fallacies", "Fabric weaves")
- Any category where all 4 words share a telltale surface feature (all end in -ism, all Italian musical terms, all scientific Latin). Those are giveaways.
- "Words that are both X and Y" — forbidden. Split into two real categories instead.
- Long words that can only mean one thing (SNICKERDOODLE, TIPTOE, CUMULONIMBUS). Prefer 1-2 syllable everyday words.
- A word that appears inside its own category name (POP in "Things that Pop").

STEP 4 — FILL REMAINING SLOTS
Prefer short common words. Favor polysemous words even in non-anchor slots — they create ambient misdirection.

STEP 5 — UNIQUENESS CHECK
Every one of the 16 board words must be unique (case-insensitive). List all 16 in your thinking field. If any word appears twice, fix it before outputting categories.

============================
TARGET QUALITY: THIS IS GOOD
============================

thinking.anchors: [{word:"ICE", home:"Things in a fridge", meaning_a:"frozen water stored in a fridge", tempts_toward:"BREAK ___", meaning_b:"break the ice"}, {word:"DEAL", home:"Ways to say yes", meaning_a:"deal = yes, I agree", tempts_toward:"BREAK ___", meaning_b:"break a deal"}]
thinking.all_16_words: WAZOWSKI TYSON MYERS PENCE MILK EGGS LEFTOVERS ICE SURE DEAL BET GRANTED DANCE UP FAST EVEN

CHARACTERS NAMED "MIKE" — WAZOWSKI, TYSON, MYERS, PENCE  (medium)
THINGS IN A FRIDGE — MILK, EGGS, LEFTOVERS, ICE  (easy)
WAYS TO SAY "YES" — SURE, DEAL, BET, GRANTED  (medium)
BREAK ___ — DANCE, UP, FAST, EVEN  (hard)

Decoys: ICE (fridge / break the ice), DEAL (yes / break a deal), BET (yes / break a bet)
Why it works: four categories that seem independent but share anchor words with dual meanings. No word appears twice. 3 real decoys.

============================
THIS IS BAD — DO NOT DO THIS
============================

KITCHEN HERBS — BASIL, OREGANO, THYME, PARSLEY
PHILOSOPHICAL SCHOOLS — STOICISM, NIHILISM, IDEALISM, REALISM
TEMPO MARKINGS — ALLEGRO, ANDANTE, PRESTO, LARGO
WORDS THAT ARE BOTH COLORS AND EMOTIONS — BLUE, GREEN, GRAY, BLACK

Why it fails: flat taxonomy, academic jargon, surface giveaways (-ism), forbidden "both X and Y" pattern. No anchor words, no real decoys possible.

============================
OUTPUT FORMAT
============================
Return ONLY valid JSON with this exact structure. Fill in "thinking" first — it is your scratchpad and must come before "categories":

{
  "thinking": {
    "anchors": [
      {
        "word": "ANCHOR_WORD",
        "meaning_a": "what it means in its home category",
        "home_category": "name of the category it actually lives in",
        "meaning_b": "the other common meaning that creates decoy tension",
        "tempts_toward": "name of the category solvers will wrongly try"
      }
    ],
    "all_16_words": "LIST ALL 16 BOARD WORDS HERE space-separated — check for duplicates before proceeding"
  },
  "categories": [
    {
      "name": "Short human-friendly name",
      "difficulty": "easy | medium | hard",
      "words": ["WORD1", "WORD2", "WORD3", "WORD4"]
    }
  ],
  "decoys": [
    {
      "word": "ANCHOR_WORD",
      "category_a": "Exact name of its true home category",
      "reason_a": "One plain sentence: why this word belongs here",
      "category_b": "Exact name of the category it tempts toward",
      "reason_b": "One plain sentence: why solvers will be tempted by this"
    }
  ],
  "other_trick": "Optional: one sentence on any other overlap or misdirection on the board."
}
"""
    # PORTFOLIO_END — do not remove: used by roiesh.com/grooped.html to display this prompt live

    # Loop until we get a puzzle with NO banned categories AND 16 unique words.
    # Duplicates make the puzzle literally unsolvable, so we do NOT fall back
    # to accepting a duplicate-word puzzle — we retry until clean or we exhaust
    # attempts. Each attempt costs ~8-15 seconds; max_attempts=6 caps total
    # time around 60-90 seconds.
    attempt = 0
    max_attempts = 6
    last_no_banned = None  # puzzle with no banned categories, may have duplicates

    while attempt < max_attempts:
        attempt += 1
        print(f"Puzzle generation attempt {attempt}")

        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "You are an expert Grooped puzzle generator."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            response_format={"type": "json_object"},
        )
        puzzle_json = response.choices[0].message.content
        data = json.loads(puzzle_json)

        # Check for banned categories first (hard constraint)
        banned_set = set(banned_norm)
        has_banned = False
        for cat in data["categories"]:
            name = cat.get("name", "")
            if normalize_category(name) in banned_set:
                has_banned = True
                print(f"Rejected puzzle (banned category): {name}")
                break

        if has_banned:
            # Never accept puzzles with banned categories
            continue

        # Semantic similarity check — catch paraphrases of banned ideas
        has_semantic_banned = False
        for cat in data["categories"]:
            name = cat.get("name", "")
            matched, sim = find_semantically_banned(name, banned_embeddings, client)
            if matched is not None:
                has_semantic_banned = True
                print(
                    f"Rejected puzzle (semantically banned): '{name}' "
                    f"≈ '{matched}' (similarity {sim:.3f})"
                )
                break

        if has_semantic_banned:
            continue

        # At this point, NO banned categories (exact or semantic)
        # Check uniqueness of words (soft constraint)
        words = []
        for cat in data["categories"]:
            for w in cat["words"]:
                words.append(w.upper().strip())

        # Reject puzzles where any word appears in its own category name (circular / too obvious)
        has_circular = False
        for cat in data["categories"]:
            cat_name_upper = cat.get("name", "").upper()
            for w in cat.get("words", []):
                if w.upper().strip() in cat_name_upper.split():
                    print(f"Rejected puzzle: '{w}' appears in its own category name '{cat['name']}'")
                    has_circular = True
                    break
            if has_circular:
                break
        if has_circular:
            continue

        # Validate and strip bogus decoys before returning.
        # A decoy is only kept if:
        #   1. Its word appears in the 16-board words (case-insensitive)
        #   2. Both category_a and category_b are real category names in this puzzle
        board_words_upper = {w.upper() for w in words}
        category_names = {cat.get("name", "").strip() for cat in data["categories"]}
        clean_decoys = []
        for decoy in data.get("decoys", []):
            dword = (decoy.get("word") or "").upper().strip()
            cat_a = (decoy.get("category_a") or "").strip()
            cat_b = (decoy.get("category_b") or "").strip()
            if dword not in board_words_upper:
                print(f"Dropped decoy '{dword}': word not on the board")
                continue
            if cat_a not in category_names:
                print(f"Dropped decoy '{dword}': category_a '{cat_a}' not a real category")
                continue
            if cat_b not in category_names:
                print(f"Dropped decoy '{dword}': category_b '{cat_b}' not a real category")
                continue
            if cat_a == cat_b:
                print(f"Dropped decoy '{dword}': category_a and category_b are the same")
                continue
            clean_decoys.append(decoy)
        dropped = len(data.get("decoys", [])) - len(clean_decoys)
        if dropped:
            print(f"Stripped {dropped} structurally invalid decoy(s); {len(clean_decoys)} remain")

        # Semantic verification pass — ask a second LLM call to fact-check each decoy.
        # This catches hallucinated connections that pass structural checks
        # (e.g. "PUN fits Things you do to food" — structurally valid, semantically false).
        if clean_decoys:
            clean_decoys = _verify_decoys_semantically(clean_decoys, data["categories"], client)

        data["decoys"] = clean_decoys

        if len(words) == 16 and len(set(words)) == 16:
            print(f"Puzzle accepted after {attempt} attempts (no banned categories, all words unique)")
            return data

        # Report exactly which words duplicated, so the log is useful
        from collections import Counter
        dup_counter = Counter(words)
        dups = [w for w, n in dup_counter.items() if n > 1]
        print(
            f"Puzzle rejected: duplicate words on board {dups} "
            f"(16 slots but only {len(set(words))} unique words). Retrying…"
        )
        last_no_banned = data
        # Try again to get fully unique words
        continue

    # Exhausted attempts. We refuse to ship a puzzle with duplicate words
    # because it would be unsolvable. Surface a clear error instead of a
    # silently-broken puzzle.
    if last_no_banned is not None:
        raise RuntimeError(
            f"Could not generate a puzzle with 16 unique words after {max_attempts} attempts. "
            f"Model keeps placing the same word in multiple categories. Try again."
        )

    raise RuntimeError(
        f"Could not generate any valid puzzle after {max_attempts} attempts."
    )

