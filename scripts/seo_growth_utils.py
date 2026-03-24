import json
import os
import re
from collections import defaultdict
from itertools import combinations

SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "https://yoursite.com")

MONEY_INTENTS = ("best", "vs", "under", "review", "compare", "top")
US_MARKERS = ("usa", "us", "america", "unlocked", "prepaid", "verizon", "t-mobile", "at&t")

PRICE_POINTS = [100, 150, 200, 250, 300, 350, 400, 500, 600, 700, 800, 1000, 1200]
USE_CASES = [
    "gaming", "camera", "battery life", "college", "students", "seniors",
    "travel", "work", "video", "low light", "streaming", "multitasking",
    "content creators", "vlogging", "kids", "business", "everyday use",
]
FEATURE_QUERIES = [
    "oled display", "amoled display", "120hz display", "144hz display", "wireless charging",
    "fast charging", "5g", "esim", "stereo speakers", "long battery life", "telephoto camera",
    "ultrawide camera", "nfc", "small phone", "large screen", "stock android",
]
COMPARISON_MODIFIERS = [
    "which is better", "camera test", "battery life", "gaming", "value for money",
    "for students", "for everyday use", "for photos", "for video", "in usa",
]
CHIPSET_TIERS = {
    "flagship": ["snapdragon 8", "dimensity 9300", "tensor g4", "apple a17", "apple a18", "exynos 2400"],
    "upper_mid": ["snapdragon 7+", "snapdragon 7 gen", "dimensity 8300", "tensor g3", "exynos 1480"],
    "midrange": ["snapdragon 6", "snapdragon 7s", "dimensity 7050", "dimensity 7300", "helio g99"],
    "entry": ["helio g", "unisoc", "snapdragon 4", "snapdragon 680", "dimensity 6100"],
}
BRAND_POSITIONING = {
    "apple": "premium ecosystem pick",
    "samsung": "mainstream premium all-rounder",
    "google": "camera-first clean Android option",
    "pixel": "camera-first clean Android option",
    "oneplus": "performance-led value flagship",
    "xiaomi": "spec-heavy value play",
    "redmi": "budget performance specialist",
    "motorola": "clean-software value pick",
    "nothing": "design-led Android alternative",
}


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
        "chipset": ["chipset"],
        "display_type": ["display_type"],
        "os": ["os"],
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
    normalized["specs"].setdefault("refresh", get_spec(phone, "refresh"))
    normalized["specs"].setdefault("chipset", get_spec(phone, "chipset"))
    normalized["specs"].setdefault("display_type", get_spec(phone, "display_type"))
    normalized["specs"].setdefault("os", get_spec(phone, "os"))
    normalized["images"] = get_images(phone)
    normalized.setdefault("score", phone.get("overall_score") or phone.get("value_score") or 0)
    normalized.setdefault("alt_text", f"{normalized['name']} review image")
    normalized.setdefault("entity_profile", enrich_phone_entities(normalized))
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
    if get_spec(phone, "ram") >= 8 or "gaming" in str(phone.get("gaming_level", "")).lower():
        return "gaming"
    return "budget"


def chipset_tier(phone):
    chipset = str(get_spec(phone, "chipset") or phone.get("chipset") or "").lower()
    for tier, markers in CHIPSET_TIERS.items():
        if any(marker in chipset for marker in markers):
            return tier
    score = phone.get("performance_score") or phone.get("overall_score") or 0
    if score >= 8:
        return "flagship"
    if score >= 6.5:
        return "upper_mid"
    if score >= 4.5:
        return "midrange"
    return "entry"


def display_summary(phone):
    display_type = str(get_spec(phone, "display_type") or phone.get("display_type") or "").strip() or "display"
    refresh = int(float(get_spec(phone, "refresh") or 0) or 0)
    refresh_text = f"{refresh}Hz" if refresh else "standard refresh"
    return f"{display_type} at {refresh_text}"


def os_signal(phone):
    brand = (phone.get("brand") or "").lower()
    os_name = str(get_spec(phone, "os") or phone.get("os") or "Android").strip()
    if "apple" in brand or "iphone" in phone.get("name", "").lower():
        return "iOS ecosystem"
    if "pixel" in phone.get("name", "").lower() or brand == "google":
        return f"{os_name} with Google-first features"
    if brand == "samsung":
        return f"{os_name} with Galaxy ecosystem extras"
    return f"{os_name} ecosystem"


