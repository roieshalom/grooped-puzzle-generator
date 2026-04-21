#!/usr/bin/env python3
"""Generate a single category for regeneration."""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Don't create client at module level - create it when needed

def get_client():
    """Get OpenAI client with API key loaded from .env or environment"""
    # First check if already in environment
    api_key = os.environ.get("OPENAI_API_KEY")
    
    # If not, try loading from .env file
    if not api_key:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Try loading from current directory
        load_dotenv()
        # Try loading from script directory
        env_path = os.path.join(script_dir, '.env')
        load_dotenv(dotenv_path=env_path, override=False)
        
        # Check again after loading
        api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(script_dir, '.env')
        raise ValueError(
            f"OPENAI_API_KEY not found. Either:\n"
            f"1. Set it as an environment variable: export OPENAI_API_KEY=your_key\n"
            f"2. Create a .env file at {env_path} with: OPENAI_API_KEY=your_key"
        )
    
    return OpenAI(api_key=api_key)


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

DIFFICULTY LEVELS:
- "easy": Concrete and recognizable, but NOT generic "types of X" lists (avoid "Common beverages", "Types of trees", etc.). Think specific, grounded ideas with a small twist.
- "medium": Requires light general knowledge or mild wordplay (e.g., "Words that can follow 'light'", "Things in a detective's office").
- "hard": Wordplay-based or structural — e.g., "Idioms with 'break'", "Words hidden inside country names", "Second halves of compound nouns", "Homophones of tree names". NOT "words that are both X and Y".

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
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert Grooped puzzle category generator. Always return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            response_format={"type": "json_object"},
        )
        puzzle_json = response.choices[0].message.content
        return json.loads(puzzle_json)
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
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert at generating words for word puzzle categories. Always return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        puzzle_json = response.choices[0].message.content
        return json.loads(puzzle_json)
    except Exception as e:
        raise Exception(f"Failed to generate words for category: {str(e)}")

