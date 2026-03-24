# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# FULL FILE START (ORIGINAL + AUTHORITY ENGINE INTEGRATED)
# NOTHING REMOVED — ONLY EXTENDED
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

#!/usr/bin/env python3

import os
import json
import datetime
import requests
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import random
from seo_growth_utils import (
    build_keyword_universe,
    build_link_graph,
    choose_keyword_devices,
    classify_phone,
    normalize_phones,
    save_json as save_json_helper,
)
# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════
BASE_DIR        = os.path.abspath("site")
DATA_FILE       = "data/phones/phones_enriched.json"
KEYWORD_FILE    = "data/keywords_real.json"

INDEX_FILE      = "data/page_index.json"
INDEX_LOCK      = threading.Lock()

BATCH_SIZE      = int(os.environ.get("BATCH_SIZE", "20"))
MAX_WORKERS     = int(os.environ.get("MAX_WORKERS", "5"))

ADSENSE_CLIENT  = "ca-pub-XXXXXXXXXXXXXXXX"
AD_SLOTS        = ["1111111111", "2222222222", "3333333333", "4444444444"]  # 4 slots
SITE_DOMAIN     = "https://yoursite.com"
SITE_NAME       = "PhoneRank"
AUTHOR_NAME     = f"{SITE_NAME} Editorial Team"
NOW_YEAR        = "2026"
TODAY           = datetime.date.today().isoformat()
RANKED_PHONES = None

BACKLINK_DB = "data/backlinks/live_links.json"
AMAZON_TAG = "yourtag-21"

# Launch phase gate: 1=phones only, 2=phones+compare, 3=all pages
# Start at 1. Move to 2 after GSC confirms indexing. Move to 3 after clicks appear.
LAUNCH_PHASE    = int(os.environ.get("LAUNCH_PHASE", "3"))

MAX_KEYWORDS    = 700
MAX_COMPARE_PHONES = 20  # top N phones in comparison matrix

SUGGESTION_QUERIES_URL = "https://suggestqueries.google.com/complete/search?client=firefox&q={q}"
SUGGESTION_CACHE_FILE = "data/suggestions_cache.json"

os.makedirs(BASE_DIR, exist_ok=True)

with open(DATA_FILE, "r", encoding="utf-8") as f:
    PHONES = json.load(f)

# -------------------------
# DATA VALIDATION LAYER
# -------------------------
def validate_phones(data):
    valid = []

    for p in data:
        if not isinstance(p, dict):
            continue
        if "name" not in p:
            continue

        # enforce minimum structure
        p.setdefault("specs", {})
        p.setdefault("price", 0)
        p.setdefault("images", [])

        valid.append(p)

    print(f"[INFO] Loaded {len(valid)} valid phones (from {len(data)})")
    return valid

PHONES = normalize_phones(validate_phones(PHONES))
# ═══════════════════════════════════════════════════════════
# PAGE INDEX ENGINE (RESUME + INCREMENTAL BUILD)
# ═══════════════════════════════════════════════════════════

def load_index():
    if not os.path.exists(INDEX_FILE):
        return {
            "phones": {},
            "compare": {},
            "keywords": {},
            "cluster": {},
            "topics": {}
        }
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "phones": {},
            "compare": {},
            "keywords": {},
            "cluster": {},
            "topics": {}
        }

def save_index(idx):
    tmp = INDEX_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)
    os.replace(tmp, INDEX_FILE)

PAGE_INDEX = load_index()

def mark_done(section, key):
    with INDEX_LOCK:
        PAGE_INDEX.setdefault(section, {})
        PAGE_INDEX[section][key] = TODAY
        save_index(PAGE_INDEX)
        

def is_done(section, key):
    return key in PAGE_INDEX.get(section, {})    

# ═══════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def get_spec(p, k):
    return p.get("specs", {}).get(k, 0)

def safe_price(p):
    return p.get("price") or 0

def slugify(s):
    return s.strip().lower().replace(" ", "-").replace("/", "-").replace("\\", "-")

def safe_write(path, content):
    """Atomic write with fsync (production-safe)"""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:
        print(f"[WARN] Could not write {path}: {e}")

def price_bucket_label(p):
    price = safe_price(p)
    if price < 100:  return "under $100"
    if price < 200:  return "$100–$200"
    if price < 300:  return "$200–$300"
    if price < 400:  return "$300–$400"
    if price < 500:  return "$400–$500"
    if price < 700:  return "$500–$700"
    if price < 1000: return "$700–$1000"
    return "$1000+"

# ═══════════════════════════════════════════════════════════
# ADS — 4 SLOTS
# ═══════════════════════════════════════════════════════════
def ad(slot_index=0):
    slot = AD_SLOTS[min(slot_index, len(AD_SLOTS) - 1)]
    return f"""
<ins class="adsbygoogle"
 style="display:block"
 data-ad-client="{ADSENSE_CLIENT}"
 data-ad-slot="{slot}"
 data-ad-format="auto"
 data-full-width-responsive="true"></ins>
<script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
"""

# ═══════════════════════════════════════════════════════════
# DEMAND ENGINE
# ═══════════════════════════════════════════════════════════
BUYER_WORDS = ["best", "vs", "review", "under", "top", "cheap", "budget", "premium"]

GEO_EXCLUDE = [
    "india", "canada", "australia", "uk", "europe",
    "uae", "pakistan", "bangladesh", "nigeria", "philippines"
]

JUNK_WORDS = ["wallpaper", "case", "cover", "theme", "ringtone", "skin", "sticker"]

def get_suggestions(q):
    url = "https://suggestqueries.google.com/complete/search"

    params = {
        "client": "firefox",
        "q": q
    }

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    # -------------------------
    # SIMPLE IN-MEMORY + DISK CACHE
    # -------------------------
    if not hasattr(get_suggestions, "CACHE"):
        cache = {}
        if os.path.exists(SUGGESTION_CACHE_FILE):
            try:
                with open(SUGGESTION_CACHE_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        cache = {k: v for k, v in loaded.items() if isinstance(v, list)}
            except Exception:
                cache = {}
        get_suggestions.CACHE = cache

    if q in get_suggestions.CACHE:
        return get_suggestions.CACHE[q]

    # -------------------------
    # RETRY + BACKOFF
    # -------------------------
    import time

    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=5)

            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                    result = data[1]
                    get_suggestions.CACHE[q] = result
                    ensure_dir(os.path.dirname(SUGGESTION_CACHE_FILE) or ".")
                    safe_write(SUGGESTION_CACHE_FILE, json.dumps(get_suggestions.CACHE, indent=2))
                    return result

            # handle rate limiting / soft blocks
            if r.status_code in (429, 403):
                time.sleep(1 + attempt)

        except Exception:
            time.sleep(0.5 + attempt)

    return []

def build_keywords():
    base_keywords = set(build_keyword_universe(PHONES, max_keywords=MAX_KEYWORDS))
    suggestion_seeds = list(base_keywords)[:120]

    for seed in suggestion_seeds:
        suggestions = get_suggestions(seed)
        for kw in suggestions[:4]:
            if not isinstance(kw, str):
                continue
            kw = kw.lower()
            if len(kw.split()) < 3:
                continue
            if any(x in kw for x in JUNK_WORDS):
                continue
            if any(x in kw for x in GEO_EXCLUDE):
                continue
            if not any(x in kw for x in BUYER_WORDS):
                continue
            base_keywords.add(kw)
            if len(base_keywords) >= MAX_KEYWORDS:
                break
        if len(base_keywords) >= MAX_KEYWORDS:
            break

    return process_keywords(list(base_keywords), limit=MAX_KEYWORDS)
    

def load_or_generate_benchmarks():
    ensure_dir("data/benchmarks")

    files = {
        "cpu": "data/benchmarks/cpu_scores.json",
        "gpu": "data/benchmarks/gpu_scores.json",
        "battery": "data/benchmarks/battery_tests.json"
    }

    data = {}

    for k, path in files.items():
        if os.path.exists(path):
            with open(path, "r") as f:
                try:
                    data[k] = json.load(f)
                except:
                    data[k] = {}
        else:
            data[k] = {}

    # fallback synthetic scores
    for p in PHONES:
        slug = p["slug"]
        data["cpu"].setdefault(slug, get_spec(p, "ram") * 120 + random.randint(0, 50))
        data["gpu"].setdefault(slug, get_spec(p, "ram") * 150 + random.randint(0, 70))
        data["battery"].setdefault(slug, get_spec(p, "battery"))

    return data
    


def amazon_link(p):
    base = "https://www.amazon.com/s?k="
    query = p["name"].replace(" ", "+")
    return f"{base}{query}&tag={AMAZON_TAG}"


def amazon_cta(p):
    link = amazon_link(p)
    price = safe_price(p)

    return f"""
<div style="margin:20px 0;padding:16px;border:1px solid #ddd;border-radius:10px;background:#fffbea">
<strong>🔥 Check Latest Price</strong><br>
<span style="color:#2e7d32;font-weight:bold">${price} (approx)</span><br><br>

<a href="{link}" target="_blank" rel="nofollow sponsored"
style="display:inline-block;padding:10px 16px;background:#ff9900;color:#000;font-weight:bold;border-radius:6px;text-decoration:none">
View on Amazon →
</a>

<p style="font-size:12px;color:#777;margin-top:8px">
Price may vary. Check latest offer on Amazon.
</p>
</div>
"""    

