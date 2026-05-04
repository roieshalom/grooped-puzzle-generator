#!/usr/bin/env python3
"""Generate a single category for regeneration."""

import os
import re
import json
import google.generativeai as genai
from dotenv import load_dotenv

def _configure_genai():
    """Configure Gemini with API key loaded from .env or environment"""
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        load_dotenv()
        env_path = os.path.join(script_dir, '.env')
        load_dotenv(dotenv_path=env_path, override=False)
        api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(script_dir, '.env')
        raise ValueError(
            f"GEMINI_API_KEY not found. Either:\n"
            f"1. Set it as an environment variable: export GEMINI_API_KEY=your_key\n"
            f"2. Create a .env file at {env_path} with: GEMINI_API_KEY=your_key"
        )

    genai.configure(api_key=api_key)


def generate_single_category(difficulty="medium", existing_categories=None):
    """
    Generate a single category with specified difficulty.
    existing_categories: list of existing category names to avoid duplicates
    """
    existing_names = [cat.get('name', '').lower() for cat in (existing_categories or [])]

    # Load the full banned categories list so regeneration respects it too
    try:
        from banned_categories import load_banned_categories, normalize_category
        banned = sorted({normalize_category(n) for n in load_banned_categories()})
        banned_text = ", ".join(banned) if banned else "none"
    except Exception:
        banned_text = "none"

    prompt = f"""
You create a completely NEW category for a "Connections"-style word puzzle.

BANNED CATEGORY IDEAS (READ FIRST — DO NOT REUSE ANY OF THESE, even rephrased):
{banned_text}

For each category idea you brainstorm, cross-check it against the banned list above. If it matches, is a paraphrase, a translation, a narrower/broader version, or a "different angle" on any banned entry, DISCARD it and try a different idea.

CRITICAL REQUIREMENTS:
- Create a COMPLETELY NEW category - NOT a variation, NOT a slight rename, NOT similar words
- The category must be UNIQUE and DISTINCT from existing categories AND from the banned list above
- Category must have difficulty: {difficulty}
- The category must have exactly 4 words
- Category name should be short and human-friendly
- Words should be in UPPERCASE

FORBIDDEN CATEGORY PATTERN — "dual-meaning" categories:
- DO NOT create categories of the form "words that can mean both X and Y" / "words that are both X and Y" / "words with two meanings: X and Y" / "terms that work as both X and Y", or any paraphrase of this shape.
- Examples of FORBIDDEN names: "Words that are both colors and emotions", "Terms that are both animals and verbs", "Words that work as both body parts and geography".
- This pattern is overused. If you're tempted to write one, pick a different angle entirely.

REGISTER — KEEP IT CASUAL AND POP-CULTURAL:
This is a casual word game, not a trivia quiz.
- PREFER: pop culture (movies, TV, music, sports, celebrities, brands), everyday objects and actions (kitchen, bathroom, commute, weekend), common verbs and nouns, idioms, things anyone says daily.
- AVOID: academic jargon, specialist vocabulary, categories whose words all share a telltale surface feature (same suffix, all Italian musical terms, all Greek/Latin, all technical jargon). Those are giveaways — the solver spots the pattern instantly.
- FORBIDDEN CATEGORY TYPES (do NOT use or rephrase): "Philosophical schools of thought", "Classical music tempo markings", "Types of fabric weaves", "Literary devices", "Architectural orders", "Logical fallacies", "Cognitive biases", or anything that reads like a college syllabus, Wikipedia category, or museum label.
- Common familiar words are HARDER and BETTER for puzzles than obscure specialist ones — they can carry multiple meanings and make real decoys. Aim for words both a teenager and a grandparent would recognize.
- GIVEAWAY CHECK: if all 4 words share a surface signal (same suffix, same language, obviously one jargon field), the category is a giveaway — rework it.

DIFFICULTY LEVELS (all casual register — no academic jargon at any level):
- "easy": Concrete, familiar, pop-culture or everyday (e.g., "Things in a fridge", "Ways to say yes", "Characters named Mike"). NOT generic "types of X" and NOT specialist vocabulary.
- "medium": Common words with mild wordplay or a light cultural reference (e.g., "Words that follow 'light'", "Things you bring to the beach", "Sitcom dads").
- "hard": Wordplay-based with common words (e.g., "Idioms with 'break'", "Words hidden inside country names", "Second halves of compound nouns", "___ + UP"). NOT academic topics like "Literary devices" or "Philosophical schools".

EXISTING CATEGORIES TO AVOID (create something completely different):
{', '.join(existing_names) if existing_names else 'none'}

IMPORTANT: Do NOT create a category similar to any of the above or to anything on the banned list. Create something completely new and different in both name and concept.

OUTPUT FORMAT:
Return ONLY valid JSON with this exact structure:
{{
  "name": "Category name here",
  "difficulty": "{difficulty}",
  "words": ["WORD1", "WORD2", "WORD3", "WORD4"]
}}

No extra text, no explanations, just JSON.
"""
    
    try:
        _configure_genai()

        # Prepare banned-check helpers (graceful if banned_categories module missing)
        try:
            from banned_categories import load_banned_categories, normalize_category
            banned_set = {normalize_category(n) for n in load_banned_categories()}
        except Exception:
            banned_set = set()
            normalize_category = lambda s: (s or "").strip().lower()  # noqa: E731

        gmodel = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction="You are an expert Grooped puzzle category generator. Always return valid JSON only.",
        )

        max_attempts = 8
        last_candidate = None
        for attempt in range(1, max_attempts + 1):
            response = gmodel.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=512,
                    temperature=0.8,
                    response_mime_type="application/json",
                ),
            )
            text = re.sub(r"^```(?:json)?\s*", "", response.text.strip(), flags=re.IGNORECASE); text = re.sub(r"```\s*$", "", text).strip()
            match = re.search(r"\{[\s\S]*\}", text)
            data = json.loads(match.group() if match else text)
            last_candidate = data

            name = (data.get("name") or "").strip()
            norm = normalize_category(name)

            # Hard reject: exact (normalized) banned match
            if norm and norm in banned_set:
                print(f"[regenerate_single_category] Rejected (banned exact): {name}")
                continue

            print(f"[regenerate_single_category] Accepted on attempt {attempt}: {name}")
            return data

        # Fallback: return last candidate (extremely rare — model kept producing banned names)
        print(
            f"[regenerate_single_category] Exhausted {max_attempts} attempts; "
            f"returning last candidate (may still be banned)."
        )
        return last_candidate
    except Exception as e:
        raise Exception(f"Failed to generate category: {str(e)}")


