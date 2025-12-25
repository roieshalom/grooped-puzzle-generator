#!/usr/bin/env python3
"""Global banned categories helpers."""

import json
import os

BANNED_CATEGORIES_PATH = "banned_categories.json"


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