def brand_positioning(phone):
    brand = (phone.get("brand") or "").lower()
    return BRAND_POSITIONING.get(brand, "mainstream value option")


def enrich_phone_entities(phone):
    return {
        "chipset_tier": chipset_tier(phone),
        "display_summary": display_summary(phone),
        "os_signal": os_signal(phone),
        "brand_positioning": brand_positioning(phone),
    }


def keyword_modifiers_for_phone(phone):
    entities = enrich_phone_entities(phone)
    modifiers = {
        entities["chipset_tier"],
        entities["display_summary"].lower(),
        entities["os_signal"].lower(),
        entities["brand_positioning"],
    }
    if get_spec(phone, "battery") >= 5000:
        modifiers.add("long battery life")
    if get_spec(phone, "camera") >= 50:
        modifiers.add("camera")
    if int(float(get_spec(phone, "refresh") or 0)) >= 120:
        modifiers.add("120hz")
    return sorted(modifiers)


def phone_rank_score(phone, keyword=""):
    price = max(get_price(phone), 1)
    score = float(phone.get("overall_score") or phone.get("value_score") or phone.get("score") or 0)
    perf = float(phone.get("performance_score") or 0)
    cam = float(phone.get("camera_score") or 0)
    battery = float(phone.get("battery_score") or 0)
    refresh = float(get_spec(phone, "refresh") or 0)
    kw = (keyword or "").lower()
    total = score * 4 + perf * 2 + cam * 1.5 + battery * 1.5 + min(refresh / 30, 5)
    if "gaming" in kw:
        total += perf * 3 + float(get_spec(phone, "ram") or 0) * 1.2 + refresh / 20
    if "camera" in kw or "photo" in kw or "video" in kw:
        total += cam * 4 + float(get_spec(phone, "camera") or 0) / 10
    if "battery" in kw or "long battery" in kw:
        total += battery * 4 + float(get_spec(phone, "battery") or 0) / 1000
    if any(token in kw for token in ("budget", "under", "cheap", "value")):
        total += (score * 12) / price * 100
    if "small" in kw and float(get_spec(phone, "display") or 0) <= 6.3:
        total += 4
    if "usa" in kw or "unlocked" in kw:
        total += 2 if phone.get("network_5g") else 0.5
    return total


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

    if "small phone" in kw or "compact" in kw:
        ranked = [phone for phone in ranked if float(get_spec(phone, "display") or 0) <= 6.4] or ranked
    if "large screen" in kw:
        ranked = [phone for phone in ranked if float(get_spec(phone, "display") or 0) >= 6.7] or ranked
    if "wireless charging" in kw:
        ranked = [phone for phone in ranked if phone.get("wireless_charging")] or ranked
    if "esim" in kw:
        ranked = [phone for phone in ranked if phone.get("esim")] or ranked
    if "5g" in kw:
        ranked = [phone for phone in ranked if phone.get("network_5g")] or ranked

    ranked.sort(key=lambda phone: (phone_rank_score(phone, keyword), phone.get("score", 0), get_spec(phone, "ram"), get_spec(phone, "battery")), reverse=True)
    return ranked[:limit]