def generate_words_for_category(category_name, difficulty="medium"):
    """
    Generate 4 words for a given category name.
    This is used when the user writes a category name and wants words generated for it.
    """
    prompt = f"""
You are generating words for a "Connections"-style word puzzle category.

CATEGORY NAME: {category_name}

REQUIREMENTS:
- Generate exactly 4 words that fit this category
- Words should be in UPPERCASE
- Words should be clear, recognizable, and appropriate for a word puzzle
- Difficulty level: {difficulty}
  - "easy": Common, concrete words
  - "medium": Requires some general knowledge
  - "hard": More abstract or wordplay-based

OUTPUT FORMAT:
Return ONLY valid JSON with this exact structure:
{{
  "name": "{category_name}",
  "difficulty": "{difficulty}",
  "words": ["WORD1", "WORD2", "WORD3", "WORD4"]
}}

No extra text, no explanations, just JSON.
"""
    
    try:
        _configure_genai()
        gmodel = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction="You are an expert at generating words for word puzzle categories. Always return valid JSON only.",
        )
        response = gmodel.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=512,
                temperature=0.7,
                response_mime_type="application/json",
            ),
        )
        text = re.sub(r"^```(?:json)?\s*", "", response.text.strip(), flags=re.IGNORECASE); text = re.sub(r"```\s*$", "", text).strip()
        match = re.search(r"\{[\s\S]*\}", text)
        return json.loads(match.group() if match else text)
    except Exception as e:
        raise Exception(f"Failed to generate words for category: {str(e)}")

