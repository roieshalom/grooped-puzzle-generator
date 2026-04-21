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


def generate_connections_puzzle():
    # Load banned categories and normalize them once
    banned = load_banned_categories()
    banned_norm = sorted({normalize_category(name) for name in banned})
    banned_text = ", ".join(banned_norm) if banned_norm else "none"

    # Load (or recompute) embedding vectors for semantic similarity checks
    banned_embeddings = load_banned_embeddings(client)

    # This small block needs string interpolation
    banned_block = f"""
BANNED CATEGORY IDEAS (READ THIS FIRST, BEFORE YOU THINK OF ANY CATEGORY)

The following category ideas have already been used and MUST NOT be reused — not as-is, not rephrased, not shortened, not translated, not with a different angle on the same underlying idea.

Treat them as normalized, lowercase labels representing whole ideas that are off-limits:

{banned_text}

MANDATORY PROCESS (do this in your head before writing any JSON):
1. Brainstorm at least 8–10 candidate category ideas for this puzzle.
2. For EACH candidate, compare it against every item in the banned list above.
   - If the candidate is the same idea, a synonym, a narrower/broader version, a translation, or a "different-angle version" of any banned idea, DISCARD it.
   - Example: if "types of bread" is banned, then "baked goods", "things in a bakery", "sandwich foundations", or "bread varieties" are ALL discarded too.
3. Only after this filter, pick your 4 final categories from the survivors.
4. Before emitting the JSON, re-check each of the 4 chosen category names one more time against the banned list.

If you cannot find 4 survivors, brainstorm more candidates. Do NOT ever output a banned idea.
"""

    # Main prompt is a plain triple-quoted string (NOT an f-string),
    # so the JSON braces remain literal
    prompt = banned_block + """
You create Connections-style 4x4 word puzzles for adults.

GOAL

Create 1 puzzle with 4 categories:
1 easy, 2 medium, 1 hard.
Each category has exactly 4 words (16 total), all words unique (no repeats).
The puzzle should feel fair but non-trivial: familiar words, but not childish textbook lists.

BOARD-LEVEL DESIGN
Think in terms of the whole 16-word board, not separate lists.
Between all 16 words, there should be:
At least 3 and at most 5 genuine decoy words.
A decoy is a word that a reasonable adult solver could seriously place in two different categories that actually exist on THIS board before seeing the solution.

STRICT RULES FOR DECOYS (VERY IMPORTANT):
- A decoy must clearly and concretely fit BOTH of its categories using common, well-known meanings.
- If you are NOT clearly sure that a word obviously belongs in both categories, DO NOT list it as a decoy.
- Prefer fewer, absolutely clear decoys over more, unclear ones.
- Do NOT stretch meanings, invent metaphors, or rely on niche references to make a decoy work.
- Examples of INVALID decoys (do NOT do this):
  - Treating a mythological god as a "tool of persuasion".
  - Treating a planet as a "type of cloud".
  - Treating a cloud type as a "musical term".
- Decoys must be defendable with a short, simple explanation that most adults would agree with.

Decoys must be natural:
Use common meanings or well-known references, not obscure or niche interpretations.
A valid explanation should be short and direct (“X is both a ___ and a ___”), not a long story.
Do not count as decoys:
Connections that need a long or far-fetched explanation.
Vague thematic links like “this feels literary/jazzy/morning-ish” without a concrete shared role.
Design at least one pair of categories that are close in concept (e.g., professions vs tools, genres vs moods, roles vs relationships), so ambiguity arises from related categories, not four unrelated lists.
The “wink” is allowed: small patterns or references that solvers might notice (like BLOOD / SWEAT / TEARS, or BUS / SUB / D-SUB / USB in another puzzle), as long as the final solution is still clear and fair.

CATEGORY STYLE
Avoid school-worksheet and trivia-list categories:
- No simple “types of X / kinds of X / common X / famous X / X terms / X concepts”.
- Especially avoid everyday taxonomy sets like “types of knots”, “types of clouds”, “types of metal”, “types of dance”, “types of hats”, “board game pieces”, “common beverages”, “everyday vehicles”. These are overused and should NOT appear.

FORBIDDEN CATEGORY PATTERN — "dual-meaning" categories:
- DO NOT create any category whose definition is "words that can mean both X and Y", "words that are both X and Y", "words with two meanings: X and Y", "words that work as both X and Y", or any paraphrase of this idea.
- Examples of FORBIDDEN category names (do not use or rephrase):
  - "Words that are both colors and emotions"
  - "Words that can mean both animals and verbs"
  - "Terms that are both sports and cooking actions"
  - "Words that work as both body parts and geography"
- This pattern is overused in our puzzles. The dual-meaning effect should instead come from DECOYS (one word plausibly fitting two real, separate categories on the board), NOT from a category whose entire concept is "words that do double duty".
- If your instinct is to write a "both X and Y" category, redesign it: make X and Y into two separate categories on the board and let one ambiguous word serve as the decoy between them.
Instead, design categories that feel like mini ideas or scenarios, not flat lists:
- Use roles, situations, or specific angles people would talk about (e.g., “Ways people stall for time in meetings”, “Things that come in pairs”, “Phrases you might see on a warning sign”, “Things that can be both literal and metaphorical”).
- Everyday domains (people, culture, body, objects, events) are fine, but give them a clear, grounded twist or scenario instead of pure taxonomy.
At least some categories should cross contexts or meanings, not just list items in the same domain.

GOOD PUZZLE EXAMPLE (IMITATE THIS LEVEL)
This puzzle is a good style example:
BROTHERS — WRIGHT, BLOOD, MARX, WARNER
MUSIC GENRES — BLUES, FOLK, HOUSE, SWING
PHILOSOPHERS — KANT, NIETZSCHE, PLATO, SARTRE
FLUIDS IN OUR BODY — LYMPH, TEARS, SWEAT, SALIVA

Why it works:
The topics are diverse (pop culture, biology, philosophy, music) and require light general knowledge, but nothing too niche.
Words are familiar but not childish (no “dog / cat / red / blue” style lists).
Clear, natural decoys based on overlaps on this board:
BLUES: music genre and part of the expression “having the blues”.
MARX: philosopher and one of the Marx Brothers.
BLOOD: links BROTHERS (blood brothers) and FLUIDS.
BLOOD / SWEAT / TEARS: appear together as a phrase / band name, tempting a solver to group them.
The whole board interacts: the fun comes from placing ambiguous words between real categories on this board, not from obscure tricks.

BAD PUZZLE EXAMPLE (AVOID THIS STYLE)
This puzzle is NOT suitable for adults:
COMMON KITCHEN HERBS — BASIL, OREGANO, THYME, PARSLEY
COLORS ASSOCIATED WITH EMOTIONS OR MOODS — BLUE, GREEN, GRAY, BLACK
WORDS RELATED TO COURTROOM/LEGAL ACTIONS — APPEAL, CHARGE, TRIAL, SENTENCE
COMPOUND WORDS FORMED BY ADDING A TYPE OF TREE — PINEAPPLE, MAPLE, BIRCH, CEDAR

Why it fails:
Categories are flat taxonomies (“common herbs”, “colors”, “legal terms”, “tree compounds”) with no real twist.
There are essentially NO decoys: each category is extremely distinct and solved immediately.
This feels like a vocabulary exercise for kids, not an adult puzzle.
DIFFICULTY MIX

EASY category:
Concrete and recognizable, but not “Common kitchen herbs”, “Colors”, “Common animals”, etc.
May include 1 decoy word that could plausibly fit a harder category.

MEDIUM categories:
Still concrete, may require light general knowledge or mild wordplay.
Should be confusable with at least one other category on this board.

HARD category:
Can be more abstract or wordplay-based.
At least 2 of its words should look like they belong in other categories at first glance.
The underlying idea must be clear and explainable once revealed.

UNIQUENESS & VARIETY
No word may appear more than once in the 16-word grid (case-insensitive).
Avoid repeating the same category idea across puzzles unless the angle is clearly different and more interesting than a simple list.


SELF-CHECK BEFORE OUTPUT
Before you answer, mentally check:

- FIRST: Re-read the BANNED CATEGORY IDEAS list at the top. For each of your 4 chosen category names, confirm it is not the same idea, a paraphrase, a translation, a narrower version, or a "different-angle version" of any banned entry. If any match, replace that category.
- Is any category a "words that are both X and Y" / "words that can mean both X and Y" / "dual-meaning" style category? If yes, redesign it — split into two real categories with a decoy, or replace it entirely.
- Are there 3–5 natural decoys that could belong to two real categories on this board, with short, obvious explanations?
- Are ALL decoys clearly correct, using ordinary meanings that most adults would recognize and agree with?
- Is any category essentially “types of X / common X / famous X / X terms / X concepts” with no twist (like the BAD puzzle above)? If yes, redesign it.
- Are all 16 words unique?
- Are any of the categories just “types of X / common X / famous X / X terms / X concepts”, or obviously about knots, clouds, metals, dances, hats, beverages, vehicles, or game pieces? If yes, redesign them into more interesting, twisted ideas.


OUTPUT FORMAT
Return ONLY strict JSON:
{
  "categories": [
    {
      "name": "Category name (short, human-friendly, does NOT give away the answer immediately)",
      "difficulty": "easy | medium | hard",
      "words": ["word1", "word2", "word3", "word4"]
    }
  ],
  "decoys": [
    {
      "word": "WORD",
      "category_a": "First category name",
      "category_b": "Second category name"
    }
  ],
  "other_trick": "Very short description (one sentence) of any other decoy pattern or overlap."
}

No extra text, no explanations, just JSON.
"""

    # Loop until we get a puzzle with NO banned categories.
    # Prefer 16 unique words, but stop after max_attempts and
    # allow some duplicates rather than looping forever.
    attempt = 0
    max_attempts = 12
    last_no_banned = None  # puzzle with no banned categories, may have duplicates

    while attempt < max_attempts:
        attempt += 1
        print(f"Puzzle generation attempt {attempt}")

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are an expert Grooped puzzle generator."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
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

        if len(words) == 16 and len(set(words)) == 16:
            print(f"Puzzle accepted after {attempt} attempts (no banned categories, all words unique)")
            return data

        print("Puzzle has no banned categories but duplicate/missing words")
        last_no_banned = data
        # Try again to get fully unique words
        continue

    # Fallback: accept best puzzle with NO banned categories, even if duplicates
    if last_no_banned is not None:
        print(
            f"Puzzle accepted after {attempt} attempts with duplicates "
            "(no fully-unique puzzle without banned categories found)"
        )
        return last_no_banned

    # Extreme fallback: should almost never happen
    print(f"Puzzle accepted after {attempt} attempts (no clean candidate; returning last)")
    return data

