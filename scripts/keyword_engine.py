import json
import os
import random
import datetime
import itertools
import hashlib

# OPTIONAL TREND SUPPORT
try:
    from pytrends.request import TrendReq
    TREND_ENABLED = True
except:
    TREND_ENABLED = False

OUTPUT = "data/keywords.json"
PHONES_FILE = "data/phones/phones.json"
TREND_CACHE = "data/trends_cache.json"

YEAR = str(datetime.datetime.now().year)

# -------------------------
# LOAD HELPERS
# -------------------------
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# -------------------------
# LOAD PHONES
# -------------------------
def load_phones():
    return load_json(PHONES_FILE, [])

# -------------------------
# EXTRACT BRANDS
# -------------------------
def extract_brands(phones):
    brands = set()

    for p in phones:
        name = p.get("name", "").lower()
        if name:
            brands.add(name.split()[0])

    return list(brands)

# -------------------------
# PRICE BUCKETS
# -------------------------
def generate_price_buckets():
    base = [100, 200, 300, 500, 700, 1000, 1500]
    return [f"under ${x}" for x in base]

# -------------------------
# INTENT LAYERS
# -------------------------
BUYER = ["best", "top", "buy", "review", "deals", "worth it"]
MODIFIERS = ["cheap", "affordable", "premium", "fastest"]
USE_CASES = ["gaming", "camera", "battery", "students", "business"]
ATTRIBUTES = ["5g", "oled", "fast charging", "long battery"]
CARRIERS = ["verizon", "t mobile", "at&t", "unlocked"]

# -------------------------
# TREND ENGINE (CACHED)
# -------------------------
def fetch_trends():
    cache = load_json(TREND_CACHE, {})

    if cache.get("date") == str(datetime.date.today()):
        return cache.get("data", [])

    if not TREND_ENABLED:
        return []

    try:
        pytrends = TrendReq(hl='en-US', tz=360)

        topics = ["iphone", "samsung", "pixel", "smartphone"]
        trends = []

        for t in topics:
            pytrends.build_payload([t], timeframe='now 7-d', geo='US')
            related = pytrends.related_queries()

            if t in related and related[t]["rising"] is not None:
                for _, row in related[t]["rising"].iterrows():
                    trends.append(row["query"])

        trends = list(set(trends))

        save_json(TREND_CACHE, {
            "date": str(datetime.date.today()),
            "data": trends
        })

        return trends

    except:
        return cache.get("data", [])

# -------------------------
# GENERATION
# -------------------------
def generate_keywords(brands, prices):
    kws = []

    for b, p in itertools.product(brands, prices):
        kws.extend([
            f"best {b} phones {p}",
            f"{b} phones {p} {YEAR}",
            f"{b} smartphone deals {p}"
        ])

    for u, p in itertools.product(USE_CASES, prices):
        kws.extend([
            f"best phones for {u} {p}",
            f"phones {p} for {u}"
        ])

    for a, p in itertools.product(ATTRIBUTES, prices):
        kws.append(f"phones with {a} {p}")

    for c, p in itertools.product(CARRIERS, prices):
        kws.append(f"best phones for {c} {p}")

    return kws

def generate_long_tail(kws):
    expanded = []

    for kw in kws:
        expanded.extend([
            kw,
            f"{kw} in {YEAR}",
            f"{kw} for beginners",
            f"{kw} pros and cons",
            f"{kw} worth buying"
        ])

    return expanded

def generate_trend_keywords(trends):
    kws = []

    for t in trends:
        kws.extend([
            f"{t} review",
            f"{t} worth it",
            f"buy {t}",
            f"{t} vs iphone"
        ])

    return kws

# -------------------------
# CLEAN + DIVERSIFY
# -------------------------
def clean_keywords(keywords):
    seen = set()
    final = []

    for kw in keywords:
        kw = kw.lower().strip()

        if len(kw) < 10:
            continue

        h = hashlib.md5(kw.encode()).hexdigest()

        if h not in seen:
            seen.add(h)
            final.append(kw)

    return final

# -------------------------
# SCORING
# -------------------------
def score_keyword(kw):
    score = 0

    if "best" in kw:
        score += 5
    if "under $" in kw:
        score += 4
    if "review" in kw:
        score += 3
    if "vs" in kw:
        score += 3
    if "buy" in kw or "deals" in kw:
        score += 4

    return score

def prioritize(keywords):
    return sorted(keywords, key=lambda x: score_keyword(x), reverse=True)

# -------------------------
# MAIN
# -------------------------
def run():
    print("[KEYWORD ENGINE 10/10] Running...")

    phones = load_phones()
    brands = extract_brands(phones)
    prices = generate_price_buckets()

    if not brands:
        brands = ["iphone", "samsung", "pixel"]

    base = generate_keywords(brands, prices)
    long_tail = generate_long_tail(base)

    trends = fetch_trends()
    trend_kws = generate_trend_keywords(trends)

    all_keywords = base + long_tail + trend_kws

    all_keywords = clean_keywords(all_keywords)
    all_keywords = prioritize(all_keywords)

    os.makedirs("data", exist_ok=True)
    save_json(OUTPUT, all_keywords[:15000])

    print(f"[KEYWORD ENGINE] Generated {len(all_keywords)} keywords")

if __name__ == "__main__":
    run()