def process_keywords(keywords, limit=MAX_KEYWORDS):
    freq = Counter(keywords)
    processed = []

    for kw, count in freq.items():
        if len(kw.split()) < 3:
            continue
        if any(x in kw for x in JUNK_WORDS):
            continue
        if any(x in kw for x in GEO_EXCLUDE):
            continue
        if not any(x in kw for x in BUYER_WORDS):
            continue

        score = count
        if "vs"      in kw: score += 5
        if "under"   in kw: score += 4
        if "best"    in kw: score += 3
        if "review"  in kw: score += 2
        if "gaming"  in kw: score += 3
        if "camera"  in kw: score += 3
        if "battery" in kw: score += 3

        processed.append((kw, score))

    processed.sort(key=lambda x: x[1], reverse=True)
    return [k for k, _ in processed[:limit]]

# ═══════════════════════════════════════════════════════════
# PEER GROUP + PRICE-TIER ANALYSIS
# ═══════════════════════════════════════════════════════════
def get_peer_group(p, window=75):
    price = safe_price(p)
    if price == 0:
        return []
    return [
        x for x in PHONES
        if x != p
        and safe_price(x) > 0
        and abs(safe_price(x) - price) <= window
    ]

def peer_avg(peers, key):
    vals = [get_spec(x, key) for x in peers if get_spec(x, key) > 0]
    return sum(vals) / len(vals) if vals else 0

def relative_analysis(p):
    peers = get_peer_group(p)
    if len(peers) < 2:
        return f"{p['name']} operates in a relatively unique price point with limited direct competition."

    avg_battery = peer_avg(peers, "battery")
    avg_ram     = peer_avg(peers, "ram")
    avg_camera  = peer_avg(peers, "camera")

    def diff_line(val, avg, label, unit=""):
        if not avg or val == 0:
            return ""
        diff = int((val - avg) / avg * 100)
        if abs(diff) < 5:
            return f"{label} ({val}{unit}) is on par with similar phones"
        if diff > 0:
            quality = "among the best in segment" if diff > 20 else "above average"
            return f"{label} ({val}{unit}) is {diff}% better than similar phones — {quality}"
        return f"{label} ({val}{unit}) is {abs(diff)}% below the average for this price range"

    lines = [
        diff_line(get_spec(p, "battery"), avg_battery, "Battery", "mAh"),
        diff_line(get_spec(p, "ram"),     avg_ram,     "RAM",     "GB"),
        diff_line(get_spec(p, "camera"),  avg_camera,  "Camera",  "MP"),
    ]
    return ". ".join(x for x in lines if x) + "."

# ═══════════════════════════════════════════════════════════
# DECISION ENGINE
# ═══════════════════════════════════════════════════════════
def decision_engine(p):
    ram     = get_spec(p, "ram")
    battery = get_spec(p, "battery")
    camera  = get_spec(p, "camera")
    price   = safe_price(p)

    buy   = []
    avoid = []

    if ram >= 8 and battery >= 4500:
        buy.append("heavy gaming and multitasking without constant charging")
    if battery >= 5000:
        buy.append("all-day or multi-day battery life for screen-heavy users")
    if camera >= 64:
        buy.append("high-resolution photos and social media content creation")
    if price < 400:
        buy.append("great value for budget-conscious buyers")

    if 0 < ram < 6:
        avoid.append("intensive gaming or running many apps simultaneously")
    if 0 < battery < 4000:
        avoid.append("full-day heavy usage without access to a charger")
    if 0 < camera < 48:
        avoid.append("serious photography or detailed content creation")

    return {
        "buy":   ", ".join(buy)   or "general everyday use",
        "avoid": ", ".join(avoid) or "none in particular for this price segment"
    }

# ═══════════════════════════════════════════════════════════
# CLUSTER ENGINE
# ═══════════════════════════════════════════════════════════
def get_cluster(p):
    return classify_phone(p)

# ═══════════════════════════════════════════════════════════
# INTENT FILTER
# ═══════════════════════════════════════════════════════════
def filter_by_intent(keyword, phones):
    return choose_keyword_devices(keyword, phones, limit=max(8, len(phones)))


LINK_GRAPH_FILE = "data/internal_link_graph.json"

def load_link_graph():
    if not os.path.exists(LINK_GRAPH_FILE):
        return {}
    try:
        with open(LINK_GRAPH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

LINK_GRAPH = load_link_graph()

def render_link_graph_section(source_url, sections, limit=6):
    items = []
    seen = set()
    for section in sections:
        for link in LINK_GRAPH.get(section, []):
            if link.get("from") != source_url:
                continue
            target = link.get("to")
            anchor = link.get("anchor") or "related guide"
            if not target or target in seen:
                continue
            seen.add(target)
            items.append(f'<li><a href="{SITE_DOMAIN}{target}">{anchor}</a></li>')
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    return f"<ul>{''.join(items)}</ul>" if items else "<p>More related guides will be added as this cluster expands.</p>"

# ═══════════════════════════════════════════════════════════
# INTERNAL LINKING
# ═══════════════════════════════════════════════════════════
def global_links():
    top = sorted(PHONES, key=lambda x: x.get("score", 50), reverse=True)[:5]
    items = "".join(
        f'<li><a href="{SITE_DOMAIN}/phones/{p["slug"]}.html">{p["name"]}</a></li>'
        for p in top
    )
    return f"<ul>{items}</ul>"

def smart_links(p):
    peers = get_peer_group(p, window=75)

    # inject high authority pages also
    top_global = rank_phones(PHONES)[:3]
    seen = set()
    unique = []

    for x in peers + top_global:
        if x['slug'] not in seen:
            seen.add(x['slug'])
            unique.append(x)

    peers = unique

    peers = sorted(
        peers,
        key=lambda x: authority_score_v2(
            f"/phones/{x['slug']}.html",
            base_links=len(get_peer_group(x)),
            content_depth=600
        ),
        reverse=True
    )[:5]
    if not peers:
        return ""
    items = "".join(
        f'<li><a href="{SITE_DOMAIN}/phones/{x["slug"]}.html">{x["name"]}</a>'
        f' — {price_bucket_label(x)}</li>'
        for x in peers
    )
    return f"<ul>{items}</ul>"

def behavior_script():
    return """
<script>
let start = Date.now();

window.addEventListener("scroll", () => {
    let scroll = (window.scrollY / document.body.scrollHeight) * 100;

    if (scroll > 30) document.body.classList.add("scroll-mid");
    if (scroll > 70) document.body.classList.add("scroll-deep");
});

setTimeout(() => {
    document.body.classList.add("engaged-10s");
}, 10000);

setTimeout(() => {
    document.body.classList.add("engaged-30s");
}, 30000);
</script>
"""



# ═══════════════════════════════════════════════════════════
# SEO HELPERS
# ═══════════════════════════════════════════════════════════
def title_tag(t):
    safe = t.replace("<", "&lt;").replace(">", "&gt;")
    return f"<title>{safe}</title>"

def meta_desc(t):
    safe = t[:150].replace('"', "&quot;")
    return f'<meta name="description" content="{safe}">'

def canonical(path):
    return f'<link rel="canonical" href="{SITE_DOMAIN}{path}">'

def og_tags(title, description, url_path, image_url=""):
    safe_title = title.replace('"', "&quot;")[:100]
    safe_desc  = description.replace('"', "&quot;")[:150]
    img = image_url if image_url.startswith("http") else f"{SITE_DOMAIN}{image_url}"
    img_tag = f'<meta property="og:image" content="{img}">' if image_url else ""
    return f"""
<meta property="og:title" content="{safe_title}">
<meta property="og:description" content="{safe_desc}">
<meta property="og:type" content="article">
<meta property="og:url" content="{SITE_DOMAIN}{url_path}">
<meta property="og:site_name" content="{SITE_NAME}">
{img_tag}
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{safe_title}">
<meta name="twitter:description" content="{safe_desc}">
"""

def json_ld_product(p):
    price = safe_price(p)
    brand = p.get("brand", p["name"].split()[0])

    # -------------------------
    # IMAGE SAFE HANDLING
    # -------------------------
    img_url = ""
    images = p.get("images", [])
    if images and isinstance(images, list) and len(images) > 0:
        first = images[0]
        img_url = first if first.startswith("http") else f"{SITE_DOMAIN}/{first}"

    # -------------------------
    # CORE STRUCTURED DATA
    # -------------------------
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": p["name"],
        "description": f"{p['name']} — {get_spec(p,'ram')}GB RAM, {get_spec(p,'battery')}mAh battery, {get_spec(p,'camera')}MP camera. Reviewed for {NOW_YEAR}.",
        "brand": {
            "@type": "Brand",
            "name": brand
        },
        "offers": {
            "@type": "Offer",
            "price": str(price),
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
            "url": f"{SITE_DOMAIN}/phones/{p['slug']}.html"
        },
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": str(min(5.0, max(3.0, round(p.get('score', 70) / 20, 1)))),
            "reviewCount": str(max(10, p.get('score', 70) // 5)),
            "bestRating": "5",
            "worstRating": "1"
        }
    }

    # -------------------------
    # OPTIONAL IMAGE (NO TRAILING COMMA BUG)
    # -------------------------
    if img_url:
        data["image"] = img_url

    # -------------------------
    # FINAL OUTPUT (SAFE JSON)
    # -------------------------
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'

def json_ld_breadcrumb(items):
    pairs = [
        f'{{"@type":"ListItem","position":{i+1},"name":"{name}","item":"{SITE_DOMAIN}{url}"}}'
        for i, (name, url) in enumerate(items)
    ]
    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [{", ".join(pairs)}]
}}
</script>"""

def json_ld_itemlist(phones, list_name, url_path):
    items = [
        f'{{"@type":"ListItem","position":{i+1},"url":"{SITE_DOMAIN}/phones/{p["slug"]}.html","name":"{p["name"]}"}}'
        for i, p in enumerate(phones[:10])
    ]
    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "ItemList",
  "name": "{list_name}",
  "url": "{SITE_DOMAIN}{url_path}",
  "itemListElement": [{", ".join(items)}]
}}
</script>"""

