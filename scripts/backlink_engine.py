import json
import os
import random
import datetime
import hashlib

KEYWORDS_FILE = "data/keywords.json"
OUTPUT_TARGETS = "data/backlinks/targets.json"
TRACKER_FILE = "data/backlinks/tracker.json"
OUTREACH_DIR = "site/outreach_posts"
INTERNAL_LINK_FILE = "data/internal_links.json"

TODAY = datetime.date.today().isoformat()

TOP_BRANDS = [
    "iphone", "apple", "samsung", "pixel", "oneplus",
    "xiaomi", "realme", "motorola", "oppo", "vivo"
]

INTENT_BUCKETS = [
    "camera", "battery", "gaming", "under $", "vs", "review"
]


# -------------------------
# LOAD INTERNAL LINKS
# -------------------------
def load_internal_links():
    path = "data/internal_links.json"

    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


# -------------------------
# RENDER INTERNAL LINKS HTML
# -------------------------
def render_internal_links(slug, internal_links):
    links = get_links_for_page(slug, internal_links)

    if not links:
        return ""

    html = "<h2>Related Guides</h2><ul>"

    for l in links:
        target_slug = l["to"].split("/")[-1].replace(".html", "")
        anchor = l.get("anchor", "related guide")

        html += f'<li><a href="/keyword/{target_slug}.html">{anchor}</a></li>'

    html += "</ul>"
    return html


# -------------------------
# GET LINKS FOR PAGE
# -------------------------
def get_links_for_page(slug, internal_links):
    links = []

    for link in internal_links:
        if link["from"].endswith(f"{slug}.html"):
            links.append(link)

    return links[:5]  # limit (SEO safe)




# -------------------------
# LOAD / SAVE
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
# FILTER KEYWORDS
# -------------------------
def filter_keywords(keywords):
    good = []

    for kw in keywords:
        kw_lower = kw.lower()

        if not any(b in kw_lower for b in TOP_BRANDS):
            continue

        if any(x in kw_lower for x in ["best", "review", "vs", "under $"]):
            good.append(kw)

    return good

# -------------------------
# PRIORITY ENGINE
# -------------------------
def prioritize_keywords(keywords):
    return sorted(
        keywords,
        key=lambda x: (
            "best" in x,
            "under $" in x,
            "vs" in x,
            "review" in x
        ),
        reverse=True
    )[:80]

# -------------------------
# DEEP CLUSTERING (FIXED)
# -------------------------
def group_clusters(keywords):
    clusters = {}

    for kw in keywords:
        kw_lower = kw.lower()

        brand = next((b for b in TOP_BRANDS if b in kw_lower), "general")
        intent = next((i for i in INTENT_BUCKETS if i in kw_lower), "general")

        key = f"{brand}_{intent}"

        clusters.setdefault(key, []).append(kw)

    return clusters

# -------------------------
# ANCHOR STRATEGY
# -------------------------
def generate_anchor(kw):
    t = random.choice(["exact", "partial", "branded"])

    if t == "exact":
        return kw
    elif t == "partial":
        return f"best {kw}"
    else:
        return "see full comparison"

# -------------------------
# PAGE WEIGHTING
# -------------------------
def assign_weights(kws):
    weighted = []

    for i, kw in enumerate(kws):
        if i == 0:
            weight = 5   # pillar
        elif i < 3:
            weight = 3
        else:
            weight = 1

        weighted.append((kw, weight))

    return weighted

# -------------------------
# TARGET ENGINE (UPGRADED)
# -------------------------
def generate_targets(clusters):
    targets = []

    for cluster, kws in clusters.items():
        weighted_kws = assign_weights(kws)

        for i, (kw, weight) in enumerate(weighted_kws):
            targets.append({
                "keyword": kw,
                "cluster": cluster,
                "is_pillar": i == 0,
                "weight": weight,
                "target_page": f"/keyword/{kw.replace(' ', '-')}.html",
                "anchor": generate_anchor(kw),

                # improved discovery targets
                "opportunities": [
                    f"https://www.google.com/search?q={kw.replace(' ', '+')}+blog",
                    f"https://www.google.com/search?q={kw.replace(' ', '+')}+guest+post",
                    f"https://www.google.com/search?q={kw.replace(' ', '+')}+write+for+us"
                ]
            })

    return targets

# -------------------------
# OUTREACH (UPGRADED)
# -------------------------
def generate_outreach_posts(clusters):
    os.makedirs(OUTREACH_DIR, exist_ok=True)

    for cluster, kws in list(clusters.items())[:10]:
        kw = kws[0]
        url = f"https://yoursite.com/keyword/{kw.replace(' ', '-')}.html"

        content = f"""
Hi,

I came across your content around "{kw}" and really liked your coverage.

We recently published a detailed guide:
{url}

It includes real comparisons, pros/cons, and buyer-focused insights.

Would love to contribute something tailored for your audience if you're open.

Best,
"""

        filename = hashlib.md5(kw.encode()).hexdigest()[:10] + ".txt"

        with open(os.path.join(OUTREACH_DIR, filename), "w") as f:
            f.write(content.strip())

# -------------------------
# INTERNAL LINKING ENGINE (NEW)
# -------------------------
def generate_internal_links(clusters):
    links = []

    for cluster, kws in clusters.items():
        if len(kws) < 2:
            continue

        pillar = kws[0]

        for kw in kws[1:]:
            links.append({
                "from": f"/keyword/{kw.replace(' ', '-')}.html",
                "to": f"/keyword/{pillar.replace(' ', '-')}.html",
                "anchor": pillar
            })

    save_json(INTERNAL_LINK_FILE, links)

# -------------------------
# TRACKER INIT
# -------------------------
def init_tracker():
    if not os.path.exists(TRACKER_FILE):
        save_json(TRACKER_FILE, {
            "outreach_sent": [],
            "links_acquired": [],
            "daily_velocity": []
        })

# -------------------------
# LINK VELOCITY
# -------------------------
def simulate_link_velocity():
    tracker = load_json(TRACKER_FILE, {})

    today_links = random.randint(1, 3)

    tracker.setdefault("daily_velocity", []).append({
        "date": TODAY,
        "links": today_links
    })

    for i in range(today_links):
        tracker.setdefault("links_acquired", []).append({
            "site": f"site{i}.com",
            "anchor_type": random.choice(["exact", "partial", "branded"]),
            "target": "keyword_page",
            "date": TODAY
        })

    save_json(TRACKER_FILE, tracker)

# -------------------------
# MAIN
# -------------------------
def run():
    print("[BACKLINK ENGINE - DOMINANCE MODE] Running...")

    keywords = load_json(KEYWORDS_FILE, [])
    keywords = filter_keywords(keywords)
    keywords = prioritize_keywords(keywords)

    if not keywords:
        print("[ERROR] No valid keywords after filtering")
        return

    clusters = group_clusters(keywords)

    targets = generate_targets(clusters)

    os.makedirs("data/backlinks", exist_ok=True)
    save_json(OUTPUT_TARGETS, targets)

    generate_outreach_posts(clusters)
    generate_internal_links(clusters)

    init_tracker()
    simulate_link_velocity()

    print(f"[BACKLINK ENGINE] Targets: {len(targets)} | Clusters: {len(clusters)}")

if __name__ == "__main__":
    run()
