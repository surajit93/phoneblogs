import json
import os
import re
import hashlib
from collections import defaultdict

SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "https://yoursite.com")
MONEY_INTENTS = ("best", "vs", "under", "review", "compare", "top")


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


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


def get_images(phone):
    images = phone.get("images")
    if isinstance(images, list) and images:
        return images
    hero = phone.get("hero_image")
    return [hero] if hero else []


def normalize_phone(phone):
    normalized = dict(phone)
    normalized.setdefault("slug", slugify(phone.get("name", "phone")))
    normalized.setdefault("brand", (phone.get("brand") or phone.get("name", "").split(" ")[0]).strip())
    normalized["price"] = get_price(phone)
    normalized.setdefault("specs", {})
    normalized["specs"].setdefault("ram", get_spec(phone, "ram"))
    normalized["specs"].setdefault("battery", get_spec(phone, "battery"))
    normalized["specs"].setdefault("camera", get_spec(phone, "camera"))
    normalized["specs"].setdefault("storage", get_spec(phone, "storage"))
    normalized["images"] = get_images(phone)
    normalized.setdefault("score", phone.get("overall_score") or phone.get("value_score") or 0)
    normalized.setdefault("alt_text", f"{normalized['name']} review image")
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
    brand_tokens = {phone["brand"].lower() for phone in phones if phone.get("brand")}
    matched_brand = next((brand for brand in brand_tokens if brand in kw), None)
    if matched_brand:
        ranked = [phone for phone in ranked if phone["brand"].lower() == matched_brand] or ranked

    if "under" in kw:
        prices = [int(token) for token in re.findall(r"\d+", kw)]
        if prices:
            cap = prices[0]
            ranked = [phone for phone in ranked if get_price(phone) and get_price(phone) <= cap] or ranked

    intent = keyword_intent(keyword)
    if "gaming" in kw:
        ranked.sort(key=lambda phone: (get_spec(phone, "ram"), phone.get("score", 0), get_price(phone)), reverse=True)
    elif "camera" in kw:
        ranked.sort(key=lambda phone: (get_spec(phone, "camera"), phone.get("score", 0), get_price(phone)), reverse=True)
    elif "battery" in kw:
        ranked.sort(key=lambda phone: (get_spec(phone, "battery"), phone.get("score", 0), get_price(phone)), reverse=True)
    elif intent == "budget":
        ranked.sort(key=lambda phone: ((phone.get("score") or 0) / max(get_price(phone), 1), phone.get("score", 0)), reverse=True)
    else:
        ranked.sort(key=lambda phone: (phone.get("score", 0), get_spec(phone, "ram"), get_spec(phone, "battery")), reverse=True)
    return ranked[:limit]


# >>> UPDATED START