def build_keyword_universe(phones, max_keywords=700):
    keywords = set()
    brands = sorted({phone["brand"] for phone in phones if phone.get("brand")})[:120]
    years = ["2026", "2025"]
    normalized = normalize_phones(phones)

    for price in PRICE_POINTS:
        for use_case in USE_CASES:
            keywords.update({
                f"best phone under ${price} for {use_case}",
                f"best phones under ${price} for {use_case} usa",
                f"best {use_case} phone under ${price}",
            })
        for feature in FEATURE_QUERIES:
            keywords.update({
                f"best phone under ${price} with {feature}",
                f"best {feature} phone under ${price} usa",
            })

    for brand in brands:
        lower = brand.lower()
        for year in years:
            keywords.update({
                f"best {lower} phone {year}",
                f"{lower} phone review {year}",
                f"best {lower} phone under $500 usa",
                f"best {lower} camera phone",
                f"best {lower} battery phone",
                f"best {lower} gaming phone",
                f"{lower} phone comparison",
                f"{lower} vs samsung phone",
                f"{lower} vs iphone phone",
            })

    top_phones = sorted(normalized, key=lambda phone: phone_rank_score(phone), reverse=True)[:220]
    for phone in top_phones:
        name = phone["name"].lower()
        brand = phone["brand"].lower()
        entities = enrich_phone_entities(phone)
        keywords.update({
            f"{name} review",
            f"{name} review usa",
            f"{name} camera test",
            f"{name} battery life review",
            f"{name} for gaming",
            f"{name} worth buying",
            f"{name} vs {brand} alternatives",
            f"{name} vs iphone",
            f"{name} vs samsung galaxy",
            f"best alternative to {name}",
            f"best {entities['chipset_tier']} phone under ${int(get_price(phone) or 500)}",
            f"best {entities['display_summary'].lower()} phone",
        })
        for modifier in ["gaming", "camera", "battery life", "students", "travel", "usa"]:
            keywords.add(f"{name} {modifier}")

    by_cluster = defaultdict(list)
    for phone in normalized:
        by_cluster[classify_phone(phone)].append(phone)

    for cluster, items in by_cluster.items():
        sorted_items = sorted(items, key=lambda phone: phone_rank_score(phone, cluster), reverse=True)[:40]
        keywords.add(f"best {cluster} phones")
        keywords.add(f"top {cluster} phones usa")
        for phone in sorted_items:
            name = phone["name"].lower()
            keywords.update({
                f"best {cluster} phone like {name}",
                f"{name} vs best {cluster} phones",
            })

    compare_candidates = sorted(normalized, key=lambda phone: phone_rank_score(phone), reverse=True)[:36]
    compare_count = 0
    for p1, p2 in combinations(compare_candidates, 2):
        if p1["brand"].lower() == p2["brand"].lower() and abs(get_price(p1) - get_price(p2)) > 300:
            continue
        pair = f"{p1['name'].lower()} vs {p2['name'].lower()}"
        keywords.add(pair)
        for modifier in COMPARISON_MODIFIERS[:4]:
            keywords.add(f"{pair} {modifier}")
        compare_count += 1
        if compare_count >= max_keywords // 2 or len(keywords) > max_keywords * 4:
            break

    cleaned = []
    seen = set()
    for kw in keywords:
        kw = re.sub(r"\s+", " ", kw.strip().lower())
        normalized_kw = slugify(kw)
        if not normalized_kw or normalized_kw in seen:
            continue
        if len(kw.split()) < 3:
            continue
        if not any(token in kw for token in MONEY_INTENTS) and not any(marker in kw for marker in US_MARKERS + tuple(USE_CASES)):
            continue
        seen.add(normalized_kw)
        cleaned.append(kw)
    cleaned.sort(key=lambda kw: score_keyword_opportunity(kw, normalized), reverse=True)
    return cleaned[:max_keywords]


def score_keyword_opportunity(keyword, phones):
    kw = (keyword or "").lower()
    intent = keyword_intent(kw)
    score = 0
    score += 40 if intent == "comparison" else 0
    score += 35 if intent == "commercial" else 0
    score += 32 if intent == "budget" else 0
    score += 28 if intent == "review" else 10
    score += 12 if "usa" in kw or "unlocked" in kw else 0
    score += 10 if any(token in kw for token in ("gaming", "camera", "battery", "low light", "students")) else 0
    score += 8 if "under $" in kw else 0
    score += 10 if "vs" in kw else 0
    score += 6 if any(token in kw for token in FEATURE_QUERIES) else 0
    selected = choose_keyword_devices(kw, phones, limit=3) if phones else []
    if selected:
        score += int(sum(phone_rank_score(phone, kw) for phone in selected) / max(len(selected), 1) / 10)
    return score


def build_title_variants(keyword, phones=None, limit=4):
    kw = (keyword or "").strip()
    title = kw.title()
    intent = keyword_intent(kw)
    top_phone = phones[0]["name"] if phones else None
    variants = []
    if intent == "comparison":
        variants.extend([
            f"{title} ({'2026'}) — Which Phone Wins?",
            f"{title} — Camera, Battery & Value Compared",
            f"{title} — Best Choice for US Buyers in 2026",
        ])
    elif intent == "budget":
        variants.extend([
            f"{title} — Best Value Picks for 2026",
            f"{title} — Top Budget Phones Ranked",
            f"{title} — Cheap Phones Worth Buying in the US",
        ])
    elif intent == "review":
        variants.extend([
            f"{title} — Real-World Review & Buyer Verdict",
            f"{title} — Pros, Cons & Better Alternatives",
            f"{title} — What to Know Before You Buy",
        ])
    else:
        variants.extend([
            f"{title} — Best Phones Ranked for 2026",
            f"{title} — Top Picks, Trade-Offs & Buying Advice",
            f"{title} — Best Options for US Buyers",
        ])
    if top_phone:
        variants.append(f"{title} — Is {top_phone} the Best Pick?")
    deduped = []
    seen = set()
    for item in variants:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped[:limit]