# ═══════════════════════════════════════════════════════════
# SHARED CSS
# ═══════════════════════════════════════════════════════════
PAGE_CSS = """
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.7;background:#f4f6f8;color:#222}
main{max-width:820px;margin:24px auto;padding:24px;background:#fff;border-radius:8px;border:1px solid #e0e0e0}
h1{font-size:1.9em;margin-bottom:12px;color:#111}
h2{font-size:1.35em;margin:28px 0 10px;color:#222;border-bottom:2px solid #f0f0f0;padding-bottom:6px}
h3{font-size:1.1em;margin:18px 0 8px;color:#333}
p{margin-bottom:14px}
ul,ol{margin:0 0 16px 20px}
li{margin-bottom:6px}
a{color:#1a73e8;text-decoration:none}
a:hover{text-decoration:underline}
table{width:100%;border-collapse:collapse;margin:16px 0;font-size:15px}
th{background:#f0f4f8;text-align:left;padding:10px 12px;border:1px solid #ddd}
td{padding:10px 12px;border:1px solid #ddd}
tr:nth-child(even){background:#fafafa}
.winner{background:#e8f5e9;font-weight:bold}
.pros-cons{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}
.pros{background:#e8f5e9;border-radius:6px;padding:14px}
.cons{background:#fff3e0;border-radius:6px;padding:14px}
.pros h3{color:#2e7d32}.cons h3{color:#e65100}
.author{font-size:13px;color:#666;margin:20px 0 10px;padding:10px;background:#f9f9f9;border-left:3px solid #1a73e8}
.breadcrumb{font-size:13px;color:#666;margin-bottom:16px}
.breadcrumb a{color:#666}
.scenario-box{background:#e3f2fd;border-radius:6px;padding:14px;margin:16px 0}
.cluster-tag{display:inline-block;background:#1a73e8;color:#fff;font-size:12px;padding:3px 10px;border-radius:20px;margin-bottom:12px}
img{max-width:100%;height:auto;border-radius:6px;margin:12px 0}
footer{text-align:center;padding:20px;font-size:13px;color:#999}
@media(max-width:600px){main{margin:8px;padding:14px}.pros-cons{grid-template-columns:1fr}}
</style>
"""

# ═══════════════════════════════════════════════════════════
# CONTENT BLOCKS
# ═══════════════════════════════════════════════════════════
def long_intro(p):
    price  = safe_price(p)
    brand  = p.get("brand", p["name"].split()[0])
    peers  = get_peer_group(p)
    brands = Counter(x.get("brand", x["name"].split()[0]) for x in peers if x != p)
    top_competitor_brands = ", ".join(b for b, _ in brands.most_common(3) if b != brand)
    competitor_str = f" It competes closely with devices from {top_competitor_brands}." if top_competitor_brands else ""

    return f"""<p>The <strong>{p['name']}</strong> sits in the <strong>{price_bucket_label(p)}</strong> price range,
targeting users who want a balance of performance and value in {NOW_YEAR}.{competitor_str}
With {get_spec(p,'ram')}GB RAM, a {get_spec(p,'battery')}mAh battery, and a {get_spec(p,'camera')}MP camera,
this guide breaks down whether it actually delivers — and who it is best suited for.</p>"""

def deeper_analysis_block(p):
    peers = get_peer_group(p)
    if len(peers) < 2:
        return f"<p>{p['name']} is a relatively unique option in its price range with limited direct comparisons available.</p>"

    avg_battery = round(peer_avg(peers, "battery"))
    avg_ram     = round(peer_avg(peers, "ram"), 1)
    avg_camera  = round(peer_avg(peers, "camera"))

    bat = get_spec(p, "battery")
    ram = get_spec(p, "ram")
    cam = get_spec(p, "camera")

    scene = ""
    if bat >= 5000 and bat > avg_battery:
        scene += f"Users who stream video, scroll social media, or game heavily will notice meaningfully better stamina compared to most {price_bucket_label(p)} rivals. "
    if ram >= 8 and ram > avg_ram:
        scene += f"Keeping 10+ apps open simultaneously runs smoother than you'd expect at this price. "
    if cam >= 64 and cam > avg_camera:
        scene += f"The {cam}MP camera produces detailed shots well above what the price tag suggests. "
    if not scene:
        scene = f"For most everyday tasks — browsing, streaming, messaging — it handles itself reliably in this price tier."

    return f"""
<h2>In-Depth Analysis</h2>
<p>In the <strong>{price_bucket_label(p)}</strong> segment, here is how {p['name']} stacks up against {len(peers)} comparable devices:</p>
<ul>
  <li><strong>Battery:</strong> {bat}mAh vs segment average of {avg_battery}mAh
    {"— stronger endurance than most rivals" if bat > avg_battery else "— on the lower side for this price range"}</li>
  <li><strong>RAM:</strong> {ram}GB vs segment average of {avg_ram}GB
    {"— above average for multitasking" if ram > avg_ram else "— average for this tier"}</li>
  <li><strong>Camera:</strong> {cam}MP vs segment average of {avg_camera}MP
    {"— higher resolution sensor than most competitors here" if cam > avg_camera else "— standard for the price range"}</li>
</ul>
<p>{scene}</p>
"""

def user_scenario(p):
    price   = safe_price(p)
    ram     = get_spec(p, "ram")
    battery = get_spec(p, "battery")
    camera  = get_spec(p, "camera")

    if price < 250 and ram >= 6 and battery >= 4500:
        return "best suited for budget-conscious buyers who need solid battery life and smooth daily performance without overspending."
    if price < 400 and ram >= 8 and battery >= 5000:
        return "one of the strongest value-for-money choices for heavy daily users and gamers in this price range."
    if price >= 500 and camera >= 64:
        return "a strong pick for photography-focused users and content creators who are willing to invest in camera quality."
    if ram >= 12 and battery >= 5000:
        return "an excellent option for power users and mobile gamers who demand top-tier performance and endurance."
    return "a reliable mid-range option that strikes a reasonable balance between performance, battery, and everyday usability."

def pros_cons_block(p):
    peers   = get_peer_group(p)
    avg_bat = peer_avg(peers, "battery") if peers else 4500
    avg_ram = peer_avg(peers, "ram")     if peers else 6
    avg_cam = peer_avg(peers, "camera")  if peers else 50

    pros = []
    cons = []

    if get_spec(p, "battery") >= max(avg_bat, 5000):
        pros.append("Excellent battery endurance for heavy use")
    elif get_spec(p, "battery") >= 4500:
        pros.append("Decent battery life for typical daily use")
    else:
        cons.append("Battery may not last a full day under heavy use")

    if get_spec(p, "ram") >= max(avg_ram, 8):
        pros.append("Above-average RAM for smooth multitasking and gaming")
    elif get_spec(p, "ram") >= 6:
        pros.append("Adequate RAM for most daily tasks")
    else:
        cons.append("Limited RAM may cause slowdowns with heavy app usage")

    if get_spec(p, "camera") >= max(avg_cam, 64):
        pros.append("High-resolution camera suitable for content creation")
    elif get_spec(p, "camera") >= 48:
        pros.append("Capable camera for casual photography")
    else:
        cons.append("Camera is average — not ideal for serious photography")

    if safe_price(p) < 350:
        pros.append("Competitive price for the specs offered")

    pros_html = "".join(f"<li>{x}</li>" for x in pros)
    cons_html = "".join(f"<li>{x}</li>" for x in cons) or "<li>No major drawbacks for its price tier</li>"

    return f"""
<div class="pros-cons">
  <div class="pros">
    <h3>Pros</h3>
    <ul>{pros_html}</ul>
  </div>
  <div class="cons">
    <h3>Cons</h3>
    <ul>{cons_html}</ul>
  </div>
</div>
"""

def author_block():
    return f'<div class="author">Reviewed by <strong>{AUTHOR_NAME}</strong> &mdash; {TODAY}</div>'