def deterministic_pick(options, key):
    if not options:
        return ""
    digest = hashlib.sha256((key or "").encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(options)
    return options[idx]


def select_title_variant(slug: str, variants):
    return deterministic_pick(variants, slug)


def semantic_sections_template(context, keyword=""):
    label = keyword or context
    return {
        "who_should_buy": f"Buyers who prioritize {context} outcomes and predictable value from {label}.",
        "who_should_not_buy": f"Shoppers needing ultra-premium features or niche workflows outside {context}.",
        "hidden_tradeoffs": f"Better {context} usually trades off with price, camera tuning, or thermal comfort.",
        "real_world_usage": f"Daily behavior for {label} depends on app mix, connectivity, battery wear, and travel patterns.",
        "better_alternatives": f"Alternative models outperform {label} for at least one core decision axis.",
    }


def anti_thin_content_guard(blocks, required_sections=None, min_blocks=8):
    required_sections = required_sections or [
        "who_should_buy",
        "who_should_not_buy",
        "hidden_tradeoffs",
        "real_world_usage",
        "better_alternatives",
    ]
    if not isinstance(blocks, dict):
        return False
    non_empty = [k for k, v in blocks.items() if isinstance(v, str) and v.strip()]
    return len(non_empty) >= min_blocks and all(blocks.get(section, "").strip() for section in required_sections)


def generate_keyword_clusters(phones, min_keywords=5000, max_keywords=10000, min_clusters=100, max_clusters=300):
    brands = sorted({(p.get("brand") or "general").lower() for p in phones if p.get("brand")})
    if not brands:
        brands = ["general"]

    intents = ["best", "vs", "how", "why", "should i buy", "worth it"]
    features = ["battery", "camera", "gaming", "performance", "display"]
    audiences = ["students", "gamers", "creators"]
    scenarios = [
        "students", "travelers", "parents", "creators", "multitasking", "work", "streaming", "photography",
        "night photos", "long battery", "business", "everyday use", "gaming sessions", "social media",
    ]
    prices = [200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 1000, 1200]

    cluster_target = max(min_clusters, min(max_clusters, max(100, len(brands) * 10)))
    clusters = []
    keyword_count = 0

    cidx = 0
    while len(clusters) < cluster_target and keyword_count < max_keywords:
        brand = brands[cidx % len(brands)]
        feature = features[cidx % len(features)]
        intent = intents[cidx % len(intents)]
        scenario = scenarios[cidx % len(scenarios)]
        audience = audiences[cidx % len(audiences)]
        price = prices[cidx % len(prices)]

        pillar = f"{intent} {brand} {feature} phones for {audience} {scenario}".replace("  ", " ").strip()
        subclusters = []
        supporting = []

        for sidx in range(4):
            sub_name = f"{brand}-{feature}-{scenario}-{sidx+1}"
            sub_keywords = [
                f"best {brand} {feature} phone for {audience} under {price + (sidx*50)}",
                f"how to choose {brand} {feature} phone for {audience} under {price + (sidx*50)}",
                f"why {brand} {feature} phone may be worth it for {audience}",
                f"should i buy {brand} {feature} phone for {audience}",
                f"{brand} {feature} vs alternatives for {audience}",
                f"{brand} {feature} hidden trade offs for {audience}",
                f"{brand} {feature} real world usage for {audience}",
                f"{brand} {feature} comparison chain for {audience} under {price}",
            ]
            subclusters.append({"name": sub_name, "keywords": sub_keywords})
            supporting.extend(sub_keywords)

        deduped = []
        seen = set()
        for kw in [pillar] + supporting:
            cleaned = " ".join(kw.lower().split())
            if cleaned not in seen and len(cleaned.split()) >= 4:
                seen.add(cleaned)
                deduped.append(cleaned)

        cluster = {
            "cluster_id": f"cluster-{len(clusters)+1:03d}",
            "cluster_slug": slugify(f"{brand}-{feature}-{scenario}-{len(clusters)+1}"),
            "brand": brand,
            "feature": feature,
            "scenario": scenario,
            "audience": audience,
            "pillar_keyword": deduped[0],
            "supporting_keywords": deduped[1:],
            "subclusters": subclusters,
            "all_keywords": deduped,
        }
        keyword_count += len(deduped)
        clusters.append(cluster)
        cidx += 1

    all_keywords = [kw for cluster in clusters for kw in cluster["all_keywords"]]
    if len(all_keywords) < min_keywords:
        # Extend with deterministic compare long-tail set.
        phones_by_name = [p.get("name", "phone").lower() for p in phones[:120]]
        seed_cluster = clusters[0] if clusters else None
        for i in range(min_keywords - len(all_keywords)):
            a = phones_by_name[i % max(len(phones_by_name), 1)] if phones_by_name else "phone a"
            b = phones_by_name[(i + 7) % max(len(phones_by_name), 1)] if phones_by_name else "phone b"
            kw = f"{a} vs {b} which phone should i buy"
            if seed_cluster is not None:
                seed_cluster["supporting_keywords"].append(kw)
                seed_cluster["all_keywords"].append(kw)
            all_keywords.append(kw)

    if len(all_keywords) > max_keywords:
        overflow = len(all_keywords) - max_keywords
        for cluster in reversed(clusters):
            while overflow > 0 and cluster["supporting_keywords"]:
                cluster["supporting_keywords"].pop()
                cluster["all_keywords"].pop()
                overflow -= 1
            if overflow <= 0:
                break

    return {
        "generated_at": os.environ.get("BUILD_DATE") or "2026-03-24",
        "cluster_count": len(clusters),
        "keyword_count": sum(len(c["all_keywords"]) for c in clusters),
        "clusters": clusters,
    }


def build_keyword_page_map(cluster_data, phones):
    mapping = {
        "generated_at": os.environ.get("BUILD_DATE") or "2026-03-24",
        "keywords": {},
        "clusters": {},
    }

    for cluster in cluster_data.get("clusters", []):
        cluster_slug = cluster["cluster_slug"]
        cluster_url = f"/cluster/{cluster_slug}.html"
        topic_url = f"/topics/{cluster_slug}.html"
        mapping["clusters"][cluster_slug] = {
            "cluster_id": cluster["cluster_id"],
            "pillar_keyword": cluster["pillar_keyword"],
            "cluster_url": cluster_url,
            "topic_url": topic_url,
            "keyword_count": len(cluster.get("all_keywords", [])),
        }
        for kw in cluster.get("all_keywords", []):
            kw_slug = slugify(kw)
            devices = choose_keyword_devices(kw, phones, limit=6)
            comp_pairs = []
            for i in range(min(len(devices), 4)):
                for j in range(i + 1, min(len(devices), 4)):
                    comp_pairs.append(f"/compare/{devices[i]['slug']}-vs-{devices[j]['slug']}.html")
            mapping["keywords"][kw] = {
                "keyword_slug": kw_slug,
                "keyword_url": f"/keyword/{kw_slug}.html",
                "cluster_slug": cluster_slug,
                "cluster_url": cluster_url,
                "topic_url": topic_url,
                "supporting_phone_pages": [f"/phones/{d['slug']}.html" for d in devices],
                "supporting_compare_pages": comp_pairs[:6],
                "pillar_keyword": cluster["pillar_keyword"],
            }
    return mapping


def build_link_graph(phones, keywords, keyword_map=None):
    graph = {
        "phone_to_cluster": [],
        "phone_to_keywords": [],
        "keyword_to_phones": [],
        "keyword_to_cluster": [],
        "cluster_to_keywords": [],
        "comparison_to_reviews": [],
        "money_pages": [],
        "pillar_to_supporting": [],
        "supporting_to_pillar": [],
        "phone_to_keyword": [],
        "keyword_to_compare": [],
    }
    cluster_pages = defaultdict(list)
    for phone in phones:
        cluster = classify_phone(phone)
        phone_url = f"/phones/{phone['slug']}.html"
        cluster_url = f"/cluster/{cluster}.html"
        graph["phone_to_cluster"].append({"from": phone_url, "to": cluster_url, "anchor": f"best {cluster} phones"})
        cluster_pages[cluster].append(phone)
        graph["money_pages"].append(phone_url)

    for keyword in keywords:
        keyword_slug = slugify(keyword)
        keyword_url = f"/keyword/{keyword_slug}.html"
        intent = keyword_intent(keyword)
        chosen = choose_keyword_devices(keyword, phones, limit=6)

        if keyword_map and keyword in keyword_map.get("keywords", {}):
            m = keyword_map["keywords"][keyword]
            graph["keyword_to_cluster"].append({"from": keyword_url, "to": m["cluster_url"], "anchor": m["pillar_keyword"]})
            graph["cluster_to_keywords"].append({"from": m["cluster_url"], "to": keyword_url, "anchor": keyword})
            graph["keyword_to_compare"].extend({"from": keyword_url, "to": cp, "anchor": "compare alternatives"} for cp in m["supporting_compare_pages"])
            if keyword != m["pillar_keyword"]:
                pslug = slugify(m["pillar_keyword"])
                graph["supporting_to_pillar"].append({"from": keyword_url, "to": f"/keyword/{pslug}.html", "anchor": m["pillar_keyword"]})
                graph["pillar_to_supporting"].append({"from": f"/keyword/{pslug}.html", "to": keyword_url, "anchor": keyword})
        elif chosen:
            primary_cluster = classify_phone(chosen[0])
            graph["keyword_to_cluster"].append({"from": keyword_url, "to": f"/cluster/{primary_cluster}.html", "anchor": f"best {primary_cluster} phones"})
            graph["cluster_to_keywords"].append({"from": f"/cluster/{primary_cluster}.html", "to": keyword_url, "anchor": keyword})

        for phone in chosen:
            phone_url = f"/phones/{phone['slug']}.html"
            graph["keyword_to_phones"].append({"from": keyword_url, "to": phone_url, "anchor": f"{phone['name']} review"})
            graph["phone_to_keywords"].append({"from": phone_url, "to": keyword_url, "anchor": keyword})
            graph["phone_to_keyword"].append({"from": phone_url, "to": keyword_url, "anchor": f"best use case for {phone['name']}"})
        if intent in {"comparison", "commercial", "budget", "review"}:
            graph["money_pages"].append(keyword_url)

    graph["money_pages"] = sorted(set(graph["money_pages"]))
    return graph


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)

