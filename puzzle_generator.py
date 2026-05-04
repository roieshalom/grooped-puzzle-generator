import os
import re
import json
from datetime import datetime, timedelta
import google.generativeai as genai
from dotenv import load_dotenv
from banned_categories import (
    load_banned_categories,
    normalize_category,
)

load_dotenv()  # This loads the .env file

genai.configure(api_key=os.environ["GEMINI_API_KEY"])


def _extract_json(text: str) -> str:
    """Extract raw JSON from Gemini output, handling prose preambles and code fences."""
    text = text.strip()
    fence = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    obj = re.search(r'\{[\s\S]*\}', text)
    if obj:
        return obj.group()
    return text


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
        gmodel = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction="You are a strict fact-checker. Return only valid JSON.",
        )
        resp = gmodel.generate_content(
            verify_prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=1024,
                temperature=0.1,
            ),
        )
        result = json.loads(_extract_json(resp.text))
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
GROOPED PUZZLE GENERATION PROMPT (v5)
=====================================

You are designing a single 4x4 NYT Connections-style puzzle for Grooped. 16 unique words, four groups of four, each tagged with a difficulty color: yellow (easiest), green, blue, purple (hardest). Output schema must match puzzles.json.

NORTH STAR
==========

A great Grooped puzzle is not four neat lists. It is four groups that bleed into each other on the board, so a solver feels multiple words could plausibly live in multiple homes. A STRONG BOARD BEATS EVERY RULE BELOW. That cross-pull tension is the puzzle. Without it, you made a quiz.

STEP 0: FETCH THE LIVE CORPUS
============================

Before drafting, fetch https://raw.githubusercontent.com/roieshalom/grooped/refs/heads/main/puzzles.json. You will use it for four things:

1. REPEAT CHECK: no category theme or individual word may repeat from the last 60 days.
2. STYLE CALIBRATION: absorb the corpus voice.
3. MECHANIC BALANCING: read the 'mechanic' field on each category and the 'attempt_log' field on each puzzle. See "MECHANIC FREQUENCY SYSTEM" below.
4. WARMUP AWARENESS: puzzles before #137 do not have 'mechanic' fields. They are untagged history. Your cooldown calculations only run on tagged puzzles.

If you cannot fetch it, say so and stop.

MECHANIC FREQUENCY SYSTEM
=========================

Mechanics live in four tiers by how often they should appear. The tiers exist because some mechanics (simple "___ X" fill-in-blank) feel fresh weekly, while others (first-letter acrostics) feel forced if used often.

HOW TO USE THE TIERS
====================

When picking the four mechanics for a new puzzle:

1. SCAN the last 21 tagged puzzles in puzzles.json. Note which mechanics appeared in their 'mechanic' fields AND in their 'attempt_log' (abandoned attempts count toward cooldown too).
2. APPLY COOLDOWNS: a mechanic that appeared inside its cooldown window is off-limits for this puzzle.
3. PREFER UNDERUSED MECHANICS: if a Tier 2 or Tier 3 mechanic has not appeared in the last 21 puzzles, it is a strong candidate.
4. DON'T FORCE RARE MECHANICS: Tier 4 should appear when a great idea naturally lands, not because the cooldown expired.

A typical strong puzzle uses 1-2 mechanics from Tier 1, 1-2 from Tier 2, optionally 1 from Tier 3, and rarely one from Tier 4.

WARMUP PERIOD (until 21 tagged puzzles exist)
==============================================

The corpus before puzzle #137 is heavily skewed toward Tier 1 (taxonomy and reference). Until there are 21 tagged puzzles to read from:

- LEAN TOWARD TIER 2 AND TIER 3 MECHANICS, since the untagged history already provides plenty of Tier 1 baseline.
- DON'T DOUBLE UP ON TIER 1 MECHANICS in the same puzzle during warmup unless the cross-pulls are exceptional.
- No more than 2 categories from the same tier in a single puzzle (warmup or not).
- Once 21 tagged puzzles exist, switch to standard cooldown logic.

