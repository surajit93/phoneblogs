import json
import os
import re
from typing import Any, Dict, List

INPUT_PATH = os.path.abspath("data/phones/phones.json")
OUTPUT_PATH = os.path.abspath("data/phones/phones_enriched.json")
IMAGES_BASE = os.path.abspath("data/images")


def safe_float(val):
    try:
        if val is None:
            return None
        return float(val)
    except:
        return None


def safe_int(val):
    try:
        if val is None:
            return None
        return int(float(val))
    except:
        return None


def clean_string(val):
    if not isinstance(val, str):
        return val
    return val.strip()


def extract_battery(text):
    if not text:
        return None
    match = re.search(r"(\d{3,5})\s?mAh", str(text), re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def fix_display_type(phone):
    dt = phone.get("display_type")
    if dt and "mah" in dt.lower():
        battery = extract_battery(dt)
        if battery and not phone.get("battery_mah"):
            phone["battery_mah"] = battery
        phone["display_type"] = None
    return phone


def normalize_phone(phone):
    for k, v in phone.items():
        if isinstance(v, str):
            phone[k] = clean_string(v)

    phone["battery_mah"] = safe_int(phone.get("battery_mah")) or extract_battery(
        json.dumps(phone)
    )

    phone["price_usd"] = safe_float(phone.get("price_usd"))
    phone["display_inches"] = safe_float(phone.get("display_inches"))
    phone["refresh_hz"] = safe_float(phone.get("refresh_hz"))
    phone["fast_charge_w"] = safe_float(phone.get("fast_charge_w"))
    phone["camera_mp"] = safe_float(phone.get("camera_mp"))
    phone["ram_gb"] = safe_float(phone.get("ram_gb"))
    phone["storage_gb"] = safe_float(phone.get("storage_gb"))
    phone["weight_g"] = safe_float(phone.get("weight_g"))

    return fix_display_type(phone)


def score_battery(battery, fast_charge):
    if not battery:
        return 3
    score = min(10, battery / 600)
    if fast_charge:
        score += min(2, fast_charge / 30)
    return round(min(10, score), 1)


def score_display(size, refresh):
    score = 5
    if size:
        score += min(2, size / 4)
    if refresh:
        if refresh >= 120:
            score += 3
        elif refresh >= 90:
            score += 2
    return round(min(10, score), 1)


def score_performance(chipset):
    if not chipset:
        return 3
    c = chipset.lower()
    if any(x in c for x in ["snapdragon 8", "apple a", "dimensity 9"]):
        return 9
    if any(x in c for x in ["snapdragon 7", "dimensity 8"]):
        return 7
    if any(x in c for x in ["snapdragon 6", "dimensity 7"]):
        return 6
    return 4


def score_camera(mp, features):
    score = 4
    if mp:
        score += min(4, mp / 20)
    if features:
        score += 1
    return round(min(10, score), 1)


def score_value(price, overall_spec_score):
    if not price or price == 0:
        return 5
    value = overall_spec_score / price * 100
    return round(min(10, value), 1)


def compute_scores(phone):
    b = score_battery(phone.get("battery_mah"), phone.get("fast_charge_w"))
    d = score_display(phone.get("display_inches"), phone.get("refresh_hz"))
    p = score_performance(phone.get("chipset"))
    c = score_camera(phone.get("camera_mp"), phone.get("camera_features"))

    spec_avg = (b + d + p + c) / 4
    v = score_value(phone.get("price_usd"), spec_avg)

    overall = round((b * 0.25 + d * 0.2 + p * 0.25 + c * 0.2 + v * 0.1), 1)

    return b, d, p, c, v, overall


def generate_tags(phone, scores):
    b, d, p, c, v, o = scores
    tags = []

    if p >= 7:
        tags.append("good_for_gaming")
    if c >= 7:
        tags.append("good_for_camera")
    if b >= 7:
        tags.append("good_for_battery")
    if v >= 7:
        tags.append("value_for_money")

    price = phone.get("price_usd") or 0
    if price >= 700:
        tags.append("flagship")
    elif price >= 300:
        tags.append("midrange")
    else:
        tags.append("budget")

    if phone.get("weight_g") and phone["weight_g"] > 200:
        tags.append("heavy_phone")
    if phone.get("display_inches") and phone["display_inches"] < 6:
        tags.append("compact_phone")

    if phone.get("network_5g"):
        tags.append("5g_phone")
    if phone.get("fast_charge_w") and phone["fast_charge_w"] >= 25:
        tags.append("fast_charging")
    if phone.get("wireless_charging"):
        tags.append("wireless_charging")

    return list(set(tags))


def category_flags(price):
    return {
        "is_flagship": price >= 700 if price else False,
        "is_midrange": 300 <= price < 700 if price else False,
        "is_budget": price < 300 if price else True,
    }


def load_image_cache():
    cache = {}
    if not os.path.exists(IMAGES_BASE):
        return cache

    for slug in os.listdir(IMAGES_BASE):
        path = os.path.join(IMAGES_BASE, slug, "images.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cache[slug] = json.load(f)
            except:
                pass
    return cache


def process_images(phone, cache):
    slug = phone.get("slug")
    data = cache.get(slug)

    if not data:
        return None, 0, False

    hero = data.get("hero")
    hero_path = (
        os.path.join("data/images", slug, hero) if hero else None
    )

    count = 0
    for arr in data.get("images", {}).values():
        count += len(arr)

    return hero_path, count, count > 0


def insights(phone, scores):
    b, d, p, c, v, o = scores

    if b >= 8:
        battery_hint = "lasts ~2 days"
    elif b >= 6:
        battery_hint = "lasts ~1.5 days"
    else:
        battery_hint = "lasts ~1 day"

    gaming = "high" if p >= 8 else "medium" if p >= 6 else "low"
    camera = "excellent" if c >= 8 else "good" if c >= 6 else "basic"

    return battery_hint, gaming, camera


def main():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        phones = json.load(f)

    image_cache = load_image_cache()

    enriched = []

    for phone in phones:
        phone = normalize_phone(phone)

        scores = compute_scores(phone)
        tags = generate_tags(phone, scores)
        flags = category_flags(phone.get("price_usd"))

        hero, count, has_images = process_images(phone, image_cache)
        battery_hint, gaming, camera = insights(phone, scores)

        phone.update(
            {
                "battery_score": scores[0],
                "display_score": scores[1],
                "performance_score": scores[2],
                "camera_score": scores[3],
                "value_score": scores[4],
                "overall_score": scores[5],
                "tags": tags,
                **flags,
                "hero_image": hero,
                "image_count": count,
                "has_images": has_images,
                "battery_life_hint": battery_hint,
                "gaming_level": gaming,
                "camera_level": camera,
            }
        )

        enriched.append(phone)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
