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

    # PORTFOLIO_START — do not remove: used by roiesh.com/grooped.html to display this prompt live
    # Main prompt is a plain triple-quoted string (NOT an f-string),
    # so the JSON braces remain literal
    prompt = banned_block + """
You create Connections-style 4x4 word puzzles for adults.

GOAL

Create 1 puzzle with 4 categories:
1 easy, 2 medium, 1 hard.
Each category has exactly 4 words (16 total), all words unique (no repeats).
The puzzle should feel fair but non-trivial: familiar words, but not childish textbook lists.

BOARD-LEVEL DESIGN — START WITH THE DECOY WORDS, THEN BUILD CATEGORIES AROUND THEM

Most bad puzzles fail because the designer builds 4 categories first, then tries to find decoys as an afterthought. When categories are designed independently, there's no natural overlap and decoys become fabricated.

Do it in reverse:

STEP 1 — Pick 2–3 “anchor” words that have two completely different common meanings.
Good anchor words are short, everyday, and genuinely polysemous:
- BARK (dog sound / tree layer)
- COLD (illness / temperature)
- BASS (fish / music)
- CORK (wine stopper / Irish city)
- JIMMY (to pry open / a first name)
- PITCHER (baseball / a jug)
- SPRING (season / coil / to jump)
- DIAMOND (gem / baseball field)
- CRANE (bird / construction machine / to stretch your neck)
- BOLT (lightning / door lock / to run fast / a screw)
Proper nouns with double lives also work: MARS (planet + candy bar), MERCURY (planet + car brand), OREO (cookie + slang).

STEP 2 — Design your 4 categories so that each anchor word genuinely fits in TWO of them.
Example: if your anchor is BARK, design one category about dogs and one about trees — then BARK is a natural decoy between them.

STEP 3 — Fill in the remaining 3 words per category using common, SHORT words (ideally 1–2 syllables). Avoid words so long or distinctive that they can only ever mean one thing (SNICKERDOODLE, TIPTOE, SHORTBREAD — no second life, zero decoy potential).

STEP 4 — Do NOT include any word in a category if that word appears inside the category's own name. (“POP” in “Things That Pop” — circular and too obvious.)

DECOY RULES:
- Aim for 2–3 decoys. Zero decoys = boring puzzle where every word is obvious.
- Only list a decoy if the word GENUINELY fits both categories using common primary meanings. The test: could a random adult complete both sentences in one plain line?
  “WORD fits [category_a] because ___”
  “WORD fits [category_b] because ___”
  If either is a stretch, a metaphor, or sounds made up — drop the decoy.
- INVALID: “SLIDE fits Household Chores because you slide a mop” — nobody calls that sliding.
- INVALID: “LOOP fits Household Chores because cleaning cycles loop” — not a chore.
- VALID: BARK — “Bark is the sound a dog makes” ✓ + “Bark is the outer layer of a tree” ✓
- VALID: COLD — “A cold is an illness” ✓ + “Cold means low temperature” ✓
- VALID: MARS — “Mars is a planet” ✓ + “Mars is a chocolate bar” ✓

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

REGISTER — KEEP IT CASUAL AND POP-CULTURAL (VERY IMPORTANT):
This is a casual word game, not a trivia quiz or a vocabulary test. Aim for the register of sitcoms, everyday chat, pop culture, and household life — NOT academia, museum placards, or specialist textbooks.

- PREFER: pop culture (movies, TV, music, sports, celebrities, internet, brands), everyday objects and actions (kitchen, bathroom, commute, weekend errands), common verbs and nouns anyone uses daily, idioms and sayings, things kids know, things parents say, shared cultural references.
- AVOID: academic jargon, specialist vocabulary, domain-of-expertise word sets. Specifically avoid categories whose words all share a telltale surface feature (a shared suffix, a shared language of origin, all-Italian musical terms, all-Greek/Latin roots, all technical terminology). These are giveaways — the solver spots the pattern immediately and the category becomes trivial.
- FORBIDDEN CATEGORY TYPES (do NOT use or rephrase these):
  - "Philosophical schools of thought" (all end in "-ism" — instant giveaway)
  - "Classical music tempo markings" (all Italian — instant giveaway, also niche)
  - "Types of fabric weaves" / "Textile weaving terms" (niche jargon)
  - "Literary devices" / "Rhetorical figures" (academic)
  - "Architectural orders" / "Musical forms" / "Dance notations"
  - "Logical fallacies", "Cognitive biases", "Grammatical cases"
  - Anything that reads like a college syllabus, a Wikipedia category page, or a museum wall label.
- WHY: Common, familiar words are HARDER, not easier, for a puzzle like this — because a common word can live in multiple contexts and make a great decoy. "MARS" (planet / candy bar / god / verb) is a better puzzle word than "ALLEGRO" (only one thing, and obviously Italian). Prefer words your grandmother AND your teenager would both recognize.
- If a category would require the solver to know a specific discipline, replace it.

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

ANOTHER GOOD PUZZLE EXAMPLE (casual / pop-culture register)
CHARACTERS NAMED "MIKE" — WAZOWSKI, TYSON, MYERS, PENCE
THINGS IN A FRIDGE — MILK, EGGS, LEFTOVERS, ICE
WAYS TO SAY "YES" — SURE, DEAL, BET, GRANTED
BREAK ___ — DANCE, UP, FAST, EVEN

Why it works:
Every word is something a casual player uses or hears weekly. No jargon. No specialist knowledge.
Decoys: TYSON (Mike Tyson / chicken brand in the fridge?), ICE (fridge / "ice him" as a yes-like agreement in slang / break the ice), BET (slang yes / break a bet), GRANTED (yes / "take for granted" / break granted?). Common words are doing real puzzle work.
Register is sitcom-casual, not academic. A 12-year-old and a 70-year-old can both play.

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
- REGISTER CHECK: Does any category read like a college-syllabus topic, a museum label, or a Wikipedia subcategory (e.g., "philosophical schools of thought", "classical music tempo markings", "fabric weave types", "literary devices", "architectural orders", "logical fallacies")? If yes, replace it with a pop-culture, everyday-object, or common-action category. Prefer words familiar to both a teenager and a grandparent.
- GIVEAWAY CHECK: Do all 4 words in any category share a surface signal (same suffix like "-ism" / "-ology" / "-ness", all Italian, all Greek, all ending in the same letters, all clearly from one jargon field)? If yes, the category is a giveaway — replace or rework it.
- DECOY CHECK: For each decoy, can you complete BOTH sentences in one plain line? "This word fits [category_a] because ___" AND "This word fits [category_b] because ___". If either sentence is false, strained, or takes more than 15 words — remove that decoy entirely. It is better to have 1 real decoy than 4 fabricated ones.
- Are ALL decoys words that are actually on the board? Are both claimed categories real category names in this puzzle? If not, remove the decoy.
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
      "reason_a": "One plain sentence: why this word fits category_a",
      "category_b": "Second category name",
      "reason_b": "One plain sentence: why this word fits category_b"
    }
  ],
  "other_trick": "Very short description (one sentence) of any other decoy pattern or overlap."
}

No extra text, no explanations, just JSON.
"""
    # PORTFOLIO_END — do not remove: used by roiesh.com/grooped.html to display this prompt live

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