TIER 1: WORKHORSES — cooldown 4 puzzles, ~40% of categories long-term
====================================================================

The reliable backbones. Repeating these every few days is fine because the content is fresh even when the mechanic is familiar.

- TAXONOMY: flat list of a category type (cheeses, currencies, dog breeds). Allowed only when at least 2 of its 4 words pull toward another group on the board. Otherwise it is filler.
- FOUND_IN_SCENE: things in a place. "At the dentist" -> BRACE, CAVITY, CROWN, BRIDGE.
- PREFIX_BLANK: "___ X". "___ STONE" -> CORNER, KEY, SAND, LIME. CRITICAL: verify every word individually — "cold shoulder" means SHOULDER goes in SUFFIX_BLANK ("___ cold"), not PREFIX_BLANK. If the hub word comes AFTER any of the four words, it belongs in SUFFIX_BLANK, not here. Never mix directions in one category.
- SUFFIX_BLANK: "X ___". "DEAD ___" -> PAN, BEAT, POOL, RINGER. Same rule applies in reverse — if the hub word comes BEFORE any of the four words, it belongs in PREFIX_BLANK.
- SYNONYMS: literal synonyms for one word. "Walk" -> STROLL, TREAD, WANDER, MARCH.

TIER 2: REGULARS — cooldown 7 puzzles, ~35% of categories long-term
====================================================================

Slightly more lateral. These should appear every 1 to 2 weeks.

- THINGS_THAT_VERB: nouns that all do an action. "Things that RUN" -> NOSE, FAUCET, CANDLE, NYLON.
- CAN_BE_VERBED: things that can all receive an action. "Can be scrambled" -> EGG, TELEGRAM, CODE, LETTERS.
- SHARED_HIDDEN_PROPERTY: surprise trait. "Have teeth" -> COMB, GEAR, ZIPPER, SAW.
- METAPHOR_SUBSTITUTES: figurative terms for one concept. "In trouble" -> BIND, JAM, PICKLE, HOT WATER. UNDERUSED IN THE CORPUS. PREFER THIS.
- WAYS_TO_VERB: phrasal styles of an action. "Ways to say yes" -> SURE, BET, DEAL, GRANTED.
- IDIOM_COMPLETION: words that finish a specific idiom. "Bite the ___" -> BULLET, DUST, HAND, APPLE.
- ORDERED_SET_MEMBER: planets, Greek letters, NATO alphabet, ranks, days, months.
- WORKS_BY_ONE_MAKER: songs by an artist, films by a director.
- CHARACTERS_IN_ONE_WORK: cast of one show or book.
- FACETS_OF_SUBJECT: different angles on one named subject. "Facets of TRUMP" -> BUSINESSMAN, PRESIDENT, TV HOST, BEAUTY PAGEANT.

TIER 3: SPECIALS — cooldown 21 puzzles, ~20% of categories long-term
====================================================================

Wordplay-flavored mechanics that lose punch with overuse. Roughly once every 3 weeks each.