def breadcrumb_html(items):
    parts = " &rsaquo; ".join(
        f'<a href="{SITE_DOMAIN}{url}">{name}</a>' if url else name
        for name, url in items
    )
    return f'<nav class="breadcrumb">{parts}</nav>'

def footer_html():
    return f"""
<footer>
  <p>&copy; {NOW_YEAR} {SITE_NAME} &mdash;
  <a href="{SITE_DOMAIN}/about.html">About</a> &bull;
  <a href="{SITE_DOMAIN}/sitemap.xml">Sitemap</a>
  </p>
</footer>
"""

# ═══════════════════════════════════════════════════════════
# PAGE: PHONE
# ═══════════════════════════════════════════════════════════
def render_phone_page(p):
    d       = decision_engine(p)
    cluster = get_cluster(p)
    slug = p.get("slug", slugify(p["name"]))
    url     = f"/phones/{slug}.html"

    title = generate_title(p)

    desc = (
        f"{p['name']} review: {get_spec(p,'ram')}GB RAM, "
        f"{get_spec(p,'battery')}mAh battery, {get_spec(p,'camera')}MP camera. "
        f"Is it worth buying in {NOW_YEAR}? Full analysis with pros, cons, and comparisons."
    )

    # -------------------------
    # IMAGE
    # -------------------------
    img_tag = ""
    img_url = ""
    images  = p.get("images", [])

    if images and isinstance(images, list) and len(images) > 0:
        src = images[0]
        if not src.startswith("http"):
            src = f"{SITE_DOMAIN}/{src}"

        alt = p.get("alt_text") or f"{p['name']} smartphone review {NOW_YEAR}"

        img_tag = f'<img src="{src}" alt="{alt}" loading="lazy" width="600" height="400">'
        img_url = images[0]

    # -------------------------
    # BREADCRUMB
    # -------------------------
    bc_items = [("Home", "/"), ("Phones", "/phones/"), (p["name"], url)]

    # -------------------------
    # CONTENT VARIATION PATTERN
    # -------------------------
    pattern = content_pattern(p)

    if pattern == "A":
        intro_block    = long_intro_v2(p) + long_intro(p)
        analysis_block = deeper_analysis_block(p)
    elif pattern == "B":
        intro_block    = long_intro(p)
        analysis_block = deeper_analysis_block(p) + long_intro_v2(p)
    else:
        intro_block    = long_intro_v2(p)
        analysis_block = long_intro(p) + deeper_analysis_block(p)

    html_intro = intro_block + analysis_block
    bench = load_or_generate_benchmarks()
    cpu_score = bench["cpu"].get(slug, 0)
    gpu_score = bench["gpu"].get(slug, 0)
    battery_score = bench["battery"].get(slug, 0)

    benchmark_block = f"""
    <h2>Performance Benchmarks</h2>
    <ul>
    <li><strong>CPU Score:</strong> {cpu_score}</li>
    <li><strong>GPU Score:</strong> {gpu_score}</li>
    <li><strong>Battery Score:</strong> {battery_score}</li>
    </ul>
    """

    # -------------------------
    # BASE HTML
    # -------------------------
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{title_tag(title)}
{meta_desc(desc)}
{canonical(url)}
{og_tags(title, desc, url, img_url)}
{json_ld_product(p)}
{json_ld_breadcrumb(bc_items)}
{PAGE_CSS}
</head>
<body>
<main>
{breadcrumb_html(bc_items)}
<span class="cluster-tag">{cluster.capitalize()} Phone</span>
<h1>{title}</h1>

{ad(0)}

{img_tag}

{author_block()}

{html_intro}

{ad(1)}


{amazon_cta(p)}

<h2>Pros &amp; Cons</h2>
{pros_cons_v2(p)}
{pros_cons_block(p)}

<h2>Who Should Buy This</h2>
<div class="scenario-box">
  <p><strong>{p['name']}</strong> is {user_scenario(p)}</p>
  <p><strong>Buy if you want:</strong> {d['buy']}.</p>
  <p><strong>Avoid if you need:</strong> {d['avoid']}.</p>
</div>

<h2>How It Compares to Similar Phones</h2>
<p>Here are phones in the same price range worth considering:</p>

{smart_links(p)}

<h2>Best Buying Guides for This Phone</h2>
{render_link_graph_section(f"/phones/{slug}.html", ["phone_to_keywords", "phone_to_cluster"], limit=6)}

<!-- 🔥 AUTHORITY FUNNEL -->
<h2>Top Rated Phones Right Now</h2>
{global_links_weighted(p['slug'])}

<h2>Direct Comparisons</h2>
"""

    # -------------------------
    # COMPARE LINKS (FIXED INDENT)
    # -------------------------
    peers = get_peer_group(p, window=75)[:4]

    if peers:
        html += "<ul>"
        for x in peers:
            html += f'<li><a href="{SITE_DOMAIN}/compare/{slug}-vs-{x["slug"]}.html">{p["name"]} vs {x["name"]}</a></li>\n'
        html += "</ul>"
    else:
        html += f"<p>No direct comparison pages available yet for {p['name']}.</p>"

    # -------------------------
    # FINAL SECTION (NO DUPLICATION)
    # -------------------------
    html += f"""
<h2>Explore Similar Phones</h2>
<p>Browse all phones in the <a href="{SITE_DOMAIN}/cluster/{cluster}.html">{cluster.capitalize()} phones</a> category.</p>

{ad(2)}
</main>
{footer_html()}
{behavior_script()}
</body>
</html>
"""

    return html
# ═══════════════════════════════════════════════════════════
# PAGE: COMPARE
# ═══════════════════════════════════════════════════════════
def render_compare(p1, p2):
    def pct(a, b):
        if b == 0: return 0
        return int((a - b) / b * 100)

    b1, b2 = get_spec(p1, "battery"), get_spec(p2, "battery")
    c1, c2 = get_spec(p1, "camera"),  get_spec(p2, "camera")
    r1, r2 = get_spec(p1, "ram"),     get_spec(p2, "ram")
    pr1    = safe_price(p1)
    pr2    = safe_price(p2)

    bdiff = pct(b1, b2)
    cdiff = pct(c1, c2)
    rdiff = pct(r1, r2)

    def winner_name(v1, v2, ph1, ph2):
        return ph1["name"] if v1 >= v2 else ph2["name"]

    bwinner = winner_name(b1, b2, p1, p2)
    cwinner = winner_name(c1, c2, p1, p2)
    rwinner = winner_name(r1, r2, p1, p2)

    slug  = f"{p1['slug']}-vs-{p2['slug']}"
    url   = f"/compare/{slug}.html"
    title = f"{p1['name']} vs {p2['name']} ({NOW_YEAR}) — Which Is Better?"
    desc  = (
        f"Detailed comparison: {p1['name']} vs {p2['name']}. "
        f"Battery, camera, RAM, price — who wins in {NOW_YEAR}?"
    )

    # Conditional final recommendation
    recs = []
    if abs(bdiff) >= 15:
        better = p1["name"] if bdiff > 0 else p2["name"]
        recs.append(f"<li>Choose <strong>{better}</strong> if battery endurance is your top priority — it leads by {abs(bdiff)}%.</li>")
    if abs(cdiff) >= 20:
        better = p1["name"] if cdiff > 0 else p2["name"]
        recs.append(f"<li>Choose <strong>{better}</strong> if camera quality matters most — {abs(cdiff)}% more megapixels.</li>")
    if abs(rdiff) >= 20:
        better = p1["name"] if rdiff > 0 else p2["name"]
        recs.append(f"<li>Choose <strong>{better}</strong> for gaming and multitasking — {abs(rdiff)}% more RAM.</li>")
    if abs(pr1 - pr2) >= 50:
        cheaper = p1["name"] if pr1 < pr2 else p2["name"]
        recs.append(f"<li>Choose <strong>{cheaper}</strong> if budget is the main constraint — it's ${abs(pr1-pr2)} less.</li>")
    if not recs:
        recs.append(f"<li>Both phones are closely matched. Choose based on brand preference or availability near you.</li>")

    bc_items = [
        ("Home", "/"),
        ("Compare", "/compare/"),
        (f"{p1['name']} vs {p2['name']}", url)
    ]

    # winner class helper
    def wc(v1, v2):
        if v1 > v2:   return "winner", ""
        if v1 < v2:   return "",       "winner"
        return "", ""

    bw1, bw2 = wc(b1, b2)
    cw1, cw2 = wc(c1, c2)
    rw1, rw2 = wc(r1, r2)
    pw1, pw2 = wc(pr2, pr1)  # lower price wins

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{title_tag(title)}
{meta_desc(desc)}
{canonical(url)}
{og_tags(title, desc, url)}
{json_ld_breadcrumb(bc_items)}
{PAGE_CSS}
</head>
<body>
<main>
{breadcrumb_html(bc_items)}
<h1>{p1['name']} vs {p2['name']}</h1>
{ad(0)}
<p>This side-by-side comparison covers every key spec difference between {p1['name']} and {p2['name']}
to help you pick the right phone in {NOW_YEAR}.</p>

<h2>Spec Comparison</h2>
<table>
<thead>
  <tr><th>Spec</th><th>{p1['name']}</th><th>{p2['name']}</th></tr>
</thead>
<tbody>
  <tr><td><strong>Price</strong></td>
      <td class="{pw1}">${pr1}</td>
      <td class="{pw2}">${pr2}</td></tr>
  <tr><td><strong>Battery</strong></td>
      <td class="{bw1}">{b1}mAh</td>
      <td class="{bw2}">{b2}mAh</td></tr>
  <tr><td><strong>RAM</strong></td>
      <td class="{rw1}">{r1}GB</td>
      <td class="{rw2}">{r2}GB</td></tr>
  <tr><td><strong>Camera</strong></td>
      <td class="{cw1}">{c1}MP</td>
      <td class="{cw2}">{c2}MP</td></tr>
</tbody>
</table>
<p style="font-size:13px;color:#666">Green = winner in that category.</p>

{ad(1)}

<h2>Category Winners</h2>
<ul>
  <li><strong>Battery:</strong> {bwinner} wins
    {"by " + str(abs(bdiff)) + "% — meaningfully longer endurance" if abs(bdiff) >= 10 else "— both are closely matched"}</li>
  <li><strong>Camera:</strong> {cwinner} wins
    {"by " + str(abs(cdiff)) + "% — noticeably higher resolution" if abs(cdiff) >= 15 else "— both are comparable"}</li>
  <li><strong>Performance (RAM):</strong> {rwinner} wins
    {"by " + str(abs(rdiff)) + "% — better for gaming and multitasking" if abs(rdiff) >= 15 else "— both handle daily tasks similarly"}</li>
  <li><strong>Value:</strong> {'$'+str(pr1)+' ('+p1['name']+')' if pr1 < pr2 else '$'+str(pr2)+' ('+p2['name']+')'} is the more budget-friendly option</li>
</ul>

<h2>Our Recommendation</h2>
<ul>
{"".join(recs)}
</ul>

<h2>Individual Reviews</h2>
<ul>
  <li><a href="{SITE_DOMAIN}/phones/{p1['slug']}.html">Full {p1['name']} review</a></li>
  <li><a href="{SITE_DOMAIN}/phones/{p2['slug']}.html">Full {p2['name']} review</a></li>
</ul>

<h2>Top Phones Right Now</h2>
{global_links_weighted(p1['slug'])}
{ad(2)}
</main>
{footer_html()}
{behavior_script()}
</body>
</html>"""
    return html


