import os
import json
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv
from banned_categories import load_banned_categories, normalize_category

load_dotenv()  # This loads the .env file

# API key comes from environment (set OPENAI_API_KEY in GitHub secrets / local env)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def generate_connections_puzzle():
    # Load banned categories and normalize them once
    banned = load_banned_categories()
    banned_norm = sorted({normalize_category(name) for name in banned})
    banned_text = ", ".join(banned_norm) if banned_norm else "none"

    # This small block needs string interpolation
    banned_block = f"""
BANNED CATEGORY IDEAS (DO NOT USE)

The following category ideas are already used and must be avoided, even with different capitalization or slightly different wording.
Treat them as normalized, lowercase labels that represent whole ideas you must not reuse:

{banned_text}

You must not create categories that are essentially the same idea as any of these banned ones, even if you rephrase or shorten the title.
"""

    # Main prompt is a plain triple-quoted string (NOT an f-string),
    # so the JSON braces remain literal
    prompt = """
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

No simple “types of X / kinds of X / common X / famous X / X terms / X concepts”.

Avoid basic, instantly-recognizable sets like “Common kitchen herbs”, “Colors”, “Card games”, “Legal terms”, unless they are twisted into a specific, surprising angle.

Categories should feel like something an adult would enjoy:

Everyday domains (people, culture, body, objects, events) are fine.

Give them a clear, grounded twist or scenario instead of flat taxonomy.

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
""" + banned_block + """
SELF-CHECK BEFORE OUTPUT
Before you answer, mentally check:

- Are there 3–5 natural decoys that could belong to two real categories on this board, with short, obvious explanations?
- Are ALL decoys clearly correct, using ordinary meanings that most adults would recognize and agree with?
- Is any category essentially “types of X / common X / famous X / X terms / X concepts” with no twist (like the BAD puzzle above)? If yes, redesign it.
- Does any category idea match or closely resemble any of the banned ideas listed above? If yes, redesign it.
- Are all 16 words unique?

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

    # Loop until we get 16 unique words AND no banned categories
    attempt = 0
    while True:
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

        # HARD uniqueness check – no repeated word string in the 16‑word grid
        words = []
        for cat in data["categories"]:
            for w in cat["words"]:
                words.append(w.upper().strip())

        if len(words) != 16 or len(set(words)) != 16:
            print("Rejected puzzle (duplicate or missing words)")
            continue

        # Check categories against banned list using normalization
        banned_set = set(banned_norm)
        has_banned = False
        for cat in data["categories"]:
            name = cat.get("name", "")
            if normalize_category(name) in banned_set:
                has_banned = True
                print(f"Rejected puzzle (banned category): {name}")
                break

        if has_banned:
            continue

        print(f"Puzzle accepted after {attempt} attempts")
        return data

def build_week_of_puzzles(start_id=1, start_date_str="11.12.2025", language="en"):
    day = datetime.strptime(start_date_str, "%d.%m.%Y")
    puzzles = []

    for i in range(7):
        raw = generate_connections_puzzle()
        difficulty_map = {
            "easy": "yellow",
            "medium": "green",
            "hard": "blue",  # adjust to yellow/green/blue/purple scheme as you like
        }

        categories = []
        for cat in raw["categories"]:
            diff = cat.get("difficulty", "medium")
            color = difficulty_map.get(diff, "green")
            words_upper = [w.upper() for w in cat["words"]]
            categories.append(
                {
                    "name": cat["name"],
                    "words": words_upper,
                    "difficulty": color,
                }
            )

        puzzles.append(
            {
                "id": str(start_id + i),
                "date": day.strftime("%d.%m.%Y"),
                "language": language,
                "categories": categories,
            }
        )

        day += timedelta(days=1)

    return puzzles


if __name__ == "__main__":
    week = build_week_of_puzzles(start_id=2, start_date_str="11.12.2025", language="en")
    with open("puzzles_week.json", "w", encoding="utf-8") as f:
        json.dump(week, f, ensure_ascii=False, indent=2)
    print("Saved 7 puzzles to puzzles_week.json")