- HIDDEN_WORD: each word contains a hidden item from a category — anywhere inside (STONE/one), at the start (CRUSHWORTHY/crush), or at the end (PACKAGE/age). Specify the variant in the category label. WARNING: if using the "at the end" variant, all four words will rhyme — this makes the mechanic immediately obvious and ruins the puzzle. Avoid "hidden at end" unless the rhyme is a known red herring. Strongly prefer "inside" or "at start" variants where the hidden element lands in different positions across the four words.
- HOMOPHONES: words that sound like something in a shared category — single letters (SEA=C, ARE=R), numbers (ATE=8, WON=1), or each has a homophone fitting a category (BARE/bear, FLOWER/flour). Specify the variant in the category label.
- COMPOUND: words that form compound words as both prefix and suffix to one hub word (SUN+flower, door+STEP, FIRE+place, rain+COAT).
- ADD_DROP_LETTER: each word becomes a new real word when the same letter is added (CARE->SCARE) or dropped (BRAVE->RAVE). Specify add or drop in the category label.
- EPONYMS: things named after people. SANDWICH, BOYCOTT, GUILLOTINE, CARDIGAN.
- CROSS_LANGUAGE: same concept across languages. "Cheers" -> SLAINTE, KAMPAI, PROST, CIN-CIN.
- ABBREVIATION_EXPANSION: common acronyms read as letters (NASA, FBI, SCUBA, RADAR).
- LINGUISTIC_NOVELTY: all four words share an unusual linguistic property. Use sparingly — the pool for each flavor is small. Flavors (specify in the category label):
  - Word reversal: each word spells a different real word backwards (DOG/god, LIVE/evil, STRESSED/desserts, POTS/stop).
  - Rhymes with ___: all four rhyme with the same target word (rhymes with MOON: spoon, tune, June, boon).
  - Toponyms: words derived from place names (DENIM/Nîmes, CHAMPAGNE/region, TUXEDO/New York, CHEDDAR/village). Natural companion to EPONYMS.
  - Capitonym: same spelling, different meaning when capitalized (march/March, polish/Polish, china/China, may/May).
  - Famous ___s: all four are famously associated with the same number (things in threes: bears, musketeers, stooges, tenors).
  - Contronym: all four words are their own antonym — Janus words (SANCTION: permit or penalize; CLEAVE: split or cling; DUST: remove or apply; OVERSIGHT: supervision or mistake). Hardest flavor — only use if all four examples are airtight.

TIER 4: TREATS — cooldown 45 puzzles, ~5% of categories long-term
==================================================================

Showpiece mechanics. Heavy when they land, exhausting if they repeat. Roughly once every 6 weeks each.

- ANAGRAM_OF_ONE_SOURCE: four anagrams of one word. From LISTEN: SILENT, TINSEL, INLETS, ENLIST.
- ACROSTIC_FIRST_LETTERS: first letters of the four words spell a hidden fifth word.
- CHAIN_THROUGH_HUB: the hub of a "___ X" group is itself a word in another group on the same board. The most elegant trick when it works.
- PORTMANTEAU: blended words. BRUNCH, SMOG, MOTEL, SPORK.
- ONOMATOPOEIA: sound-effect words. POW, BAM, ZAP, BOOM.

FALLBACK WITH LOGGING
====================

If you commit to a Tier 3 or Tier 4 mechanic and after a real attempt cannot find four words that work cleanly, you may fall back to a Tier 1 or Tier 2 mechanic. YOU MUST LOG THE ABANDONED ATTEMPT in the 'attempt_log' field of the puzzle. The cooldown system reads this log, so an abandoned attempt counts toward the cooldown the same as a shipped one. This prevents the model from retrying the same broken idea day after day.

Reasons to abandon:
- Cannot find four genuine examples without forcing obscure words
- The mechanic produces words that have no decoy potential against the rest of the board
- The mechanic technically works but feels academic rather than playful

Do not abandon for trivial reasons. The point is to attempt hard mechanics, not to default away from them.

DECOY ENGINE
============

For each puzzle, identify 2 to 3 decoy words.

A DECOY is a word in category A that solvers will be tempted to drop into category B, where category B is ALSO A REAL GROUP ON THIS EXACT BOARD. A decoy that points at a phantom category is just a hard word, not a decoy.

A FALSE DECOY is the next move: a word that looks like it should belong elsewhere but actually lives in its obvious home. The suspicion is the trap. Example: THIMBLE on a board with both Monopoly Pieces and Sewing Equipment, where THIMBLE actually goes to Monopoly.

If you cannot identify at least 2 real decoys, your puzzle has no cross-board tension. Rebuild it.

CATEGORY FRAMING
================

How you name the category changes how it reads. "Words for trouble" is dull. "Metaphors for being in trouble" implies the category is figurative and that's the trick. "Look at with awe" reads like a riddle. "Ways to gesture goodbye" beats "Goodbye gestures." Frame as a verb phrase or riddle whenever you can.

DIFFICULTY AS A SOFT PATTERN
============================

