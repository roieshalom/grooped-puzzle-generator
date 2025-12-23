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
    
    prompt = f"""
You create a completely NEW category for a "Connections"-style word puzzle.

CRITICAL REQUIREMENTS:
- Create a COMPLETELY NEW category - NOT a variation, NOT a slight rename, NOT similar words
- The category must be UNIQUE and DISTINCT from existing categories
- Category must have difficulty: {difficulty}
- The category must have exactly 4 words
- Category name should be short and human-friendly
- Words should be in UPPERCASE

DIFFICULTY LEVELS:
- "easy": Concrete and recognizable (e.g., "Common beverages", "Types of trees")
- "medium": Requires light general knowledge or mild wordplay (e.g., "Words that can follow 'light'", "Types of fabric")
- "hard": Abstract or wordplay-based (e.g., "Words that are both colors and emotions", "Idioms with 'break'")

EXISTING CATEGORIES TO AVOID (create something completely different):
{', '.join(existing_names) if existing_names else 'none'}

IMPORTANT: Do NOT create a category similar to any of the above. Create something completely new and different in both name and concept.

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

