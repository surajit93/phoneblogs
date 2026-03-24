import datetime
import hashlib
import json
import os
import random
from collections import defaultdict

from seo_growth_utils import (
    anchor_variants,
    build_link_graph,
    choose_keyword_devices,
    keyword_intent,
    normalize_phones,
    save_json as save_json_helper,
    score_keyword_opportunity,
)

KEYWORDS_FILES = ["data/keywords_real.json", "data/keywords.json"]
PHONES_FILE = "data/phones/phones_enriched.json"
LINK_GRAPH_FILE = "data/internal_link_graph.json"
OUTPUT_TARGETS = "data/backlinks/targets.json"
TRACKER_FILE = "data/backlinks/tracker.json"
OUTREACH_DIR = "site/outreach_posts"
INTERNAL_LINK_FILE = "data/internal_links.json"

TODAY = datetime.date.today().isoformat()
TOP_BRANDS = ["iphone", "apple", "samsung", "pixel", "oneplus", "xiaomi", "motorola", "nothing"]
INTENT_BUCKETS = ["camera", "battery", "gaming", "under $", "vs", "review"]
DOMAIN_TIERS = [
    {"label": "editorial", "authority": 92, "weight": 1.0},
    {"label": "expert_blog", "authority": 76, "weight": 0.82},
    {"label": "niche_forum", "authority": 58, "weight": 0.56},
    {"label": "community", "authority": 42, "weight": 0.33},
]
HIGH_INTENT = {"comparison", "commercial", "budget", "review"}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_keywords():
    combined = []
    for path in KEYWORDS_FILES:
        data = load_json(path, [])
        if isinstance(data, list):
            combined.extend(data)
    deduped = []
    seen = set()
    for kw in combined:
        if not isinstance(kw, str):
            continue
        key = kw.strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


def filter_keywords(keywords):
    good = []
    for kw in keywords:
        kw_lower = kw.lower()
        if any(x in kw_lower for x in ["wallpaper", "case", "cover", "theme"]):
            continue
        if keyword_intent(kw_lower) in HIGH_INTENT:
            good.append(kw)
    return good


def prioritize_keywords(keywords):
    return sorted(keywords, key=lambda kw: score_keyword_opportunity(kw, []), reverse=True)[:320]


def group_clusters(keywords):
    clusters = defaultdict(list)
    for kw in keywords:
        kw_lower = kw.lower()
        brand = next((b for b in TOP_BRANDS if b in kw_lower), "general")
        intent = next((i for i in INTENT_BUCKETS if i in kw_lower), keyword_intent(kw_lower))
        clusters[f"{brand}_{intent}"].append(kw)
    for cluster in list(clusters.keys()):
        clusters[cluster] = sorted(clusters[cluster], key=lambda kw: score_keyword_opportunity(kw, []), reverse=True)
    return clusters


def generate_anchor(kw, is_pillar=False, phones=None):
    anchors = anchor_variants(kw, "pillar" if is_pillar else "keyword", phones=phones)
    return random.choice(anchors)


def assign_weights(kws):
    weighted = []
    for i, kw in enumerate(kws):
        weight = 8 if i == 0 else 5 if i < 4 else 3 if i < 10 else 1
        weighted.append((kw, weight))
    return weighted


def load_phones():
    return normalize_phones(load_json(PHONES_FILE, []))


def domain_quality(keyword, is_pillar=False):
    intent = keyword_intent(keyword)
    base = DOMAIN_TIERS[0] if is_pillar else DOMAIN_TIERS[1 if intent in HIGH_INTENT else 2]
    return {
        "tier": base["label"],
        "authority": base["authority"],
        "weight": base["weight"],
    }


def ctr_score(keyword):
    kw = keyword.lower()
    score = 10
    score += 6 if "under $" in kw else 0
    score += 8 if "vs" in kw else 0
    score += 5 if any(token in kw for token in ["best", "top", "review"]) else 0
    score += 4 if "usa" in kw else 0
    return score


