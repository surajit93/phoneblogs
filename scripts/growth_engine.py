import json
import os
import re
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


def build_link_graph(phones, keywords):
    graph = {
        "phone_to_cluster": [],
        "phone_to_keywords": [],
        "keyword_to_phones": [],
        "keyword_to_cluster": [],
        "cluster_to_keywords": [],
        "comparison_to_reviews": [],
        "money_pages": [],
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
        chosen = choose_keyword_devices(keyword, phones, limit=5)
        if chosen:
            primary_cluster = classify_phone(chosen[0])
            graph["keyword_to_cluster"].append({"from": keyword_url, "to": f"/cluster/{primary_cluster}.html", "anchor": f"best {primary_cluster} phones"})
            graph["cluster_to_keywords"].append({"from": f"/cluster/{primary_cluster}.html", "to": keyword_url, "anchor": keyword})
        for phone in chosen:
            phone_url = f"/phones/{phone['slug']}.html"
            graph["keyword_to_phones"].append({"from": keyword_url, "to": phone_url, "anchor": f"{phone['name']} review"})
            graph["phone_to_keywords"].append({"from": phone_url, "to": keyword_url, "anchor": keyword})
        if intent in {"comparison", "commercial", "budget", "review"}:
            graph["money_pages"].append(keyword_url)

    graph["money_pages"] = sorted(set(graph["money_pages"]))
    return graph


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
