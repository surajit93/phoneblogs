# >>> UPDATED START
#!/usr/bin/env python3

import datetime
import hashlib
import json
import os
import random
import re
from collections import defaultdict
from typing import Dict, List

SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "https://yoursite.com")
CONTENT_MEMORY_FILE = "data/content_memory.json"


REQUIRED_DEPTH_SECTIONS = [
    "Who should NOT buy",
    "Hidden trade-offs",
    "Real-world usage",
    "Better alternatives",
]


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def deterministic_int(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def deterministic_choice(options: List[str], seed: str) -> str:
    if not options:
        return ""
    return options[deterministic_int(seed, len(options))]


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def get_price(phone):
    return phone.get("price") or phone.get("price_usd") or 0


def get_spec(phone, key):
    specs = phone.get("specs") or {}
    aliases = {
        "ram": ["ram", "ram_gb"],
        "battery": ["battery", "battery_mah"],
        "camera": ["camera", "camera_mp"],
        "storage": ["storage", "storage_gb"],
        "cpu": ["cpu", "cpu_score"],
        "gpu": ["gpu", "gpu_score"],
        "display": ["display", "display_inches"],
        "refresh": ["refresh", "refresh_hz"],
    }
    for candidate in aliases.get(key, [key]):
        if candidate in specs and specs[candidate] not in (None, ""):
            return specs[candidate]
        if candidate in phone and phone[candidate] not in (None, ""):
            return phone[candidate]
    return 0


def normalize_phone(phone):
    normalized = dict(phone)
    normalized.setdefault("name", "Unknown Phone")
    normalized.setdefault("slug", slugify(normalized["name"]))
    normalized.setdefault("brand", (phone.get("brand") or normalized["name"].split(" ")[0]).strip())
    normalized["price"] = get_price(phone)
    normalized.setdefault("specs", {})
    normalized["specs"].setdefault("ram", get_spec(phone, "ram"))
    normalized["specs"].setdefault("battery", get_spec(phone, "battery"))
    normalized["specs"].setdefault("camera", get_spec(phone, "camera"))
    normalized["specs"].setdefault("storage", get_spec(phone, "storage"))
    normalized.setdefault("score", phone.get("overall_score") or phone.get("value_score") or 0)
    return normalized


def normalize_phones(phones):
    return [normalize_phone(phone) for phone in phones if isinstance(phone, dict) and phone.get("name")]


def keyword_intent(keyword):
    kw = (keyword or "").lower()
    if "vs" in kw or "compare" in kw:
        return "comparison"
    if "under" in kw or "budget" in kw or "cheap" in kw:
        return "budget"
    if "review" in kw:
        return "review"
    if any(token in kw for token in ("best", "top")):
        return "commercial"
    return "informational"


def classify_phone(phone):
    if get_spec(phone, "battery") >= 5000:
        return "battery"
    if get_spec(phone, "camera") >= 64:
        return "camera"
    if get_spec(phone, "ram") >= 8:
        return "gaming"
    return "budget"


def choose_keyword_devices(keyword, phones, limit=8):
    kw = (keyword or "").lower()
    ranked = list(phones)
    if "gaming" in kw:
        ranked.sort(key=lambda p: (get_spec(p, "ram"), p.get("score", 0)), reverse=True)
    elif "camera" in kw:
        ranked.sort(key=lambda p: (get_spec(p, "camera"), p.get("score", 0)), reverse=True)
    elif "battery" in kw:
        ranked.sort(key=lambda p: (get_spec(p, "battery"), p.get("score", 0)), reverse=True)
    elif "under" in kw:
        nums = re.findall(r"\d+", kw)
        if nums:
            cap = int(nums[0])
            ranked = [p for p in ranked if get_price(p) and get_price(p) <= cap] or ranked
        ranked.sort(key=lambda p: (p.get("score", 0) / max(get_price(p), 1)), reverse=True)
    else:
        ranked.sort(key=lambda p: p.get("score", 0), reverse=True)
    return ranked[:limit]


def build_keyword_universe(phones, max_keywords=2500):
    brands = sorted({p.get("brand", "").lower() for p in phones if p.get("brand")})
    intents = ["best", "top", "review", "under", "vs", "compare"]
    features = ["battery", "camera", "gaming", "display", "charging", "value"]
    prices = [200, 250, 300, 400, 500, 700, 1000, 1200]

    keywords = []
    for brand in brands:
        for feature in features:
            for intent in intents:
                if intent == "under":
                    for price in prices:
                        keywords.append(f"{intent} {brand} {feature} phones under ${price}")
                elif intent in {"vs", "compare"}:
                    keywords.append(f"{brand} {feature} phones {intent} alternatives")
                else:
                    keywords.append(f"{intent} {brand} {feature} phones")

    generic = [
        "is 8gb ram enough for gaming",
        "why 5000mah battery drains fast",
        "does camera megapixel matter",
        "how much ram is enough for multitasking",
        "is fast charging bad for battery health",
    ]
    keywords.extend(generic)

    deduped = []
    seen = set()
    for kw in keywords:
        k = " ".join(kw.split()).lower()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(k)
        if len(deduped) >= max_keywords:
            break
    return deduped


def generate_keyword_clusters(phones, min_keywords=2500, max_keywords=6000, min_clusters=100, max_clusters=220):
    keywords = build_keyword_universe(phones, max_keywords=max_keywords)
    while len(keywords) < min_keywords:
        i = len(keywords)
        keywords.append(f"best phone performance decision guide {i}")

    cluster_count = max(min_clusters, min(max_clusters, len(keywords) // 25))
    clusters = []
    for i in range(cluster_count):
        start = i * 25
        slice_keywords = keywords[start:start + 25]
        if not slice_keywords:
            slice_keywords = [f"phone buying guide cluster {i + 1}"]
        pillar = slice_keywords[0]
        clusters.append(
            {
                "cluster_id": f"cluster-{i + 1:03d}",
                "cluster_slug": slugify(pillar),
                "pillar_keyword": pillar,
                "all_keywords": slice_keywords,
                "supporting_keywords": slice_keywords[1:],
            }
        )

    return {
        "generated_at": datetime.date.today().isoformat(),
        "cluster_count": len(clusters),
        "keyword_count": len(keywords),
        "clusters": clusters,
    }


def build_keyword_page_map(cluster_data, phones):
    mapping = {"generated_at": datetime.date.today().isoformat(), "keywords": {}}
    phone_slugs = [p["slug"] for p in phones][:24]
    for cluster in cluster_data.get("clusters", []):
        for kw in cluster.get("all_keywords", []):
            s = slugify(kw)
            mapping["keywords"][kw] = {
                "pillar_keyword": cluster.get("pillar_keyword"),
                "keyword_url": f"{SITE_DOMAIN}/keyword/{s}.html",
                "cluster_url": f"{SITE_DOMAIN}/cluster/{cluster['cluster_slug']}.html",
                "topic_url": f"{SITE_DOMAIN}/topics/{slugify(cluster.get('pillar_keyword', kw))}.html",
                "supporting_phone_pages": [f"{SITE_DOMAIN}/phones/{x}.html" for x in phone_slugs[:8]],
                "supporting_compare_pages": [f"{SITE_DOMAIN}/compare/{phone_slugs[i]}-vs-{phone_slugs[i+1]}.html" for i in range(0, min(8, len(phone_slugs)-1), 2)],
            }
    return mapping


class UniquenessMemory:
    def __init__(self, path=CONTENT_MEMORY_FILE):
        self.path = path
        self.payload = load_json(path, {"phrases": {}, "structures": {}})

    def phrase_penalty(self, phrase: str) -> int:
        return int(self.payload.get("phrases", {}).get(phrase.lower(), 0))

    def select_fresh(self, options: List[str], seed: str) -> str:
        if not options:
            return ""
        ranked = sorted(options, key=lambda item: (self.phrase_penalty(item), deterministic_int(seed + item, 1000)))
        return ranked[0]

    def remember_phrase(self, phrase: str):
        if not phrase:
            return
        phrases = self.payload.setdefault("phrases", {})
        key = phrase.lower().strip()
        phrases[key] = int(phrases.get(key, 0)) + 1

    def remember_structure(self, page_slug: str, structure: List[str]):
        self.payload.setdefault("structures", {})[page_slug] = structure

    def save(self):
        save_json(self.path, self.payload)


def section_order(seed: str, sections: List[str]) -> List[str]:
    shuffled = sections[:]
    rnd = random.Random(deterministic_int(seed, 10_000_000))
    rnd.shuffle(shuffled)
    return shuffled


def make_ctr_title_variants(query: str, context: str = "") -> List[str]:
    q = query.strip().rstrip("?")
    c = context.strip()
    return [
        f"{q}: The Brutal Truth Most Buyers Learn Too Late",
        f"Before You Choose {c or 'a Phone'}: {q} (What Changes the Decision)",
        f"{q}? 7 Real-World Tests That Flip the Answer",
        f"Stop Guessing: {q} With Hidden Trade-Offs Exposed",
        f"{q} — The No-Hype Framework Smart Buyers Use in 2026",
    ]


def select_title_variant(slug: str, variants: List[str]) -> str:
    return deterministic_choice(variants, f"title::{slug}")


def generate_informational_topics(min_pages=500, max_pages=1500):
    stems = [
        ("is", "ram enough for"),
        ("why", "battery drains fast on"),
        ("does", "camera megapixel matter on"),
        ("how", "to reduce thermal throttling on"),
        ("is", "fast charging bad for"),
        ("why", "phone lag after update"),
        ("does", "refresh rate impact battery"),
        ("how", "much storage is enough for"),
        ("is", "oled worth it for"),
    ]
    audiences = ["gaming", "students", "travel", "parents", "creators", "business", "daily use"]
    devices = ["budget phones", "mid-range phones", "flagship phones", "android phones", "iphone users"]

    topics = []
    target = max(min_pages, min(max_pages, 900))
    idx = 0
    while len(topics) < target:
        a, b = stems[idx % len(stems)]
        audience = audiences[idx % len(audiences)]
        device = devices[(idx // len(audiences)) % len(devices)]
        query = f"{a} {8 + (idx % 9)}gb {b} {audience} {device}".replace("  ", " ")
        topics.append(
            {
                "id": f"info-{idx + 1:04d}",
                "query": query,
                "slug": slugify(query),
                "audience": audience,
                "device_segment": device,
                "priority": 1000 - idx,
            }
        )
        idx += 1
    return topics


def build_link_graph(phones, keywords, comparisons, topics, informational):
    graph = defaultdict(list)

    def add_edge(src, dst, anchor):
        if not src or not dst or src == dst:
            return
        graph[src].append({"target": dst, "anchor": anchor})

    strong_topics = [f"/topics/{slugify(t)}.html" for t in topics[:120]]
    keyword_pages = [f"/keyword/{slugify(k)}.html" for k in keywords[:2600]]
    phone_pages = [f"/phones/{p['slug']}.html" for p in phones[:1000]]
    compare_pages = [f"/compare/{slugify(a)}-vs-{slugify(b)}.html" for a, b in comparisons[:700]]
    info_pages = [f"/informational/{slugify(q['query'])}.html" for q in informational[:1500]]

    # informational -> keyword -> phone -> compare
    for i, src in enumerate(info_pages):
        for dst in keyword_pages[i % len(keyword_pages): (i % len(keyword_pages)) + 3]:
            add_edge(src, dst, "buying decision factors")

    for i, src in enumerate(keyword_pages):
        for dst in phone_pages[i % len(phone_pages): (i % len(phone_pages)) + 3]:
            add_edge(src, dst, "recommended phone options")

    for i, src in enumerate(phone_pages):
        for dst in compare_pages[i % len(compare_pages): (i % len(compare_pages)) + 2]:
            add_edge(src, dst, "compare before buying")

    weak_tail = keyword_pages[-500:] + compare_pages[-300:]
    donors = strong_topics + info_pages[:300]
    for i, weak in enumerate(weak_tail):
        src = donors[i % len(donors)]
        add_edge(src, weak, "deeper analysis")

    return dict(graph)


def enforce_depth_or_raise(content: str, min_words=1200):
    words = len(re.findall(r"\b\w+\b", content))
    if words < min_words:
        raise ValueError(f"Thin content rejected: {words} words")


# >>> UPDATED END
