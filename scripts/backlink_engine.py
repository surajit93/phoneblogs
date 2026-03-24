import json
import os
import datetime
from seo_growth_utils import (
    normalize_phones,
    build_keyword_page_map,
    generate_keyword_clusters,
    save_json as save_json_helper,
)

# >>> UPDATED START
KEYWORDS_CLUSTER_FILE = "data/keyword_clusters.json"
KEYWORD_MAP_FILE = "data/keyword_page_map.json"
PHONES_FILE = "data/phones/phones_enriched.json"
LIVE_BACKLINKS_FILE = "data/backlinks/live_links.json"
PRIORITY_PAGES_FILE = "data/backlinks/priority_pages.json"
OUTPUT_TARGETS = "data/backlinks/targets.json"

TODAY = datetime.date.today().isoformat()


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_phones():
    return normalize_phones(load_json(PHONES_FILE, []))


def ensure_keyword_system(phones):
    clusters = load_json(KEYWORDS_CLUSTER_FILE, {})
    if not clusters or not clusters.get("clusters"):
        clusters = generate_keyword_clusters(phones, min_keywords=5000, max_keywords=10000, min_clusters=100, max_clusters=300)
        save_json_helper(KEYWORDS_CLUSTER_FILE, clusters)

    keyword_map = load_json(KEYWORD_MAP_FILE, {})
    if not keyword_map or not keyword_map.get("keywords"):
        keyword_map = build_keyword_page_map(clusters, phones)
        save_json_helper(KEYWORD_MAP_FILE, keyword_map)
    return clusters, keyword_map


def load_live_backlinks_map():
    rows = load_json(LIVE_BACKLINKS_FILE, [])
    page_counts = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = row.get("url")
            if not url:
                continue
            page_counts[url] = int(row.get("count", 1))
    return page_counts


def page_importance(url):
    if "/topics/" in url or "/cluster/" in url:
        return 5.0
    if "/keyword/" in url:
        return 3.5
    if "/phones/" in url:
        return 3.0
    if "/compare/" in url:
        return 2.0
    return 1.0


def compute_priority_pages(keyword_map, backlinks_map):
    priorities = []
    for kw, mapping in keyword_map.get("keywords", {}).items():
        target_pages = [
            mapping.get("topic_url"),
            mapping.get("cluster_url"),
            mapping.get("keyword_url"),
            *mapping.get("supporting_phone_pages", [])[:3],
            *mapping.get("supporting_compare_pages", [])[:2],
        ]
        for url in target_pages:
            if not url:
                continue
            existing = backlinks_map.get(url, 0)
            score = round(page_importance(url) * 100 - (existing * 7), 2)
            if score <= 0:
                continue
            priorities.append({
                "url": url,
                "keyword": kw,
                "priority_score": score,
                "existing_backlinks": existing,
                "needs_backlinks": max(0, int(score // 12)),
            })

    deduped = {}
    for item in priorities:
        url = item["url"]
        if url not in deduped or item["priority_score"] > deduped[url]["priority_score"]:
            deduped[url] = item

    ordered = sorted(deduped.values(), key=lambda x: x["priority_score"], reverse=True)
    return ordered[:2000]


def build_backlink_targets(keyword_map):
    targets = []
    for kw, mapping in keyword_map.get("keywords", {}).items():
        targets.append({
            "keyword": kw,
            "target_page": mapping["keyword_url"],
            "cluster_page": mapping["cluster_url"],
            "topic_page": mapping["topic_url"],
            "supporting_reviews": mapping["supporting_phone_pages"][:3],
            "supporting_comparisons": mapping["supporting_compare_pages"][:3],
            "target_type": "pillar" if kw == mapping.get("pillar_keyword") else "support",
        })
    return targets


def run():
    print("[BACKLINK ENGINE - REAL AUTHORITY MODE] Running...")
    phones = load_phones()
    _, keyword_map = ensure_keyword_system(phones)

    backlinks_map = load_live_backlinks_map()
    priority_pages = {
        "generated_at": TODAY,
        "total_pages": len(keyword_map.get("keywords", {})),
        "pages_needing_backlinks": compute_priority_pages(keyword_map, backlinks_map),
    }

    targets = build_backlink_targets(keyword_map)

    os.makedirs("data/backlinks", exist_ok=True)
    save_json_helper(PRIORITY_PAGES_FILE, priority_pages)
    save_json_helper(OUTPUT_TARGETS, targets)

    print(f"[BACKLINK ENGINE] priority_pages={len(priority_pages['pages_needing_backlinks'])} targets={len(targets)}")


if __name__ == "__main__":
    run()
# >>> UPDATED END