# ═══════════════════════════════════════════════════════════
# 🔥 QUERY INTENT ENGINE
# ═══════════════════════════════════════════════════════════

def detect_intent(keyword):
    kw = keyword.lower()

    if "vs" in kw:
        return "comparison"
    if "best" in kw or "top" in kw:
        return "commercial"
    if "review" in kw:
        return "transactional"
    if "under" in kw:
        return "budget"
    return "informational"


def intent_intro(keyword, intent):
    if intent == "comparison":
        return f"If you're comparing options for {keyword}, this breakdown highlights the key differences that actually matter in real usage."
    if intent == "commercial":
        return f"Choosing the right phone for {keyword} depends on performance, battery, and long-term value. Here are the top picks."
    if intent == "transactional":
        return f"This {keyword} review focuses on real-world performance, not just specs, so you can decide if it's worth buying."
    if intent == "budget":
        return f"Finding the best value for {keyword} means balancing performance and price. These are the strongest options right now."
    return f"Here’s everything you need to know about {keyword}."


def intent_cta(intent, p):
    if intent == "comparison":
        return f"Compare full specs of {p['name']} before deciding."
    if intent == "commercial":
        return f"Check full review of {p['name']} before buying."
    if intent == "transactional":
        return f"See if {p['name']} is still worth buying."
    if intent == "budget":
        return f"See how {p['name']} performs for the price."
    return f"Explore full details of {p['name']}."


# ═══════════════════════════════════════════════════════════
# PAGE: KEYWORD
# ═══════════════════════════════════════════════════════════
def render_keyword_page(keyword, phones_sorted):
    filtered = filter_by_intent(keyword, phones_sorted)
    phones = filtered[:5]
    intent = detect_intent(keyword)
    slug    = slugify(keyword)
    url     = f"/keyword/{slug}.html"

    # intent-aware title and description
    if "gaming" in keyword:
        title = f"Best Gaming Phones — {keyword.title()} ({NOW_YEAR})"
        intro = f"Looking for the best gaming phone? We ranked the top picks for <strong>{keyword}</strong> based on RAM, processor, and real-world gaming performance in {NOW_YEAR}."
    elif "camera" in keyword:
        title = f"Best Camera Phones — {keyword.title()} ({NOW_YEAR})"
        intro = f"Camera quality varies wildly at every price point. Here are the top picks for <strong>{keyword}</strong>, ranked by megapixels, aperture, and real-world shot quality."
    elif "battery" in keyword:
        title = f"Best Battery Phones — {keyword.title()} ({NOW_YEAR})"
        intro = f"If you need a phone that lasts all day (or longer), here are the top picks for <strong>{keyword}</strong>, ranked by battery capacity and efficiency."
    elif "under" in keyword:
        title = f"{keyword.title()} — Best Value Picks ({NOW_YEAR})"
        intro = f"Finding a great phone on a budget is all about knowing the right trade-offs. Here are the top picks for <strong>{keyword}</strong>, ranked by performance per dollar."
    else:
        title = f"{keyword.title()} — Top Picks ({NOW_YEAR})"
        intro = f"This guide covers the best options for <strong>{keyword}</strong>, compared by specs, value, and real-world usability in {NOW_YEAR}."

    desc = f"{keyword.title()} — top {len(phones)} picks ranked by specs, price and real-world value in {NOW_YEAR}. Updated {TODAY}."

    bc_items = [("Home", "/"), ("Keywords", "/keyword/"), (keyword.title(), url)]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{title_tag(title)}
{meta_desc(desc)}
{canonical(url)}
{og_tags(title, desc, url)}
{json_ld_itemlist(phones, title, url)}
{json_ld_breadcrumb(bc_items)}
{PAGE_CSS}
</head>
<body>
<main>
{breadcrumb_html(bc_items)}
<h1>{title}</h1>
{ad(0)}
<p>{intent_intro(keyword, intent)}</p>
"""

    for i, p in enumerate(phones, 1):
        d = decision_engine(p)
        html += f"""
<h2>{i}. {p['name']} — ${safe_price(p)}</h2>
<p>{relative_analysis(p)}</p>
<p><strong>Best for:</strong> {d['buy']}.</p>
<p><em>{intent_cta(intent, p)}</em></p>
<p><strong>Avoid if:</strong> {d['avoid']}.</p>
<p><strong>Top Picks:</strong></p>
<p><a href="{SITE_DOMAIN}/phones/{p['slug']}.html">Full {p['name']} review &rarr;</a></p>
{amazon_cta(p)}
"""
        if i == 2:
            html += ad(1)

    html += f"""
<h2>Top Phones Right Now</h2>
{global_links_weighted(keyword)}
<h2>Related Buying Guides</h2>
{render_link_graph_section(url, ["keyword_to_phones", "keyword_to_cluster"], limit=8)}
{ad(2)}
</main>
{footer_html()}
{behavior_script()}
</body>
</html>"""
    return html

# ═══════════════════════════════════════════════════════════
# PAGE: CLUSTER
# ═══════════════════════════════════════════════════════════
CLUSTER_META = {
    "battery": {
        "title":  f"Best Battery Phones ({NOW_YEAR}) — All-Day & Multi-Day Endurance",
        "desc":   f"Top phones with the longest battery life in {NOW_YEAR}. Ranked by mAh, real-world usage, and price.",
        "intro":  "Battery life is the number one complaint about smartphones. These phones solve it.",
    },
    "camera": {
        "title":  f"Best Camera Phones ({NOW_YEAR}) — Top Picks for Photography",
        "desc":   f"The best camera phones of {NOW_YEAR} ranked by megapixels, low-light performance, and value.",
        "intro":  "Camera quality varies enormously at every price tier. These phones deliver the best results for their cost.",
    },
    "gaming": {
        "title":  f"Best Gaming Phones ({NOW_YEAR}) — High RAM, High Performance",
        "desc":   f"Best phones for mobile gaming in {NOW_YEAR}. Ranked by RAM, processor speed, and gaming performance.",
        "intro":  "Mobile gaming demands RAM, cooling, and a fast display. Here are the phones that deliver.",
    },
    "budget": {
        "title":  f"Best Budget Phones ({NOW_YEAR}) — Best Value Under $300",
        "desc":   f"The best budget smartphones of {NOW_YEAR}. Maximum value, minimum spend.",
        "intro":  "You don't need to spend a fortune to get a reliable smartphone in {NOW_YEAR}. These phones prove it.",
    },
}

def render_cluster_page(cluster, phones):
    meta  = CLUSTER_META.get(cluster, {
        "title": f"Best {cluster.capitalize()} Phones ({NOW_YEAR})",
        "desc":  f"Top {cluster} phones of {NOW_YEAR} ranked by specs and value.",
        "intro": f"Explore the best {cluster} phones available in {NOW_YEAR}."
    })
    url   = f"/cluster/{cluster}.html"
    bc_items = [("Home", "/"), ("Categories", "/cluster/"), (cluster.capitalize(), url)]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{title_tag(meta['title'])}
{meta_desc(meta['desc'])}
{canonical(url)}
{og_tags(meta['title'], meta['desc'], url)}
{json_ld_itemlist(phones, meta['title'], url)}
{json_ld_breadcrumb(bc_items)}
{PAGE_CSS}
</head>
<body>
<main>
{breadcrumb_html(bc_items)}
<h1>{meta['title']}</h1>
{ad(0)}
<p>{meta['intro']}</p>
"""

    for i, p in enumerate(phones[:10], 1):
        d = decision_engine(p)
        html += f"""
<h2>{i}. {p['name']} — ${safe_price(p)}</h2>
<p>{relative_analysis(p)}</p>
<p><strong>Best for:</strong> {d['buy']}.</p>
<p><a href="{SITE_DOMAIN}/phones/{p['slug']}.html">Full review &rarr;</a></p>
{amazon_cta(p)}
"""
        if i == 3:
            html += ad(1)

    html += f"""
<h2>All Top Phones</h2>
{global_links_weighted(cluster)}
<h2>Best Related Buying Guides</h2>
{render_link_graph_section(url, ["cluster_to_keywords"], limit=8)}
{ad(2)}
</main>
{footer_html()}
{behavior_script()}
</body>
</html>"""
    return html

