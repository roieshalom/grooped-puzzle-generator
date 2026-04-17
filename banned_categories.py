#!/usr/bin/env python3
"""Global banned categories helpers."""

import hashlib
import json
import math
import os

BANNED_CATEGORIES_PATH = "banned_categories.json"
EMBEDDING_CACHE_PATH = "banned_categories_embeddings_cache.json"
SIMILARITY_THRESHOLD = 0.88


def _ensure_file():
    if not os.path.exists(BANNED_CATEGORIES_PATH):
        with open(BANNED_CATEGORIES_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def normalize_category(name: str) -> str:
    if not name:
        return ""
    s = name.strip().lower()
    for suffix in [" category", " categories"]:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s


def load_banned_categories():
    _ensure_file()
    with open(BANNED_CATEGORIES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    normed = {normalize_category(x) for x in data if isinstance(x, str)}
    return sorted(x for x in normed if x)


def save_banned_categories(categories):
    normed = sorted({normalize_category(x) for x in categories if isinstance(x, str)})
    with open(BANNED_CATEGORIES_PATH, "w", encoding="utf-8") as f:
        json.dump(normed, f, ensure_ascii=False, indent=2)


def add_banned_category(name: str):
    norm_name = normalize_category(name)
    if not norm_name:
        return
    current = set(load_banned_categories())
    if norm_name not in current:
        current.add(norm_name)
        save_banned_categories(list(current))


# ---------------------------------------------------------------------------
# Semantic similarity helpers (embedding-based)
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _list_hash(items: list) -> str:
    joined = "\n".join(sorted(items))
    return hashlib.md5(joined.encode()).hexdigest()


def load_banned_embeddings(client) -> dict:
    """Return {normalized_category: embedding} for all banned categories.

    Embeddings are cached to disk and recomputed only when the banned list changes.
    ``client`` is an openai.OpenAI instance.
    """
    categories = load_banned_categories()
    if not categories:
        return {}

    current_hash = _list_hash(categories)

    if os.path.exists(EMBEDDING_CACHE_PATH):
        with open(EMBEDDING_CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if cache.get("hash") == current_hash:
            return cache["embeddings"]

    print(f"Computing embeddings for {len(categories)} banned categories…")
    embeddings = {}
    batch_size = 500
    for i in range(0, len(categories), batch_size):
        batch = categories[i : i + batch_size]
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=batch,
        )
        for cat, item in zip(batch, response.data):
            embeddings[cat] = item.embedding

    with open(EMBEDDING_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"hash": current_hash, "embeddings": embeddings}, f)

    print("Banned-category embeddings cached.")
    return embeddings


def find_semantically_banned(
    name: str,
    banned_embeddings: dict,
    client,
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple:
    """Check whether *name* is semantically too close to any banned category.

    Returns ``(matched_category, similarity)`` if a match is found above
    *threshold*, otherwise ``(None, best_similarity)``.
    """
    norm_name = normalize_category(name)
    if not norm_name or not banned_embeddings:
        return None, 0.0

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=[norm_name],
    )
    query_emb = response.data[0].embedding

    best_match = None
    best_sim = 0.0
    for cat, emb in banned_embeddings.items():
        sim = _cosine_similarity(query_emb, emb)
        if sim > best_sim:
            best_sim = sim
            best_match = cat

    if best_sim >= threshold:
        return best_match, best_sim
    return None, best_sim
