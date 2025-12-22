import os
import json
from datetime import datetime, timedelta
from openai import OpenAI

# API key comes from environment (set OPENAI_API_KEY in GitHub secrets / local env)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def generate_connections_puzzle():
    prompt = """
You create “Connections”-style word puzzles for adults.

GOAL
- Create one 4x4 Connections-style puzzle with:
  - 1 easy category,
  - 2 medium categories,
  - 1 hard category.
- Each category must have exactly 4 words (16 total).
- The puzzle should feel fair but non-trivial for adults.

ALLOWED CATEGORY TYPES (PATTERNS TO IMITATE, NOT COPY)
BASIC TAXONOMY (EVERYDAY CATEGORIES)
- Animals: mammals, birds, insects, sea creatures, farm animals, pets.
- Foods & drinks: fruits, vegetables, meats, dairy, beverages, cuisines.
- Colors and shades.
- Body parts.
- Plants & nature (trees, flowers, natural phenomena).
- Objects & places: furniture, clothing, vehicles, tools, geographic locations.

PROFESSIONAL & ACADEMIC
- Occupations and roles (medical, legal, educational, technical, etc.).
- Academic subjects (STEM, humanities, languages, arts).
- Sports terms, positions, or equipment.

FUNCTIONAL CATEGORIES (ACTIONS & PROPERTIES)
- Action-based: things you can “break” (record, silence, dawn, fast), “catch” (ball, cold, fire, breath), “draw” (picture, card, curtain, blood), “run” (business, race, water), etc.
- Property-based: things that are hot/cold/sharp/round/soft, heavy/light, loud/quiet, etc.

WORDPLAY & LINGUISTIC TRICKS
- Word structure: palindromes, anagrams, rhyming words, homophones, alliteration.
- Compound words & phrases: words that can go before/after a common word (like FIRE-: ant, drill, island, opal), fill‑in‑the‑blank phrases (“RAIN___”: bow, coat, forest, maker), words that follow a given word, hidden compounds.
- Letter/number play: shared letter patterns, words formed by adding/removing a letter.

CULTURAL & KNOWLEDGE-BASED
- Entertainment: movie or TV franchises and characters, music genres, song or album titles, book titles, video or board games.
- Brands & companies: tech companies, car brands, fashion brands, fast food chains, etc.
- Historical & cultural: historical figures, leaders, mythology and folklore, well-known actors/musicians/athletes, fairy-tale or story characters.

ABSTRACT & CONCEPTUAL
- Emotions & mental states (happy, sad, anxious, calm, etc.).
- Personality traits.
- Time & measurement: time periods, units, dates, seasons, eras.
- Thematic sets: wedding-related, school-related, weather-related, money-related, types of “language”, etc.
- Idioms & expressions, slang terms, phrasal verbs.
- Multiple-meaning words or context-dependent words.

DIFFICULTY MIX
- EASY category:
  - Concrete and recognizable, but avoid trivial “kids’ list” themes like “Common fruits”, “Common animals”, “Primary colors”, “Kitchen utensils”, or “Common pets”.
- MEDIUM categories:
  - Still concrete, but require either light general knowledge or mild wordplay.
  - Should feel somewhat confusable with at least one other category.
- HARD category:
  - Abstract or wordplay-based.
  - At least 2 of its words should look like they belong in some other category at first glance.
  - Not just another straightforward list (avoid plain “Classical composers”, “Types of birds”, etc., as the hard group).

COLOR ASSIGNMENT RULES
- Assign one of [yellow, green, blue, purple] to each category.
- Each category must have a different color (all 4 colors used exactly once).
- Color is purely visual and does NOT need to correlate with difficulty.

MISDIRECTING / TEMPTATION WORDS
- Design the puzzle so that 2–4 of the 16 words LOOK like they could belong to a different, obvious category, but actually belong only to their true category.
- Example pattern (do NOT copy literally):
  - There might be 5 color words overall, but only 4 belong to the “Colors” category; the extra color word belongs to a different category.
- Use such misdirections so categories feel slightly entangled, but the final solution must still feel fair.

UNIQUENESS & VARIETY RULES
- Within a single puzzle:
  - Do NOT repeat the same high-level category idea twice (no two “Classical composers”, no two “Words that can follow LIGHT”, etc.).
  - Do NOT reuse any word in more than one category.
- Across puzzles in general:
  - Avoid overusing identical patterns like “Words that can follow FIRE/LIGHT/BREAK”, “Types of clouds”, “Common fruits”, “Common pets”, “Common colors”.
  - If you revisit a broad theme (like music, weather, colors), twist it into a clearly different and more challenging angle.

QUALITY CHECK BEFORE OUTPUT
- Check that:
  - Categories are distinguishable once their ideas are revealed, even if they look similar at first.
  - There is at least one temptation word that looks like it belongs in another group but ends up in just one.
  - No two categories are essentially the same idea with different wording.
  - No word is duplicated across categories.
- If the puzzle feels trivial, repetitive, or too similar to standard textbook lists, revise it mentally and only then output the JSON.

OUTPUT FORMAT
Return the result ONLY as strict JSON with this exact structure:
{
  "categories": [
    {
      "name": "Category name (short, human-friendly, does NOT give away the answer immediately)",
      "difficulty": "easy | medium | hard",
      "words": ["word1", "word2", "word3", "word4"]
    }
  ]
}
No extra text, no explanations, just JSON.
"""
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are an expert Connections puzzle generator."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        response_format={"type": "json_object"},
    )
    puzzle_json = response.choices[0].message.content
    return json.loads(puzzle_json)


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