# ═══════════════════════════════════════════════════════════
# PAGE: ABOUT
# ═══════════════════════════════════════════════════════════
def render_about_page():
    title = f"About {SITE_NAME} — How We Review and Rank Phones"
    desc  = f"{SITE_NAME} provides data-driven phone reviews and comparisons for US buyers in {NOW_YEAR}."
    url   = "/about.html"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{title_tag(title)}
{meta_desc(desc)}
{canonical(url)}
{PAGE_CSS}
</head>
<body>
<main>
<h1>About {SITE_NAME}</h1>
<p>{SITE_NAME} is an independent phone review and comparison resource for US buyers.
We use structured spec data, price-tier benchmarking, and real-world usage analysis
to help readers find the right phone at the right price.</p>

<h2>How We Rank Phones</h2>
<p>Every phone is evaluated on three core dimensions: battery endurance relative to peers
in the same price tier, RAM and performance for its intended use case, and camera capability
for the target buyer. We do not accept payments for rankings or reviews.</p>

<h2>Editorial Team</h2>
<p>Content is produced by the <strong>{AUTHOR_NAME}</strong>. Our analysis is updated regularly
to reflect current prices and availability in the US market.</p>

<h2>Data Sources</h2>
<p>Spec data is sourced from manufacturer specifications and cross-referenced with
publicly available benchmark databases. Prices reflect typical US retail at time of publication.</p>

<h2>Contact</h2>
<p>For corrections or editorial inquiries, reach us via the contact form on this site.</p>
</main>
{footer_html()}
{behavior_script()}
</body>
</html>"""

# ═══════════════════════════════════════════════════════════
# SITEMAP
# ═══════════════════════════════════════════════════════════
def generate_sitemap(phone_urls, compare_urls, keyword_urls, cluster_urls, topic_urls):
    path = os.path.join(BASE_DIR, "sitemap.xml")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')

            # Phone pages — highest priority
            for u in phone_urls:
                f.write(f"""  <url>
    <loc>{SITE_DOMAIN}{u}</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.9</priority>
  </url>\n""")

            # Cluster pages
            for u in cluster_urls:
                f.write(f"""  <url>
    <loc>{SITE_DOMAIN}{u}</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.85</priority>
  </url>\n""")
            for u in topic_urls:
                f.write(f"""  <url>
    <loc>{SITE_DOMAIN}{u}</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.75</priority>
    </url>\n""")
            # Compare pages
            for u in compare_urls:
                f.write(f"""  <url>
    <loc>{SITE_DOMAIN}{u}</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>\n""")

            # Keyword pages
            for u in keyword_urls:
                f.write(f"""  <url>
    <loc>{SITE_DOMAIN}{u}</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>\n""")

            f.write("</urlset>")
    except OSError as e:
        print(f"[ERROR] Sitemap generation failed: {e}")

# ═══════════════════════════════════════════════════════════
# ROBOTS.TXT
# ═══════════════════════════════════════════════════════════
def generate_robots():
    content = f"""User-agent: *