# >>> UPDATED END


def build_keyword_universe(phones, max_keywords=700):
    keywords = set()
    price_points = [200, 300, 400, 500, 700, 1000]
    feature_map = {
        "battery": "battery",
        "camera": "camera",
        "gaming": "gaming",
        "budget": "budget",
    }
    brands = sorted({phone["brand"] for phone in phones if phone.get("brand")})

    for brand in brands[:80]:
        lower = brand.lower()
        keywords.update({
            f"{lower} phone review",
            f"best {lower} phone",
            f"best {lower} phone under $500",
            f"{lower} phone comparison",
        })

    for price in price_points:
        keywords.update({
            f"best phones under ${price}",
            f"best gaming phone under ${price}",
            f"best camera phone under ${price}",
            f"best battery phone under ${price}",
        })

    cluster_examples = defaultdict(list)
    for phone in phones:
        cluster_examples[classify_phone(phone)].append(phone)

    for cluster, items in cluster_examples.items():
        items = sorted(items, key=lambda phone: (phone.get("score", 0), get_price(phone)), reverse=True)[:24]
        keywords.add(f"best {feature_map[cluster]} phones")
        for phone in items:
            name = phone["name"].lower()
            brand = phone["brand"].lower()
            keywords.update({
                f"{name} review",
                f"{name} vs {brand} alternatives",
                f"best {brand} {cluster} phone",
            })

    cleaned = []
    seen = set()
    for kw in keywords:
        normalized = slugify(kw)
        if not normalized or normalized in seen:
            continue
        if len(kw.split()) < 3:
            continue
        if not any(token in kw for token in MONEY_INTENTS):
            continue
        seen.add(normalized)
        cleaned.append(kw)
    cleaned.sort()
    return cleaned[:max_keywords]