def anchor_variants(keyword, target_type="keyword", phones=None):
    kw = (keyword or "").strip()
    anchors = [kw, f"best picks for {kw}", f"our {kw} guide"]
    if target_type == "pillar":
        anchors.extend([f"top {kw} rankings", f"best {kw} in the US"])
    if phones:
        anchors.extend([f"{phones[0]['name']} review", f"compare {phones[0]['name']} alternatives"])
    return [anchor for anchor in anchors if anchor]


def build_link_graph(phones, keywords):
    graph = {
        "phone_to_cluster": [],
        "phone_to_keywords": [],
        "keyword_to_phones": [],
        "keyword_to_cluster": [],
        "cluster_to_keywords": [],
        "comparison_to_reviews": [],
        "money_pages": [],
        "keyword_to_pillar": [],
        "pillar_to_support": [],
        "phone_to_compare": [],
    }
    normalized_phones = normalize_phones(phones)
    cluster_pages = defaultdict(list)
    for phone in normalized_phones:
        cluster = classify_phone(phone)
        phone_url = f"/phones/{phone['slug']}.html"
        cluster_url = f"/cluster/{cluster}.html"
        graph["phone_to_cluster"].append({"from": phone_url, "to": cluster_url, "anchor": f"best {cluster} phones"})
        cluster_pages[cluster].append(phone)
        graph["money_pages"].append(phone_url)

    pillar_by_cluster = {}
    scored_keywords = sorted(set(keywords), key=lambda kw: score_keyword_opportunity(kw, normalized_phones), reverse=True)
    for keyword in scored_keywords:
        keyword_slug = slugify(keyword)
        keyword_url = f"/keyword/{keyword_slug}.html"
        intent = keyword_intent(keyword)
        chosen = choose_keyword_devices(keyword, normalized_phones, limit=5)
        cluster = classify_phone(chosen[0]) if chosen else "budget"
        phones_for_anchor = chosen[:1]
        graph["keyword_to_cluster"].append({"from": keyword_url, "to": f"/cluster/{cluster}.html", "anchor": f"best {cluster} phones"})
        graph["cluster_to_keywords"].append({"from": f"/cluster/{cluster}.html", "to": keyword_url, "anchor": anchor_variants(keyword, phones=phones_for_anchor)[0]})
        pillar_key = (cluster, intent)
        if pillar_key not in pillar_by_cluster:
            pillar_by_cluster[pillar_key] = keyword_url
        else:
            graph["keyword_to_pillar"].append({"from": keyword_url, "to": pillar_by_cluster[pillar_key], "anchor": anchor_variants(keyword, "pillar", phones_for_anchor)[1]})
            graph["pillar_to_support"].append({"from": pillar_by_cluster[pillar_key], "to": keyword_url, "anchor": anchor_variants(keyword, phones=phones_for_anchor)[2]})
        for phone in chosen:
            phone_url = f"/phones/{phone['slug']}.html"
            graph["keyword_to_phones"].append({"from": keyword_url, "to": phone_url, "anchor": f"{phone['name']} review"})
            graph["phone_to_keywords"].append({"from": phone_url, "to": keyword_url, "anchor": anchor_variants(keyword, phones=[phone])[0]})
        if len(chosen) >= 2:
            lead, challenger = chosen[0], chosen[1]
            compare_slug = f"{lead['slug']}-vs-{challenger['slug']}"
            graph["comparison_to_reviews"].append({
                "from": f"/compare/{compare_slug}.html",
                "to": f"/phones/{lead['slug']}.html",
                "anchor": f"full {lead['name']} review",
            })
            graph["comparison_to_reviews"].append({
                "from": f"/compare/{compare_slug}.html",
                "to": f"/phones/{challenger['slug']}.html",
                "anchor": f"full {challenger['name']} review",
            })
            graph["phone_to_compare"].append({
                "from": f"/phones/{lead['slug']}.html",
                "to": f"/compare/{compare_slug}.html",
                "anchor": f"{lead['name']} vs {challenger['name']}",
            })
        if intent in {"comparison", "commercial", "budget", "review"}:
            graph["money_pages"].append(keyword_url)

    graph["money_pages"] = sorted(set(graph["money_pages"]))
    return graph


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