Soft guideline, not a rule. Deviate freely if the board demands it.

- YELLOW: clearest entry. Often a clean scene, taxonomy, or synonym set, with one mild decoy temptation.
- GREEN: recognizable connection that needs a small lateral step.
- BLUE: misdirection-heavy or domain-specific.
- PURPLE: usually wordplay or the trickiest semantic leap. Tier 3/4 mechanics most often live here.

HARD RULES
=========

- 16 unique words on the board (case-insensitive).
- No word repeats from any puzzle in the last 60 days.
- No category theme repeats from the last 60 days. Older repeats fine if spread out.
- No category where all four words share a surface tell (all -ISM, all start with LIM-, all Italian musical terms). Surface tells defeat the puzzle.
- NO "FAMOUS BOBS / CHARLIES / AMYS / STEVES / MIKES" or any "FAMOUS [COMMON FIRST NAME]" pattern. Permanently retired.
- No US Presidents as a category.
- No "Words that are both X and Y" as a category name.
- No standalone color list (RED, BLUE, GREEN, YELLOW). Hues-of-X is also tired.
- No back-to-back puzzles with the same cultural theme.
- No words a 12-year-old wouldn't know unless the category demands it (avoid CINNABAR, COQUELICOT, ESCUTCHEON, SINOPER).
- No word appears twice in the same puzzle.
- Decoy words must point at a category that exists on this exact board.
- Respect mechanic cooldowns from the tier system.
- Every category must have a 'mechanic' and 'tier' field. Every puzzle must have an 'attempt_log' field (can be a single entry if no fallback happened).

CROSS-DOMAIN RULE: No two categories on the same board may draw
primarily from the same real-world domain. If two groups are both
animal-heavy, both food-heavy, or both sport-heavy, rebuild one of
them. The board must feel like four different worlds, not two worlds
split in half.

THINGS_THAT_VERB QUALITY RULE: The four words must perform the action
in genuinely different contexts or senses. "Things that run" must
include words like NOSE, FAUCET, ENGINE, MASCARA — each running in a
different domain. Four animals that all run the same way is a flat
taxonomy pretending to be a verb category. If all four words share the
same real-world domain, this mechanic is being misused. Pick different
words or pick a different mechanic.

SHARED_HIDDEN_PROPERTY QUALITY RULE: The shared property must be
surprising. "Have stripes" with four striped animals is obvious and
boring. "Have stripes" with ZEBRA, TOOTHPASTE, REFEREE, BARCODE is
surprising because the words come from different domains. The aha
moment comes from the unexpected connection, not the expected one. If
a solver can guess all four words just by knowing the category name,
the property is not hidden enough.

TIER DISTRIBUTION RULE: No more than 2 categories from the same tier
in a single puzzle. This prevents Tier 2-heavy boards and forces
variety across the mechanic tiers.

WORKFLOW
========

1. FETCH puzzles.json.
2. RUN THE MECHANIC BALANCER: scan the last 21 tagged puzzles. For each tier, list which mechanics appeared (in 'mechanic' fields or 'attempt_log' entries). Identify Tier 2 and Tier 3 mechanics that haven't appeared. Note any Tier 4 mechanics that haven't appeared in the last 45.
3. PICK THE SPINE MECHANIC (often purple). Prefer underused candidates. If a Tier 4 idea is calling to you and the cooldown allows, go for it.
4. PLANT A DECOY SEED: a word that plausibly lives in two of your groups.
5. BUILD THE OTHER THREE GROUPS so the decoy seed pulls between them. Pick mechanics that haven't appeared recently when you have a choice.
6. ADD A SECOND DECOY.
7. LIST ALL 16 WORDS. Confirm zero duplicates.
8. STRESS-TEST: can a solver group all four words of any group by surface pattern alone? If yes, weaken the surface signal.
9. IF YOUR SPINE MECHANIC ISN'T WORKING, abandon it, log the attempt, and pick a different mechanic. Do not silently switch.
10. SELF-CRITIQUE: tricked but fair, or tricked and annoyed?

