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

    verify_prompt = f"""You are a strict fact-checker for a Connections-style word puzzle.

PUZZLE CATEGORIES:
{cats_block}

DECOYS TO VERIFY:
{decoys_block}

For each numbered decoy, decide: does the word GENUINELY and OBVIOUSLY fit BOTH claimed categories using common, primary everyday meanings — not metaphors, not stretches, not niche references, not contrived action-verb uses?

Rules:
- "Fits" means: a random adult hearing "WORD is a [category item]" would immediately nod without needing an explanation.
- The word must have a STANDARD, WELL-KNOWN meaning that places it in that category — not a creative reinterpretation.
- Be especially strict about action verbs used as category items: "SLIDE fits Household Chores because you slide a mop" is INVALID — sliding is not a chore. "LOOP fits Household Chores because cleaning cycles loop" is INVALID — loop is not a chore.
- If the connection requires the solver to think creatively, it is NOT a decoy — it is a fabrication. Drop it.
- It is better to have 0 decoys than 1 false one.

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
            temperature=0.0,
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
You design a casual 4x4 Connections-style word puzzle. Think sitcom, not syllabus — a 12-year-old and their grandparent should both be able to play.

THE PUZZLE SHAPE — HARD RULES (breaking any of these = the puzzle is broken)
- 4 categories × 4 words = 16 words on the board.
- Every one of those 16 words is UNIQUE. No word appears in more than one category. Case-insensitive: "BELL" and "bell" count as the same word.
- Each word has exactly ONE home category. If BELL could plausibly be an "instrument" and a "thing that rings", you still put BELL in exactly one of those categories and fill the other category with a different word.
- Difficulty mix: 1 easy, 2 medium, 1 hard. Difficulty should come from CATEGORY TRICKINESS, not obscure vocabulary.

THE CORE PRINCIPLE — DESIGN AROUND POLYSEMOUS WORDS (without duplicating them!)

The fun of Connections is misdirection: a word that looks like it fits one category actually belongs in another. This only works when your words have multiple common meanings — BUT the word still has ONE true home on the board.

CRITICAL — DO NOT CONFUSE DECOYS WITH DUPLICATES:
- A decoy is a word that a solver might be TEMPTED to put in category B, but whose true home is category A. The word appears ONCE, in category A.
- WRONG: board has BELL in "Instruments" and BELL in "Things that ring" — that's a duplicate, not a decoy. The puzzle is unsolvable.
- RIGHT: BELL sits in "Instruments you play with your hands" (one slot, once). "Things that ring" contains ALARM, PHONE, EARS, CHURCH — completely different words. The decoy note says: "BELL could tempt a solver toward 'Things that ring', but its home is Instruments."

DO IT IN THIS ORDER:
1. Before picking categories, pick 2–3 "anchor" words — short, everyday words that have two or more different common meanings.
   Good anchors: BARK (dog sound / tree), COLD (illness / temperature), BASS (fish / music), PITCHER (baseball / jug), SPRING (season / coil / to jump), DIAMOND (gem / baseball field), CRANE (bird / machine), BOLT (lightning / lock / run), MARS (planet / candy bar), MERCURY (planet / car), JIMMY (name / pry open).
2. For EACH anchor, decide which ONE category is its home. It only goes there once. The other category it "could have fit" is where the decoy tension lives — but that other category is filled with DIFFERENT words.
3. Fill remaining slots with SHORT COMMON words (1–2 syllables, everyday use). A good Connections word has multiple meanings. A bad one (SNICKERDOODLE, TIPTOE) can only ever mean one thing and flattens the puzzle.
4. Before finalizing: list your 16 words on one line. If any word appears twice, the puzzle is invalid — fix it.
5. Never include a word that appears inside its own category name (POP in "Things That Pop" is circular and embarrassing).

WHAT MAKES A CATEGORY GOOD

GOOD category types:
- "Members of a set" when the words are polysemous. NYT does this all the time: "Parts of a piano" (HAMMER, KEY, PEDAL, STRING) works because every word also means something else.
- Fill-in-the-blank: "BREAK ___" (DANCE, UP, FAST, EVEN) or "___ HOUSE" (DOG, TREE, LIGHT, FIRE).
- Named characters sharing a first name: "Characters named Mike" (WAZOWSKI, TYSON, MYERS, PENCE).
- Common phrases/idioms as a group: "Ways to say yes" (SURE, DEAL, BET, GRANTED).
- Things in a specific everyday scene: "Things in a fridge", "Things in a beach bag".

AVOID:
- Academic or specialist jargon — no "Philosophical schools", "Classical tempo markings", "Literary devices", "Logical fallacies", "Fabric weaves", "Architectural orders".
- Categories whose 4 words all share a surface signal (all end in -ism, all Italian, all Greek, all obviously from one jargon). That's a giveaway — the solver spots the pattern before reading the words.
- "Words that are both X and Y" / "Words that can mean both X and Y" — this is overused and just packages the decoy trick as a category. If you want that effect, split into two separate categories and let a decoy connect them.
- Long distinctive words that only mean one thing (SNICKERDOODLE, TIPTOE, SHORTBREAD, CUMULONIMBUS).
- Circular categories where the answer is in the category name.

WHAT MAKES A DECOY REAL

Aim for 2–3 decoys per puzzle. A decoy is a word on the board that genuinely fits TWO of your 4 categories using common everyday meanings.

The mandatory test before listing any decoy:
  Write: "WORD fits [category_a] because ___" (one plain line, common meaning, no stretching)
  Write: "WORD fits [category_b] because ___" (one plain line, different common meaning)
If either sentence is false, metaphorical, or needs more than 12 words to justify — DROP the decoy. A fake decoy is worse than no decoy.

VALID decoy examples:
- BARK — "Bark is the sound a dog makes" ✓ + "Bark is the outer layer of a tree" ✓
- MARS — "Mars is a planet" ✓ + "Mars is a chocolate bar" ✓
- BLUES — "Blues is a music genre" ✓ + "Having the blues means sadness" ✓
- COLD — "A cold is an illness" ✓ + "Cold means low temperature" ✓

INVALID decoy examples (do NOT do this):
- "SLIDE fits Household Chores because you slide a mop" — nobody calls that sliding.
- "PUN fits Things you do to food" — a pun is not something you do to food.
- "NEVER fits Types of Jokes" — no completion works.
- "CARWASH fits Ways to Say No" — carwash has nothing to do with refusal.

GOOD PUZZLE EXAMPLE (this is the target register and decoy density)

CHARACTERS NAMED "MIKE" — WAZOWSKI, TYSON, MYERS, PENCE
THINGS IN A FRIDGE — MILK, EGGS, LEFTOVERS, ICE
WAYS TO SAY "YES" — SURE, DEAL, BET, GRANTED
BREAK ___ — DANCE, UP, FAST, EVEN

Decoys:
- ICE: fits "Things in a fridge" ✓ + fits "BREAK ___" (break the ice) ✓
- BET: fits "Ways to Say Yes" ✓ + fits "BREAK ___" (break a bet? weaker — would be dropped)

BAD PUZZLE EXAMPLE (avoid this)

COMMON KITCHEN HERBS — BASIL, OREGANO, THYME, PARSLEY
PHILOSOPHICAL SCHOOLS — STOICISM, NIHILISM, IDEALISM, REALISM
CLASSICAL TEMPO MARKINGS — ALLEGRO, ANDANTE, PRESTO, LARGO
WORDS THAT ARE BOTH COLORS AND EMOTIONS — BLUE, GREEN, GRAY, BLACK

Why it fails: flat taxonomy, academic jargon, obvious -ism pattern, forbidden "both X and Y" category. No polysemous words = no real decoys possible.

OUTPUT FORMAT
Return ONLY strict JSON, no prose:
{
  "categories": [
    {
      "name": "Short, human-friendly category name that doesn't give away the answer",
      "difficulty": "easy | medium | hard",
      "words": ["WORD1", "WORD2", "WORD3", "WORD4"]
    }
  ],
  "decoys": [
    {
      "word": "WORD",
      "category_a": "Exact name of first matching category",
      "reason_a": "One plain sentence: why this word fits category_a",
      "category_b": "Exact name of second matching category",
      "reason_b": "One plain sentence: why this word fits category_b"
    }
  ],
  "other_trick": "One sentence describing any other overlap or wink on the board (optional)."
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

