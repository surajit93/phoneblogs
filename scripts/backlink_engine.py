# >>> UPDATED START
#!/usr/bin/env python3

import datetime
import os

from seo_growth_utils import (
    build_keyword_page_map,
    generate_keyword_clusters,
    load_json,
    normalize_phones,
    save_json,
    slugify,
)

KEYWORDS_CLUSTER_FILE = "data/keyword_clusters.json"
KEYWORD_MAP_FILE = "data/keyword_page_map.json"
PHONES_FILE = "data/phones/phones_enriched.json"
LIVE_BACKLINKS_FILE = "data/backlinks/live_links.json"
PRIORITY_PAGES_FILE = "data/backlinks/priority_pages.json"
TARGETS_FILE = "data/backlinks/targets.json"
ANCHOR_LIBRARY_FILE = "data/backlinks/anchor_library.json"

TODAY = datetime.date.today().isoformat()


def load_phones():
    return normalize_phones(load_json(PHONES_FILE, []))


def ensure_keyword_system(phones):
    clusters = load_json(KEYWORDS_CLUSTER_FILE, {})
    if not clusters or not clusters.get("clusters"):
        clusters = generate_keyword_clusters(phones, min_keywords=2500, max_keywords=7000, min_clusters=100, max_clusters=220)
        save_json(KEYWORDS_CLUSTER_FILE, clusters)

    keyword_map = load_json(KEYWORD_MAP_FILE, {})
    if not keyword_map or not keyword_map.get("keywords"):
        keyword_map = build_keyword_page_map(clusters, phones)
        save_json(KEYWORD_MAP_FILE, keyword_map)

    return clusters, keyword_map


def load_live_backlinks_map():
    rows = load_json(LIVE_BACKLINKS_FILE, [])
    page_counts = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        if not url:
            continue
        page_counts[url] = page_counts.get(url, 0) + int(row.get("count", 1))
    return page_counts


def page_importance(url):
    if "/topics/" in url:
        return 6.0
    if "/informational/" in url:
        return 5.5
    if "/keyword/" in url:
        return 4.0
    if "/phones/" in url:
        return 3.0
    if "/compare/" in url:
        return 2.5
    return 1.0


def generate_anchor_variants(keyword):
    base = keyword.strip()
    return [
        base,
        f"{base} decision guide",
        f"{base} trade-offs",
        f"real-world {base}",
        f"{base} framework",
        f"{base} failure cases",
    ]


def roi_score(url, existing_backlinks):
    authority = page_importance(url)
    diminishing = max(0.2, 1 - (existing_backlinks * 0.08))
    return round(authority * 100 * diminishing, 2)


def compute_priority_pages(keyword_map, backlinks_map):
    priorities = []
    for kw, mapping in keyword_map.get("keywords", {}).items():
        targets = [
            mapping.get("topic_url"),
            mapping.get("cluster_url"),
            mapping.get("keyword_url"),
            *mapping.get("supporting_phone_pages", [])[:3],
            *mapping.get("supporting_compare_pages", [])[:2],
        ]
        anchors = generate_anchor_variants(kw)

        for url in targets:
            if not url:
                continue
            existing = backlinks_map.get(url, 0)
            score = roi_score(url, existing)
            priorities.append(
                {
                    "url": url,
                    "keyword": kw,
                    "priority_score": score,
                    "existing_backlinks": existing,
                    "roi_score": score,
                    "needs_backlinks": max(1, int(score // 25)),
                    "anchor_variants": anchors,
                }
            )

    dedup = {}
    for row in priorities:
        if row["url"] not in dedup or row["priority_score"] > dedup[row["url"]]["priority_score"]:
            dedup[row["url"]] = row

    ordered = sorted(dedup.values(), key=lambda item: item["priority_score"], reverse=True)
    return ordered[:3000]


def build_backlink_targets(priority_pages):
    targets = []
    for i, page in enumerate(priority_pages):
        anchor = page["anchor_variants"][i % len(page["anchor_variants"])]
        keyword = page["keyword"]
        target = {
            "id": f"target-{i+1:05d}",
            "keyword": keyword,
            "target_page": page["url"],
            "anchor": anchor,
            "anchor_variants": page["anchor_variants"],
            "roi_score": page["roi_score"],
            "opportunities": [
                f"intitle:{keyword} resources",
                f"{keyword} forum discussion",
                f"{keyword} expert roundup",
            ],
            "channel_mix": ["outreach", "reddit", "quora"],
        }
        targets.append(target)
    return targets


def run():
    os.makedirs("data/backlinks", exist_ok=True)

    phones = load_phones()
    _, keyword_map = ensure_keyword_system(phones)
    backlinks_map = load_live_backlinks_map()

    priority_pages = compute_priority_pages(keyword_map, backlinks_map)
    targets = build_backlink_targets(priority_pages)

    save_json(
        PRIORITY_PAGES_FILE,
        {
            "generated_at": TODAY,
            "count": len(priority_pages),
            "pages_needing_backlinks": priority_pages,
        },
    )
    save_json(TARGETS_FILE, targets)
    save_json(
        ANCHOR_LIBRARY_FILE,
        {
            "generated_at": TODAY,
            "anchors": {slugify(t["keyword"]): t["anchor_variants"] for t in targets[:2000]},
        },
    )

    print(f"[BACKLINK ENGINE] priority_pages={len(priority_pages)} targets={len(targets)}")


if __name__ == "__main__":
    run()
# >>> UPDATED END