def generate_targets(clusters, phones):
    targets = []
    for cluster, kws in clusters.items():
        weighted_kws = assign_weights(kws)
        for i, (kw, weight) in enumerate(weighted_kws):
            selected_phones = choose_keyword_devices(kw, phones, limit=3)
            quality = domain_quality(kw, is_pillar=i == 0)
            intent = keyword_intent(kw)
            target_slug = kw.replace(' ', '-')
            targets.append({
                "keyword": kw,
                "cluster": cluster,
                "intent": intent,
                "is_pillar": i == 0,
                "target_type": "pillar" if i == 0 else "support",
                "cluster_size": len(kws),
                "cluster_priority": max(len(kws), 1),
                "weight": weight,
                "authority_weight": round(quality["authority"] * quality["weight"], 2),
                "domain_tier": quality["tier"],
                "ctr_score": ctr_score(kw),
                "target_page": f"/keyword/{target_slug}.html",
                "supporting_reviews": [f"/phones/{p['slug']}.html" for p in selected_phones],
                "anchor": generate_anchor(kw, is_pillar=i == 0, phones=selected_phones[:1]),
                "anchor_variants": anchor_variants(kw, "pillar" if i == 0 else "keyword", phones=selected_phones[:1]),
                "opportunities": [
                    f"https://www.google.com/search?q={kw.replace(' ', '+')}+\"write+for+us\"",
                    f"https://www.google.com/search?q={kw.replace(' ', '+')}+guest+post",
                    f"https://www.google.com/search?q={kw.replace(' ', '+')}+\"submit+article\"",
                    f"https://www.google.com/search?q={kw.replace(' ', '+')}+expert+roundup",
                ],
            })
    return sorted(targets, key=lambda t: (t["authority_weight"], t["ctr_score"], t["weight"]), reverse=True)


def generate_outreach_posts(clusters):
    os.makedirs(OUTREACH_DIR, exist_ok=True)
    for cluster, kws in list(clusters.items())[:24]:
        kw = kws[0]
        url = f"https://yoursite.com/keyword/{kw.replace(' ', '-')}.html"
        intent = keyword_intent(kw)
        angle = {
            "comparison": "direct buying comparisons",
            "budget": "budget-focused recommendations",
            "review": "product-led testing insights",
            "commercial": "high-intent shortlist recommendations",
        }.get(intent, "smartphone buying insights")
        content = f"""
Hi,

I came across your content around \"{kw}\" and liked the way you cover buyer intent.

We recently published a guide built around {angle}:
{url}

It includes real-world trade-offs, supporting review pages, and internal comparison paths for users who are close to purchase.

If helpful, I can send a custom contribution or data-backed quote tailored to your audience.

Best,
"""
        filename = hashlib.md5(f"{cluster}:{kw}".encode()).hexdigest()[:10] + ".txt"
        with open(os.path.join(OUTREACH_DIR, filename), "w", encoding="utf-8") as f:
            f.write(content.strip())


def generate_internal_links(clusters, phones):
    links = []
    graph = build_link_graph(phones, [kw for kws in clusters.values() for kw in kws])
    for cluster, kws in clusters.items():
        if len(kws) < 2:
            continue
        pillar = kws[0]
        pillar_slug = pillar.replace(' ', '-')
        for kw in kws[1:8]:
            kw_slug = kw.replace(' ', '-')
            links.append({
                "from": f"/keyword/{kw_slug}.html",
                "to": f"/keyword/{pillar_slug}.html",
                "anchor": generate_anchor(pillar, is_pillar=True),
                "type": "support_to_pillar",
            })
            links.append({
                "from": f"/keyword/{pillar_slug}.html",
                "to": f"/keyword/{kw_slug}.html",
                "anchor": generate_anchor(kw),
                "type": "pillar_to_support",
            })
    save_json(INTERNAL_LINK_FILE, links)
    save_json_helper(LINK_GRAPH_FILE, graph)


def init_tracker():
    if not os.path.exists(TRACKER_FILE):
        save_json(TRACKER_FILE, {"outreach_sent": [], "links_acquired": [], "daily_velocity": []})


def simulate_link_velocity(targets):
    tracker = load_json(TRACKER_FILE, {})
    today_links = min(5, max(2, len(targets) // 60))
    tracker.setdefault("daily_velocity", []).append({"date": TODAY, "links": today_links})
    for target in targets[:today_links]:
        tracker.setdefault("links_acquired", []).append({
            "site": f"{target['domain_tier']}-{target['keyword'].split()[0]}.com",
            "anchor_type": random.choice(["exact", "partial", "branded"]),
            "target": target["target_page"],
            "authority_weight": target["authority_weight"],
            "date": TODAY,
        })
    save_json(TRACKER_FILE, tracker)


def run():
    print("[BACKLINK ENGINE - DOMINANCE MODE] Running...")
    keywords = prioritize_keywords(filter_keywords(load_keywords()))
    if not keywords:
        print("[ERROR] No valid keywords after filtering")
        return
    phones = load_phones()
    clusters = group_clusters(keywords)
    targets = generate_targets(clusters, phones)
    os.makedirs("data/backlinks", exist_ok=True)
    save_json(OUTPUT_TARGETS, targets)
    generate_outreach_posts(clusters)
    generate_internal_links(clusters, phones)
    init_tracker()
    simulate_link_velocity(targets)
    print(f"[BACKLINK ENGINE] Targets: {len(targets)} | Clusters: {len(clusters)}")


if __name__ == "__main__":
    run()