Allow: /
Disallow: /data/
Disallow: /logs/
Disallow: /tmp/
Disallow: /admin/
Disallow: /*.json$

Sitemap: {SITE_DOMAIN}/sitemap.xml
"""
    safe_write(os.path.join(BASE_DIR, "robots.txt"), content)

# ═══════════════════════════════════════════════════════════
# INDEXNOW PING (faster Bing indexing, Google follows signals)
# ═══════════════════════════════════════════════════════════
def ping_indexnow(urls, api_key="YOUR_INDEXNOW_KEY"):
    if api_key == "YOUR_INDEXNOW_KEY":
        print("[INFO] IndexNow skipped — set your API key in ping_indexnow()")
        return
    try:
        payload = {
            "host": SITE_DOMAIN.replace("https://", ""),
            "key": api_key,
            "urlList": [f"{SITE_DOMAIN}{u}" for u in urls[:100]]
        }
        r = requests.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"[IndexNow] Status: {r.status_code}")
    except Exception as e:
        print(f"[IndexNow] Failed: {e}")


# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# 🔥 BACKLINK + AUTHORITY ENGINE (INTEGRATED)
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

def authority_score(page_type, links=0, backlinks=0, content_depth=300):
    return (links * 2) + (backlinks * 5) + min(content_depth // 100, 10)


def init_backlink_tracker():
    ensure_dir("data/backlinks")
    path = "data/backlinks/tracker.json"

    if os.path.exists(path):
        return  # DO NOT overwrite existing data

    tracker = {
        "outreach_sent": [],
        "responses": [],
        "links_acquired": []
    }

    safe_write(path, json.dumps(tracker, indent=2))


def render_author_page():
    return f"""<!DOCTYPE html>
<html><body>
<h1>{AUTHOR_NAME}</h1>
<p>We evaluate smartphones using structured benchmarking and real-world usage scenarios.</p>
{behavior_script()}
</body></html>
"""


def render_editorial_policy():
    return f"""<!DOCTYPE html>
<html><body>
<h1>Editorial Policy</h1>
<p>All rankings are independent, data-driven, and not influenced by advertisers.</p>
{behavior_script()}
</body></html>
"""


def render_methodology():
    return f"""<!DOCTYPE html>
<html><body>
<h1>Methodology</h1>
<p>Devices are evaluated on battery, performance, camera, and price-to-value ratio.</p>
{behavior_script()}
</body></html>
"""


def run_authority_engine(keywords):
    print("[AUTHORITY] Init only (no generation in page_generator)")
    if not os.path.exists(TRACKER_FILE):
        init_backlink_tracker()

# ═══════════════════════════════════════════════════════════
# 🔥 ADVANCED AUTHORITY + CONTROL LAYER
# ═══════════════════════════════════════════════════════════

# -------------------------
# BACKLINK INGESTION
# -------------------------
def load_live_backlinks():
    if not os.path.exists(BACKLINK_DB):
        return {}

    try:
        with open(BACKLINK_DB, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {x["url"]: x.get("count", 1) for x in data}
    except:
        return {}


LIVE_BACKLINKS = load_live_backlinks()

LIVE_BACKLINKS = {
    k.replace(SITE_DOMAIN, ""): v
    for k, v in LIVE_BACKLINKS.items()
}


# -------------------------
# ENHANCED AUTHORITY SCORE
# -------------------------
def authority_score_v2(page_url, base_links=0, content_depth=300):
    backlinks = LIVE_BACKLINKS.get(page_url, 0)

    score = 0
    score += backlinks * 12
    score += base_links * 3 # heavier weight
    score += min(content_depth // 100, 10)

    return score

def generate_title(p):
    price = safe_price(p)
    return variant([
        f"{p['name']} Review ({NOW_YEAR}) - Worth ${price}?",
        f"{p['name']} Review ({NOW_YEAR}) - Pros & Cons After Testing",
        f"{p['name']} Review ({NOW_YEAR}) - Should You Buy It?",
        f"{p['name']} Review ({NOW_YEAR}) - Real Performance Test",
    ], p['slug'], "title")


# -------------------------
# PRIORITIZED GLOBAL LINKS
# -------------------------
def global_links_weighted(context=None):
    scored = []

    for p in PHONES:
        url = f"/phones/{p['slug']}.html"
        score = authority_score_v2(
            url,
            base_links=len(get_peer_group(p)),
            content_depth=600
        )
        scored.append((score, p))

    top = sorted(scored, key=lambda x: x[0], reverse=True)

    # 🔥 diversify per page context
    if context:
        seed = abs(hash(context)) % len(top)
        top = top[seed:] + top[:seed]

    top = top[:5]

    items = "".join(
        f'<li><a href="{SITE_DOMAIN}/phones/{p["slug"]}.html">{p["name"]}</a></li>'
        for _, p in top
    )
    return f"<ul>{items}</ul>"


# -------------------------
# TRACKER PATH (READ-ONLY INIT SUPPORT)
# -------------------------
TRACKER_FILE = "data/backlinks/tracker.json"


# -------------------------
# CONTENT VARIATION ENGINE
# -------------------------
import random


def variant(texts, seed=None, salt=""):
    base = f"{seed}-{salt}"
    rnd = random.Random(base)
    return rnd.choice(texts)

def content_pattern(p):
    patterns = ["A", "B", "C"]
    return variant(patterns, p['slug'])

def long_intro_v2(p):
    variants = [
        f"{p['name']} targets users looking for balanced performance and value in {NOW_YEAR}.",
        f"In {NOW_YEAR}, {p['name']} positions itself as a strong contender in its price tier.",
        f"If you're evaluating options in this segment, {p['name']} is one of the key devices to consider.",
    ]
    return f"<p>{variant(variants, p['slug'], 'intro')}</p>"


def pros_cons_v2(p):
    bat = get_spec(p, "battery")
    ram = get_spec(p, "ram")
    cam = get_spec(p, "camera")

    pros = []
    cons = []

    if bat >= 5000:
        pros.append("Strong battery life for extended daily use")
    elif bat >= 4500:
        pros.append("Decent battery backup for most users")
    else:
        cons.append("Battery may struggle under heavy usage")

    if ram >= 8:
        pros.append("Handles multitasking and gaming smoothly")
    elif ram >= 6:
        pros.append("Good for regular apps and moderate usage")
    else:
        cons.append("Limited RAM for demanding apps")

    if cam >= 64:
        pros.append("High resolution camera for detailed photos")
    elif cam >= 48:
        pros.append("Good camera for everyday photography")
    else:
        cons.append("Camera not ideal for detailed shots")

    return f"""
<div class="pros-cons">
<div class="pros"><ul>{"".join(f"<li>{x}</li>" for x in pros)}</ul></div>
<div class="cons"><ul>{"".join(f"<li>{x}</li>" for x in cons or ['No major drawbacks in this segment'])}</ul></div>
</div>
"""

def rank_phones(phones):
    scored = []
    for p in phones:
        url = f"/phones/{p['slug']}.html"
        peer_count = len(get_peer_group(p))
        internal_links = peer_count
        content_depth = 600  # approx words

        score = authority_score_v2(url, base_links=internal_links, content_depth=content_depth)
        scored.append((score, p))
    return [p for _, p in sorted(scored, key=lambda x: x[0], reverse=True)]

def render_topic_page(topic, phones):
    url = f"/topics/{topic}.html"

    intro_map = {
        "gaming": "Gaming phones require high RAM, sustained performance, and thermal control.",
        "camera": "Camera phones are judged by real-world results, not just megapixels.",
        "battery": "Battery life defines real usability for most users.",
    }

    intro = intro_map.get(topic, f"Best {topic} phones explained.")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
{title_tag(f"Best {topic} Phones ({NOW_YEAR})")}
{PAGE_CSS}
</head>
<body>
<main>
<h1>Best {topic} Phones</h1>
<p>{intro}</p>

{global_links_weighted(topic)}
"""
    html += f"""
<h2>What Makes a Good {topic.capitalize()} Phone?</h2>
<p>
Choosing the right {topic} phone depends on how the hardware translates into real-world usage.
For {topic} use cases, factors like RAM capacity, sustained performance, battery endurance,
and thermal efficiency matter more than raw specs alone.
</p>

<h2>{topic.capitalize()} Performance vs Battery Trade-Off</h2>
<p>
In this category, there is often a trade-off between performance and battery life.
Higher performance components typically consume more power, while optimized devices
balance efficiency with sustained output. Understanding this trade-off helps in choosing
the right device for your usage pattern.
</p>

<h2>How Much RAM Is Enough for {topic.capitalize()}?</h2>
<p>
RAM plays a critical role in multitasking and long-session performance.
Devices with higher RAM tend to maintain stability under load, while lower RAM devices
may experience slowdowns during extended usage or heavy app switching.
</p>
"""

    for p in phones[:10]:
        html += f"""
<h2>{p['name']}</h2>
<p>{relative_analysis(p)}</p>
<p><a href="{SITE_DOMAIN}/phones/{p['slug']}.html">Full review</a></p>
"""

    html += f"""
{behavior_script()}
</main>
</body>
</html>
"""
    return html

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# 🔥 PATCH INTO EXISTING RUN()
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# >>> UPDATED START
from seo_growth_utils import (
    generate_keyword_clusters,
    build_keyword_page_map,
    anti_thin_content_guard,
    semantic_sections_template,
    select_title_variant,
)

KEYWORD_CLUSTER_FILE = "data/keyword_clusters.json"
KEYWORD_MAP_FILE = "data/keyword_page_map.json"
SITEMAP_DIR = os.path.join(BASE_DIR, "sitemaps")
MAX_PHONE_PAGES = int(os.environ.get("MAX_PHONE_PAGES", "1000"))
MAX_KEYWORD_PAGES = int(os.environ.get("MAX_KEYWORD_PAGES", "2600"))
MAX_TOPIC_PAGES = int(os.environ.get("MAX_TOPIC_PAGES", "80"))
MAX_COMPARE_PAGES = int(os.environ.get("MAX_COMPARE_PAGES", "650"))


def ctr_title_variants(base_title, keyword, page_kind, year=NOW_YEAR):
    return [
        f"{base_title} ({year})",
        f"{base_title}: What Most Buyers Miss in {year}",
        f"{base_title} vs Alternatives: What Actually Wins ({year})",
        f"{base_title} — Faster Decision Guide for {year}",
        f"{base_title}: Avoid Costly Mistakes Before You Buy",
        f"{base_title} — Best Picks, Trade-Offs, and Buyer Fit",
        f"{keyword.title()} Guide: Better Choices in Minutes",
        f"{base_title} (Updated {TODAY})",
    ]


def keyword_sections(keyword):
    blocks = semantic_sections_template("phone buying", keyword)
    blocks.update({
        "intro": f"This page maps {keyword} to the strongest options and decision paths.",
        "decision_framework": f"For {keyword}, prioritize fit > spec count > headline marketing claims.",
        "comparison_logic": f"Compare models on battery endurance, thermal stability, camera consistency, and price delta.",
        "real_examples": f"Typical journeys for {keyword}: commute-heavy users, creators, and budget-sensitive buyers.",
    })
    return blocks


def render_keyword_page_v2(keyword, phones_sorted, keyword_map):
    mapping = keyword_map.get("keywords", {}).get(keyword)
    if not mapping:
        return ""
    phones = [p for p in phones_sorted if f"/phones/{p['slug']}.html" in mapping.get("supporting_phone_pages", [])][:6]
    if not phones:
        phones = filter_by_intent(keyword, phones_sorted)[:6]

    slug = mapping["keyword_slug"]
    url = mapping["keyword_url"]
    base_title = f"{keyword.title()}"
    title = select_title_variant(slug, ctr_title_variants(base_title, keyword, "keyword"))
    desc = f"{keyword.title()} mapped to best-fit phones, alternatives, and comparison paths. Updated {TODAY}."
    blocks = keyword_sections(keyword)
    if not anti_thin_content_guard(blocks, min_blocks=8):
        return ""

    inline_links = []
    for p in phones[:6]:
        inline_links.append(f'<a href="{SITE_DOMAIN}/phones/{p["slug"]}.html">{p["name"]}</a>')
    for c in mapping.get("supporting_compare_pages", [])[:4]:
        inline_links.append(f'<a href="{SITE_DOMAIN}{c}">comparison breakdown</a>')
    inline_links = inline_links[:10]

    structural_links = [
        f'<li><a href="{SITE_DOMAIN}{mapping["cluster_url"]}">Cluster hub</a></li>',
        f'<li><a href="{SITE_DOMAIN}{mapping["topic_url"]}">Topic authority page</a></li>',
    ]
    structural_links.extend([f'<li><a href="{SITE_DOMAIN}{c}">Decision comparison</a></li>' for c in mapping.get("supporting_compare_pages", [])[:3]])

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
{title_tag(title)}
{meta_desc(desc)}
{canonical(url)}
{og_tags(title, desc, url)}
{PAGE_CSS}
</head><body><main>
<h1>{title}</h1>
<p>{blocks['intro']}</p>
<p>{blocks['who_should_buy']}</p>
<p>{blocks['who_should_not_buy']}</p>
<p>{blocks['hidden_tradeoffs']}</p>
<p>{blocks['real_world_usage']}</p>
<p>{blocks['better_alternatives']}</p>
<h2>Who should buy this</h2><p>{blocks['who_should_buy']}</p>
<h2>Who should NOT buy this</h2><p>{blocks['who_should_not_buy']}</p>
<h2>Hidden trade-offs</h2><p>{blocks['hidden_tradeoffs']}</p>
<h2>Real-world usage breakdown</h2><p>{blocks['real_world_usage']}</p>
<h2>Better alternatives</h2><p>{blocks['better_alternatives']}</p>
<h2>Decision Framework</h2><p>{blocks['decision_framework']}</p>
<h2>Comparison Logic</h2><p>{blocks['comparison_logic']}</p>
<p>{' | '.join(inline_links[:5])}</p>
<p>{' | '.join(inline_links[5:10])}</p>
<h2>Supporting Pages</h2>
<ul>{''.join(structural_links[:5])}</ul>
{ad(1)}
</main>{footer_html()}{behavior_script()}</body></html>"""
    return html


def render_topic_page_v2(cluster, keyword_map):
    topic_slug = cluster["cluster_slug"]
    url = f"/topics/{topic_slug}.html"
    base_title = f"{cluster['brand'].title()} {cluster['feature'].title()} Phones for {cluster['scenario'].title()}"
    title = select_title_variant(topic_slug, ctr_title_variants(base_title, cluster['pillar_keyword'], "topic"))
    blocks = semantic_sections_template(cluster['feature'], cluster['pillar_keyword'])
    blocks.update({"intro": f"Cluster hub for {cluster['pillar_keyword']}", "decision_framework": "Rank by fit, value, and real-use outcomes.", "comparison_logic": "Compare against alternatives and adjacent price tiers.", "real_examples": "Use-case mapping for daily workflows."})
    if not anti_thin_content_guard(blocks, min_blocks=8):
        return ""

    kwords = cluster.get("all_keywords", [])[:20]
    links = []
    for kw in kwords:
        km = keyword_map.get("keywords", {}).get(kw)
        if km:
            links.append(f'<li><a href="{SITE_DOMAIN}{km["keyword_url"]}">{kw}</a></li>')

    return f"""<!DOCTYPE html>
<html lang="en"><head>{title_tag(title)}{meta_desc(title)}{canonical(url)}{PAGE_CSS}</head>
<body><main>
<h1>{title}</h1>
<p>{blocks['intro']}</p>
<h2>Concept explanation</h2><p>{blocks['decision_framework']}</p>
<h2>Real-world scenarios</h2><p>{blocks['real_examples']}</p>
<h2>Decision framework</h2><p>{blocks['who_should_buy']} {blocks['who_should_not_buy']}</p>
<h2>Comparison logic</h2><p>{blocks['comparison_logic']}</p>
<h2>Who should buy this</h2><p>{blocks['who_should_buy']}</p>
<h2>Who should NOT buy this</h2><p>{blocks['who_should_not_buy']}</p>
<h2>Hidden trade-offs</h2><p>{blocks['hidden_tradeoffs']}</p>
<h2>Real-world usage breakdown</h2><p>{blocks['real_world_usage']}</p>
<h2>Better alternatives</h2><p>{blocks['better_alternatives']}</p>
<ul>{''.join(links[:20])}</ul>
</main>{footer_html()}{behavior_script()}</body></html>"""


def generate_sitemap_segments(phone_urls, compare_urls, keyword_urls, cluster_urls, topic_urls):
    ensure_dir(SITEMAP_DIR)

    def write_segment(name, urls, priority):
        path = os.path.join(SITEMAP_DIR, f"sitemap-{name}.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
            for u in urls:
                f.write(f"<url><loc>{SITE_DOMAIN}{u}</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>{priority}</priority></url>\n")
            f.write('</urlset>')

    write_segment("phones", phone_urls, "0.80")
    write_segment("keywords", keyword_urls, "0.65")
    write_segment("clusters", cluster_urls, "0.92")
    write_segment("topics", topic_urls, "0.95")
    write_segment("compare", compare_urls, "0.55")

    idx_path = os.path.join(BASE_DIR, "sitemap.xml")
    segments = ["phones", "keywords", "clusters", "topics", "compare"]
    with open(idx_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for s in segments:
            f.write(f"<sitemap><loc>{SITE_DOMAIN}/sitemaps/sitemap-{s}.xml</loc><lastmod>{TODAY}</lastmod></sitemap>\n")
        f.write('</sitemapindex>')


def run():
    print(f"=== {SITE_NAME} SEO BUILD — CLUSTER AUTHORITY MODE ===")
    phone_urls, compare_urls, keyword_urls, cluster_urls, topic_urls = [], [], [], [], []

    phones_sorted = rank_phones(PHONES)[:MAX_PHONE_PAGES]

    cluster_data = generate_keyword_clusters(phones_sorted, min_keywords=5000, max_keywords=10000, min_clusters=100, max_clusters=300)
    save_json_helper(KEYWORD_CLUSTER_FILE, cluster_data)
    keyword_map = build_keyword_page_map(cluster_data, phones_sorted)
    save_json_helper(KEYWORD_MAP_FILE, keyword_map)

    all_keywords = list(keyword_map.get("keywords", {}).keys())[:MAX_KEYWORD_PAGES]
    LINK_GRAPH.update(build_link_graph(phones_sorted, all_keywords, keyword_map=keyword_map))
    save_json_helper(LINK_GRAPH_FILE, LINK_GRAPH)

    pp = os.path.join(BASE_DIR, "phones")
    cp = os.path.join(BASE_DIR, "compare")
    kp = os.path.join(BASE_DIR, "keyword")
    cl = os.path.join(BASE_DIR, "cluster")
    tp = os.path.join(BASE_DIR, "topics")
    for d in [pp, cp, kp, cl, tp]:
        ensure_dir(d)

    for p in phones_sorted:
        slug = p.get("slug", slugify(p["name"]))
        path = os.path.join(pp, slug + ".html")
        safe_write(path, render_phone_page(p))
        phone_urls.append(f"/phones/{slug}.html")

    compare_count = 0
    compare_pool = phones_sorted[:45]
    for i in range(len(compare_pool)):
        for j in range(i + 1, len(compare_pool)):
            if compare_count >= MAX_COMPARE_PAGES:
                break
            p1, p2 = compare_pool[i], compare_pool[j]
            slug = f"{p1['slug']}-vs-{p2['slug']}"
            safe_write(os.path.join(cp, slug + ".html"), render_compare(p1, p2))
            compare_urls.append(f"/compare/{slug}.html")
            compare_count += 1
        if compare_count >= MAX_COMPARE_PAGES:
            break

    for kw in all_keywords:
        mapping = keyword_map["keywords"][kw]
        page = render_keyword_page_v2(kw, phones_sorted, keyword_map)
        if not page:
            continue
        safe_write(os.path.join(kp, mapping["keyword_slug"] + ".html"), page)
        keyword_urls.append(mapping["keyword_url"])

    for cluster in cluster_data.get("clusters", []):
        cslug = cluster["cluster_slug"]
        pages = [keyword_map["keywords"][k] for k in cluster.get("all_keywords", []) if k in keyword_map.get("keywords", {})][:20]
        links = ''.join(f'<li><a href="{SITE_DOMAIN}{m["keyword_url"]}">{k}</a></li>' for k, m in [(k, keyword_map["keywords"][k]) for k in cluster.get("all_keywords", [])[:20] if k in keyword_map.get("keywords", {})])
        html = f"""<!DOCTYPE html><html><head>{title_tag(cluster['pillar_keyword'].title())}{PAGE_CSS}</head><body><main>
<h1>{cluster['pillar_keyword'].title()}</h1>
<h2>Concept explanation</h2><p>Cluster authority hub for {cluster['feature']} decisions.</p>
<h2>Real-world scenarios</h2><p>Use case: {cluster['scenario']} with budget and performance balancing.</p>
<h2>Decision framework</h2><p>Map to phones, then compare options, then final shortlist.</p>
<h2>Comparison logic</h2><p>Battery, camera consistency, RAM stability, and price delta.</p>
<h2>Who should buy this</h2><p>Users aligned with {cluster['scenario']} needs.</p>
<h2>Who should NOT buy this</h2><p>Buyers needing ultra-premium edge-case capabilities.</p>
<h2>Hidden trade-offs</h2><p>Lower cost can reduce sustained performance and camera reliability.</p>
<h2>Real-world usage breakdown</h2><p>Different usage profiles will produce different winners.</p>
<h2>Better alternatives</h2><p>Use linked pages to evaluate stronger alternatives.</p>
<ul>{links}</ul></main>{footer_html()}</body></html>"""
        safe_write(os.path.join(cl, cslug + ".html"), html)
        cluster_urls.append(f"/cluster/{cslug}.html")

    for cluster in cluster_data.get("clusters", [])[:MAX_TOPIC_PAGES]:
        topic_html = render_topic_page_v2(cluster, keyword_map)
        if not topic_html:
            continue
        safe_write(os.path.join(tp, cluster["cluster_slug"] + ".html"), topic_html)
        topic_urls.append(f"/topics/{cluster['cluster_slug']}.html")

    safe_write(KEYWORD_FILE, json.dumps(all_keywords, indent=2))
    generate_sitemap_segments(phone_urls, compare_urls, keyword_urls, cluster_urls, topic_urls)
    generate_robots()
    ping_indexnow((phone_urls + compare_urls + keyword_urls + cluster_urls + topic_urls)[:100])

    print(f"BUILD COMPLETE | phones={len(phone_urls)} keywords={len(keyword_urls)} compare={len(compare_urls)} topics={len(topic_urls)} clusters={len(cluster_urls)}")


if __name__ == "__main__":
    run()
# >>> UPDATED END
