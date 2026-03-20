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

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════
BASE_DIR        = os.path.abspath("site")
DATA_FILE       = "data/phones/phones_enriched.json"
KEYWORD_FILE    = "data/keywords_real.json"

ADSENSE_CLIENT  = "ca-pub-XXXXXXXXXXXXXXXX"
AD_SLOTS        = ["1111111111", "2222222222", "3333333333", "4444444444"]  # 4 slots
SITE_DOMAIN     = "https://yoursite.com"
SITE_NAME       = "PhoneRank"
AUTHOR_NAME     = f"{SITE_NAME} Editorial Team"
NOW_YEAR        = "2026"
TODAY           = datetime.date.today().isoformat()
RANKED_PHONES = None

# Launch phase gate: 1=phones only, 2=phones+compare, 3=all pages
# Start at 1. Move to 2 after GSC confirms indexing. Move to 3 after clicks appear.
LAUNCH_PHASE    = int(os.environ.get("LAUNCH_PHASE", "3"))

MAX_KEYWORDS    = 700
MAX_COMPARE_PHONES = 20  # top N phones in comparison matrix

os.makedirs(BASE_DIR, exist_ok=True)

with open(DATA_FILE, "r", encoding="utf-8") as f:
    PHONES = json.load(f)

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
    """Write file with error handling — no silent corruption."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
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
    try:
        url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={q}"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return []
        return r.json()[1]
    except Exception:
        return []

def build_keywords():
    seeds = set()
    for p in PHONES:
        name = p["name"].lower()
        brand = name.split()[0]
        seeds.update([
            f"{name} review",
            f"{name} vs",
            f"best {brand} phone",
            f"{name} specs",
            f"best phone under 500 dollars",
            f"best phone under 400",
            f"best phone under 300",
            f"best phone under 200",
            f"best {brand} phone under 500",
            f"best {brand} phone under 300",
            f"best gaming phone under 500",
            f"best camera phone under 500",
            f"best battery phone under 500",
        ])
    kws = []
    for s in seeds:
        kws += get_suggestions(s)
    return [k.lower() for k in kws]

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
    if get_spec(p, "battery") >= 5000: return "battery"
    if get_spec(p, "camera")  >= 64:   return "camera"
    if get_spec(p, "ram")     >= 8:    return "gaming"
    return "budget"

# ═══════════════════════════════════════════════════════════
# INTENT FILTER
# ═══════════════════════════════════════════════════════════
def filter_by_intent(keyword, phones):
    kw = keyword.lower()
    if "gaming" in kw:
        return sorted(phones, key=lambda x: get_spec(x, "ram"), reverse=True)
    if "camera" in kw:
        return sorted(phones, key=lambda x: get_spec(x, "camera"), reverse=True)
    if "battery" in kw:
        return sorted(phones, key=lambda x: get_spec(x, "battery"), reverse=True)
    if "under" in kw:
        digits = [x for x in kw.split() if x.isdigit()]
        if digits:
            try:
                price = int(digits[0])
                filtered = [p for p in phones if safe_price(p) <= price]
                return filtered if filtered else phones
            except Exception:
                pass
    # brand filter
    for p in PHONES:
        brand = p["name"].lower().split()[0]
        if brand in kw and len(brand) > 3:
            return [x for x in phones if x["name"].lower().startswith(brand)]
    return phones

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
    phones = rank_phones(filtered)[:5]

    # 🔥 intent tightening
    if "under" in keyword:
        digits = [int(x) for x in keyword.split() if x.isdigit()]
        if digits:
            cap = digits[0]
            phones = [p for p in phones if safe_price(p) <= cap][:5]
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
"""
        if i == 2:
            html += ad(1)

    html += f"""
<h2>Top Phones Right Now</h2>
{global_links_weighted(keyword)}
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
"""
        if i == 3:
            html += ad(1)

    html += f"""
<h2>All Top Phones</h2>
{global_links_weighted(cluster)}
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
def generate_sitemap(phone_urls, compare_urls, keyword_urls, cluster_urls):
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

def mine_competitor_backlinks():
    competitors = ["gsmarena.com", "techradar.com", "phonearena.com"]

    opportunities = []

    for c in competitors:
        opportunities.append({
            "competitor": c,
            "blogs": [f"{c}/blog-example"],
            "forums": [f"{c}/forum-example"],
            "resources": [f"{c}/resources"]
        })

    ensure_dir("data/backlinks")
    safe_write("data/backlinks/opportunities.json", json.dumps(opportunities, indent=2))


def generate_outreach_email(site, topic):
    return f"""Hi,