OUTPUT FORMAT
=============

Match the production schema. The 'thinking' block is your scratchpad and must come first. Note the new 'mechanic' and 'tier' fields per category, and the 'attempt_log' field on the puzzle.

EXAMPLE JSON OUTPUT (PUZZLE #137)
================================

{
  "id": "137",
  "date": "27.04.2026",
  "language": "en",
  "thinking": {
    "mechanic_balance": {
      "tagged_puzzles_available": 12,
      "warmup_active": true,
      "tier_1_recently_used": ["PREFIX_BLANK", "FOUND_IN_SCENE"],
      "tier_2_recently_used": ["SHARED_HIDDEN_PROPERTY"],
      "tier_3_recently_used": [],
      "tier_4_recently_used": [],
      "underused_candidates": ["METAPHOR_SUBSTITUTES", "HIDDEN_WORD_AT_START", "EPONYMS"],
      "chosen_for_this_puzzle": ["FOUND_IN_SCENE", "METAPHOR_SUBSTITUTES", "WAYS_TO_VERB", "SUFFIX_BLANK"],
      "cooldown_check": "PASS"
    },
    "all_16_words": "KEYS CHANGE LINT RECEIPTS BIND JAM PICKLE HOT_WATER SURE BET DEAL GRANTED PAN BEAT POOL RINGER",
    "duplicate_check": "PASS"
  },
  "categories": [
    {
      "name": "Things that jingle in your pocket",
      "difficulty": "yellow",
      "mechanic": "FOUND_IN_SCENE",
      "tier": 1,
      "words": ["KEYS", "CHANGE", "LINT", "RECEIPTS"]
    },
    {
      "name": "Metaphors for being in trouble",
      "difficulty": "green",
      "mechanic": "METAPHOR_SUBSTITUTES",
      "tier": 2,
      "words": ["BIND", "JAM", "PICKLE", "HOT WATER"]
    },
    {
      "name": "Ways to say yes",
      "difficulty": "blue",
      "mechanic": "WAYS_TO_VERB",
      "tier": 2,
      "words": ["SURE", "BET", "DEAL", "GRANTED"]
    },
    {
      "name": "DEAD ___",
      "difficulty": "purple",
      "mechanic": "SUFFIX_BLANK",
      "tier": 1,
      "words": ["PAN", "BEAT", "POOL", "RINGER"]
    }
  ],
  "decoys": [
    {
      "word": "JAM",
      "home": "Metaphors for being in trouble",
      "tempts_toward": "Things that jingle in your pocket",
      "why": "Solvers might think of jam jars or food in their pocket before reading JAM as 'in a jam'."
    },
    {
      "word": "BET",
      "home": "Ways to say yes",
      "tempts_toward": "DEAD ___",
      "why": "DEAD BET isn't a phrase, but the word feels gambly enough that solvers may try it there."
    }
  ],
  "false_decoy": null,
  "attempt_log": [
    { "mechanic": "ACROSTIC_FIRST_LETTERS", "tier": 4, "result": "abandoned", "reason": "couldn't land four natural words spelling a fifth without forcing obscure terms" },
    { "mechanic": "SUFFIX_BLANK", "tier": 1, "result": "shipped" }
  ]
}

If no fallback happened, attempt_log contains a single entry with result: "shipped".

REFERENCE: TARGET QUALITY PUZZLE
===============================

The example above (puzzle #137) is the target. Two scenes/idioms in Tiers 1-2, one wordplay in Tier 1 purple, real cross-pulls between groups (CHANGE could be pocket or could be improvement, JAM could be food or trouble, BEAT could be drum or DEAD BEAT). Strong board, varied mechanics, no Tier 4 forced. This is what good looks like.
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

        gmodel = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction="You are an expert Grooped puzzle generator. Return valid JSON only, no prose.",
        )
        response = gmodel.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=4096,
                temperature=0.9,
            ),
        )
        data = json.loads(_extract_json(response.text))

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

        # At this point, NO banned categories (exact match)
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

