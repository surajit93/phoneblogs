import json
import os
import re

INPUT_FILE = "data/phones/phones.json"
OUTPUT_FILE = "data/phones/phones_enriched.json"
IMAGE_BASE = "data/images"


def safe_float(val):
    try:
        return float(val)
    except:
        return None


def safe_int(val):
    try:
        return int(val)
    except:
        return None


def clean_string(val):
    if not val:
        return None
    return str(val).strip()


def extract_battery_any(text):
    if not text:
        return None
    m = re.search(r"(\d{3,5})\s?mAh", str(text), re.I)
    return int(m.group(1)) if m else None


def fix_display_type(display_type, battery_type):
    if display_type and "mah" in display_type.lower():
        return None
    return display_type


def normalize_numeric(phone):
    phone["price_usd"] = safe_float(phone.get("price_usd"))
    phone["display_inches"] = safe_float(phone.get("display_inches"))
    phone["refresh_hz"] = safe_int(phone.get("refresh_hz"))
    phone["battery_mah"] = safe_int(phone.get("battery_mah"))
    phone["fast_charge_w"] = safe_float(phone.get("fast_charge_w"))
    phone["camera_mp"] = safe_float(phone.get("camera_mp"))
    phone["front_camera_mp"] = safe_float(phone.get("front_camera_mp"))
    phone["ram_gb"] = safe_int(phone.get("ram_gb"))
    phone["storage_gb"] = safe_int(phone.get("storage_gb"))
    phone["weight_g"] = safe_float(phone.get("weight_g"))


def clean_phone(phone):
    phone["display_type"] = fix_display_type(
        phone.get("display_type"), phone.get("battery_type")
    )

    if not phone.get("battery_mah"):
        for field in ["battery_type", "display_type", "camera_features"]:
            val = extract_battery_any(phone.get(field))
            if val:
                phone["battery_mah"] = val
                break

    for k, v in phone.items():
        if isinstance(v, str):
            phone[k] = clean_string(v)

    normalize_numeric(phone)


def battery_score(p):
    b = p.get("battery_mah") or 0
    c = p.get("fast_charge_w") or 0

    score = 0
    if b >= 7000:
        score += 6
    elif b >= 5000:
        score += 4
    elif b >= 4000:
        score += 3
    else:
        score += 2

    if c >= 80:
        score += 4
    elif c >= 30:
        score += 2

    return min(score, 10)


def display_score(p):
    hz = p.get("refresh_hz") or 60
    size = p.get("display_inches") or 6
    res = p.get("display_resolution") or ""

    score = 0

    if hz >= 120:
        score += 4
    elif hz >= 90:
        score += 3
    else:
        score += 2

    if size >= 6.5:
        score += 2

    if "1440" in res or "2k" in res.lower():
        score += 4
    elif "1080" in res:
        score += 3
    else:
        score += 2

    return min(score, 10)


def performance_score(p):
    chipset = (p.get("chipset") or "").lower()

    if any(x in chipset for x in ["snapdragon 8", "apple a", "dimensity 9"]):
        return 9
    if any(x in chipset for x in ["snapdragon 7", "dimensity 8"]):
        return 7
    if any(x in chipset for x in ["snapdragon 6", "dimensity 7"]):
        return 5
    return 3


def camera_score(p):
    mp = p.get("camera_mp") or 0
    features = (p.get("camera_features") or "").lower()

    score = 0

    if mp >= 100:
        score += 6
    elif mp >= 50:
        score += 5
    elif mp >= 12:
        score += 3
    else:
        score += 2

    if "ois" in features:
        score += 2
    if "hdr" in features:
        score += 1

    return min(score, 10)


def value_score(p):
    price = p.get("price_usd") or 1000
    perf = performance_score(p)
    cam = camera_score(p)

    if price <= 200:
        return min(10, perf + cam)
    elif price <= 500:
        return min(10, perf + cam - 1)
    else:
        return min(10, perf + cam - 2)


def overall_score(p):
    return round(
        (
            battery_score(p)
            + display_score(p)
            + performance_score(p)
            + camera_score(p)
            + value_score(p)
        )
        / 5,
        1,
    )


def category_flags(p):
    price = p.get("price_usd") or 0

    if price >= 700:
        return True, False, False
    if price >= 300:
        return False, True, False
    return False, False, True


def generate_tags(p):
    tags = []

    if performance_score(p) >= 7:
        tags.append("good_for_gaming")
    if camera_score(p) >= 7:
        tags.append("good_for_camera")
    if battery_score(p) >= 7:
        tags.append("good_for_battery")
    if value_score(p) >= 7:
        tags.append("value_for_money")

    if p.get("network_5g"):
        tags.append("5g_phone")
    if p.get("wireless_charging"):
        tags.append("wireless_charging")
    if (p.get("fast_charge_w") or 0) >= 30:
        tags.append("fast_charging")

    if (p.get("weight_g") or 0) > 200:
        tags.append("heavy_phone")
    if (p.get("display_inches") or 0) <= 6.1:
        tags.append("compact_phone")

    f, m, b = category_flags(p)
    if f:
        tags.append("flagship")
    if m:
        tags.append("midrange")
    if b:
        tags.append("budget")

    return tags


def load_image_cache():
    cache = {}
    if not os.path.exists(IMAGE_BASE):
        return cache

    for slug in os.listdir(IMAGE_BASE):
        path = os.path.join(IMAGE_BASE, slug, "images.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    cache[slug] = json.load(f)
            except:
                pass
    return cache


def integrate_images(p, cache):
    slug = p.get("slug")
    data = cache.get(slug)

    if not data:
        p["hero_image"] = None
        p["image_count"] = 0
        p["has_images"] = False
        return

    hero = data.get("hero")
    images = data.get("images", {})

    count = sum(len(v) for v in images.values())

    p["hero_image"] = f"{IMAGE_BASE}/{slug}/{hero}" if hero else None
    p["image_count"] = count
    p["has_images"] = count > 0


def insights(p):
    b = p.get("battery_mah") or 0

    if b >= 7000:
        p["battery_life_hint"] = "lasts ~2 days"
    elif b >= 5000:
        p["battery_life_hint"] = "lasts ~1.5 days"
    else:
        p["battery_life_hint"] = "lasts ~1 day"

    perf = performance_score(p)
    if perf >= 8:
        p["gaming_level"] = "high"
    elif perf >= 5:
        p["gaming_level"] = "medium"
    else:
        p["gaming_level"] = "low"

    cam = camera_score(p)
    if cam >= 8:
        p["camera_level"] = "excellent"
    elif cam >= 5:
        p["camera_level"] = "good"
    else:
        p["camera_level"] = "basic"


def run():
    with open(INPUT_FILE) as f:
        phones = json.load(f)

    image_cache = load_image_cache()

    enriched = []

    for p in phones:
        try:
            clean_phone(p)

            p["battery_score"] = battery_score(p)
            p["display_score"] = display_score(p)
            p["performance_score"] = performance_score(p)
            p["camera_score"] = camera_score(p)
            p["value_score"] = value_score(p)
            p["overall_score"] = overall_score(p)

            f, m, b = category_flags(p)
            p["is_flagship"] = f
            p["is_midrange"] = m
            p["is_budget"] = b

            p["tags"] = generate_tags(p)

            integrate_images(p, image_cache)

            insights(p)

            enriched.append(p)

        except:
            continue

    with open(OUTPUT_FILE, "w") as f:
        json.dump(enriched, f, indent=2)


if __name__ == "__main__":
    run()