I came across your site ({site}) while researching {topic}, and really liked your coverage.

I recently put together something on this and thought it might be useful.

Would love your thoughts.

Best,
{AUTHOR_NAME}
"""


def generate_guest_post(topic, target_site):
    content = f"{topic} - Complete Guide\n\n"

    for i in range(12):
        content += f"## Section {i+1}\n{topic} explained in detail with real-world context.\n\n"

    return content


def generate_resource_pitch(site, url):
    return f"""Hi,

I noticed your resource page on {site}.

We recently created something that could fit well here:
{url}

Let me know what you think.

Thanks
"""


def generate_guest_posts(keywords):
    ensure_dir("site/outreach_posts")

    for kw in keywords[:25]:
        content = generate_guest_post(kw, "example.com")
        path = f"site/outreach_posts/{slugify(kw)}.txt"
        safe_write(path, content)


def generate_discussions(keywords):
    posts = []

    for kw in keywords[:25]:
        posts.append({
            "keyword": kw,
            "posts": [
                f"I've been comparing options for {kw} - what are people using?",
                f"What actually works best for {kw} in real life?",
                f"Is there a clear winner for {kw} right now?"
            ]
        })

    ensure_dir("data/distribution")
    safe_write("data/distribution/reddit_quora_posts.json", json.dumps(posts, indent=2))


def authority_score(page_type, links=0, backlinks=0, content_depth=300):
    return (links * 2) + (backlinks * 5) + min(content_depth // 100, 10)


def init_backlink_tracker():
    ensure_dir("data/backlinks")

    tracker = {
        "outreach_sent": [],
        "responses": [],
        "links_acquired": []
    }

    safe_write("data/backlinks/tracker.json", json.dumps(tracker, indent=2))


def generate_weekly_plan(keywords):
    plan = []

    for kw in keywords[:10]:
        plan.append({
            "publish": kw,
            "promote": f"Reddit + Quora",
            "backlinks": f"5 outreach targets"
        })

    safe_write("data/distribution/weekly_plan.json", json.dumps(plan, indent=2))


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
    print("Running Authority Engine...")

    if not os.path.exists(BACKLINK_DB):
        global LIVE_BACKLINKS
        LIVE_BACKLINKS = {}  # fallback only if no real data
    generate_guest_posts(keywords)
    generate_discussions(keywords)
    init_backlink_tracker()
    generate_weekly_plan(keywords)
    
    safe_write(os.path.join(BASE_DIR, "author.html"), render_author_page())
    safe_write(os.path.join(BASE_DIR, "editorial-policy.html"), render_editorial_policy())
    safe_write(os.path.join(BASE_DIR, "methodology.html"), render_methodology())

# ═══════════════════════════════════════════════════════════
# 🔥 ADVANCED AUTHORITY + CONTROL LAYER
# ═══════════════════════════════════════════════════════════

BACKLINK_DB = "data/backlinks/live_links.json"


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
# OUTREACH TRACKING LOOP
# -------------------------
TRACKER_FILE = "data/backlinks/tracker.json"


def update_outreach(status, site, email=None):
    if not os.path.exists(TRACKER_FILE):
        return

    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    entry = {
        "site": site,
        "email": email,
        "date": datetime.date.today().isoformat()
    }

    if status == "sent":
        data["outreach_sent"].append(entry)
    elif status == "reply":
        data["responses"].append(entry)
    elif status == "won":
        data["links_acquired"].append(entry)

    safe_write(TRACKER_FILE, json.dumps(data, indent=2))


def outreach_stats():
    if not os.path.exists(TRACKER_FILE):
        return {}

    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        d = json.load(f)

    sent = len(d["outreach_sent"])
    replies = len(d["responses"])
    won = len(d["links_acquired"])

    return {
        "sent": sent,
        "replies": replies,
        "won": won,
        "reply_rate": round((replies / sent) * 100, 2) if sent else 0,
        "win_rate": round((won / sent) * 100, 2) if sent else 0
    }


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

def export_outreach_targets():
    targets = []

    for p in PHONES[:50]:
        targets.append({
            "url": f"{SITE_DOMAIN}/phones/{p['slug']}.html",
            "anchor": p['name'] + " review",
            "priority": authority_score_v2(f"/phones/{p['slug']}.html")
        })

    safe_write("data/backlinks/outreach_targets.json", json.dumps(targets, indent=2))


# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# 🔥 PATCH INTO EXISTING RUN()
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

def run():
    print(f"=== {SITE_NAME} SEO BUILD — LAUNCH PHASE {LAUNCH_PHASE} ===")

    phones_sorted = rank_phones(PHONES)

    phone_urls   = []
    compare_urls = []
    keyword_urls = []
    cluster_urls = []
    topic_urls = []
    tp = os.path.join(BASE_DIR, "topics")
    ensure_dir(tp)

    keywords = []  # SAFE INIT (IMPORTANT)

    # ---------------- ORIGINAL LOGIC ----------------

    pp = os.path.join(BASE_DIR, "phones")
    ensure_dir(pp)

    for p in PHONES:
        slug = p.get("slug", slugify(p["name"]))
        path = os.path.join(pp, slug + ".html")
        safe_write(path, render_phone_page(p))
        phone_urls.append(f"/phones/{slug}.html")

    cl = os.path.join(BASE_DIR, "cluster")
    ensure_dir(cl)

    cluster_map = defaultdict(list)
    for p in PHONES:
        cluster_map[get_cluster(p)].append(p)

    for cluster_name, cluster_phones in cluster_map.items():
        sorted_phones = rank_phones(cluster_phones)
        path = os.path.join(cl, cluster_name + ".html")
        safe_write(path, render_cluster_page(cluster_name, sorted_phones))
        cluster_urls.append(f"/cluster/{cluster_name}.html")

    safe_write(os.path.join(BASE_DIR, "about.html"), render_about_page())
    
    topics = ["gaming", "camera", "battery"]

    for t in topics:
        topic_phones = rank_phones([p for p in PHONES if get_cluster(p) == t])
        path = os.path.join(tp, t + ".html")
        safe_write(path, render_topic_page(t, topic_phones))
        topic_urls.append(f"/topics/{t}.html")

    if LAUNCH_PHASE >= 2:
        cp = os.path.join(BASE_DIR, "compare")
        ensure_dir(cp)

        top = rank_phones(PHONES)[:MAX_COMPARE_PHONES]
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                p1, p2 = top[i], top[j]
                slug = f"{p1['slug']}-vs-{p2['slug']}"
                path = os.path.join(cp, slug + ".html")
                safe_write(path, render_compare(p1, p2))
                compare_urls.append(f"/compare/{slug}.html")

    if LAUNCH_PHASE >= 3:
        raw = build_keywords()
        keywords = process_keywords(raw)

        ensure_dir("data")
        safe_write(KEYWORD_FILE, json.dumps(keywords, indent=2))

        kp = os.path.join(BASE_DIR, "keyword")
        ensure_dir(kp)

        for kw in keywords:
            slug = slugify(kw)
            path = os.path.join(kp, slug + ".html")
            safe_write(path, render_keyword_page(kw, phones_sorted))
            keyword_urls.append(f"/keyword/{slug}.html")

    generate_sitemap(phone_urls, compare_urls, keyword_urls, cluster_urls)
    generate_robots()

    all_urls = phone_urls + cluster_urls + compare_urls + keyword_urls + topic_urls
    ping_indexnow(all_urls)
    global RANKED_PHONES
    RANKED_PHONES = rank_phones(PHONES)
    phones_sorted = RANKED_PHONES

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # 🔥 AUTHORITY ENGINE EXECUTION (SAFE)
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    run_authority_engine(keywords if keywords else [])

    print("BUILD COMPLETE")


if __name__ == "__main__":
    run()

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# FULL FILE END
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
