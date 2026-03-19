import requests
import cloudscraper
from bs4 import BeautifulSoup
import json
import os
import time
import re
from datetime import datetime

BASE = "https://www.gsmarena.com"
MAKERS_URL = f"{BASE}/makers.php3"

# -----------------------
# 🔥 FILE STRATEGY (NON-BREAKING)
# -----------------------
#DATA_FILE = os.path.abspath("data/phones/phones.json")

timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
#TIMESTAMP_FILE = os.path.abspath(f"data/phones/phones_{timestamp}.json")
TIMESTAMP_FILE = os.path.abspath(f"data/phones/phones_updated.json")

#print("WRITING TO:", DATA_FILE)
print("TIMESTAMP SNAPSHOT:", TIMESTAMP_FILE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PhoneBlogsBot/1.0)"
}

session = cloudscraper.create_scraper()
session.headers.update(HEADERS)

os.makedirs("data/phones", exist_ok=True)

# ensure file exists
if not os.path.exists(TIMESTAMP_FILE):
    with open(TIMESTAMP_FILE) as f:
        json.dump([], f)

# -----------------------
# BUFFER
# -----------------------
BUFFER = []
FLUSH_SIZE = 50
DEBUG = False

# -----------------------
# helpers
# -----------------------

def fetch(url, retries=3):
    for _ in range(retries):
        try:
            r = session.get(url, timeout=10)
            print("FETCH:", url)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser")
        except Exception:
            pass
        time.sleep(2)
    return None


def clean_text(val):
    if val is None:
        return None
    val = val.strip()
    if val == "" or val.lower() == "yes":
        return None
    return val


def extract_number(text):
    if not text:
        return None
    m = re.search(r"\d+\.?\d*", text)
    return float(m.group()) if m else None


def extract_battery(text):
    if not text:
        return None
    m = re.search(r"(\d{3,5})\s?mAh", text, re.I)
    return int(m.group(1)) if m else None


def extract_refresh(text):
    if not text:
        return None
    m = re.search(r"(\d{2,3})\s?Hz", text)
    return int(m.group(1)) if m else None


def extract_camera_mp(text):
    if not text:
        return None
    vals = re.findall(r"(\d+)\s*MP", text)
    return max(map(int, vals)) if vals else None


def parse_ram_storage(text):
    if not text:
        return None, None
    ram = re.findall(r"(\d+)\s*GB\s*RAM", text, re.I)
    storage = re.findall(r"(\d+)\s*GB", text)
    ram_gb = max(map(int, ram)) if ram else None
    storage_gb = max(map(int, storage)) if storage else None
    return ram_gb, storage_gb


def has_feature(text, keyword):
    if not text:
        return False
    return keyword.lower() in text.lower()


def extract_price(text):
    if not text:
        return None
    m = re.search(r"\$?\d{2,4}", text)
    return float(m.group().replace("$", "")) if m else None


def extract_wifi_version(text):
    if not text:
        return None
    t = text.lower()
    if "6e" in t:
        return "6e"
    if "6" in t:
        return "6"
    if "ac" in t:
        return "5"
    if "n" in t:
        return "4"
    return None


def extract_bluetooth_version(text):
    if not text:
        return None
    m = re.search(r"\d+(\.\d+)?", text)
    return m.group() if m else None


# -----------------------
# dataset
# -----------------------

def load_dataset():
    try:
        with open(TIMESTAMP_FILE) as f:
            return json.load(f)
    except Exception as e:
        print("⚠️ JSON CORRUPTED, RESETTING:", e)
        return []


def save_dataset(data):
    with open(TIMESTAMP_FILE, "w") as f:
        json.dump(data, f, indent=2)


def save_timestamp(data):
    with open(TIMESTAMP_FILE, "w") as f:
        json.dump(data, f, indent=2)


# -----------------------
# BUFFER append (UNCHANGED + SAFE ADD)
# -----------------------

def append_phone(phone, dataset):
    BUFFER.append(phone)

    if len(BUFFER) >= FLUSH_SIZE:

        tmp = TIMESTAMP_FILE + ".tmp"

        with open(tmp, "w") as f:
            json.dump(dataset, f, indent=2)

        os.replace(tmp, TIMESTAMP_FILE)

        print(f"FLUSHED {len(BUFFER)} → TOTAL: {len(dataset)}")

        os.system("git config user.name 'phoneblogs-bot'")
        os.system("git config user.email 'bot@users.noreply.github.com'")

        os.system("git pull --rebase origin main || true")

        os.system("git add data/phones/")
        os.system("git commit -m 'incremental update' || true")

        os.system("git push origin HEAD:main || git pull --rebase origin main && git push origin HEAD:main")

        BUFFER.clear()


# -----------------------
# brand discovery (UNCHANGED)
# -----------------------

def get_brands():
    soup = fetch(MAKERS_URL)

    brands = []

    for a in soup.select("#list-brands li a"):
        href = a.get("href")
        if href:
            brands.append(BASE + "/" + href)

    if not brands:
        for a in soup.select("a[href*='-phones-']"):
            href = a.get("href")
            if href:
                brand_url = BASE + "/" + href
                if brand_url not in brands:
                    brands.append(brand_url)

    return brands


# -----------------------
# phone list (UNCHANGED)
# -----------------------

def get_brand_phones(url):

    phones = []
    page_url = url

    while page_url:

        soup = fetch(page_url)
        if soup is None:
            break

        print("---- PAGE URL ----")
        print(page_url)

        print("---- PAGE TITLE ----")
        print(soup.title)

        print("---- FIRST 2000 HTML ----")
        print(soup.prettify()[:2000])

        all_links = soup.find_all("a")
        print("TOTAL A TAGS:", len(all_links))

        items = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"-\d+\.php$", href) and "-phones-" not in href:
                items.append(a)

        print("PHONE LINKS FOUND:", len(items))

        if not items:
            break

        for a in items:
            href = a.get("href")
            if href and "-phones-" not in href:
                phones.append(BASE + "/" + href)

        next_page = None

        for a in soup.find_all("a", href=True):
            if a.text and "Next" in a.text:
                next_page = BASE + "/" + a["href"]
                break

        page_url = next_page
        time.sleep(0.6)

    return phones


# -----------------------
# parse phone (ENHANCED, NOT REMOVED)
# -----------------------

def parse_phone(url):

    soup = fetch(url)
    if soup is None:
        return None

    name_tag = soup.select_one("h1")
    if not name_tag:
        return None

    name = name_tag.text.strip()

    specs = {}
    section_specs = {}
    current_section = None

    for row in soup.select("#specs-list tr"):

        header = row.select_one("th")
        if header:
            current_section = header.text.strip().lower()
            continue

        k = row.select_one(".ttl")
        v = row.select_one(".nfo")

        if k and v:
            key = k.text.strip().lower()
            val = v.text.strip()

            specs[key] = val

            if current_section:
                section_specs[f"{current_section}_{key}"] = val

    # fallback layering
    def pick(*vals):
        for v in vals:
            if v:
                return v
        return None

    ram_gb, storage_gb = parse_ram_storage(specs.get("internal"))

    charging = pick(section_specs.get("battery_charging"), specs.get("charging"))
    network = pick(section_specs.get("network_technology"), specs.get("technology"), specs.get("network"))
    wlan = specs.get("wlan")
    bluetooth = specs.get("bluetooth")

    main_cam = pick(
        section_specs.get("main camera_single"),
        section_specs.get("main camera_dual"),
        section_specs.get("main camera_triple"),
        section_specs.get("main camera_quad"),
        specs.get("camera")
    )

    selfie_cam = pick(
        section_specs.get("selfie camera_single"),
        specs.get("selfie camera")
    )

    display_type = pick(
        section_specs.get("display_type"),
        specs.get("type")
    )

    battery_text = pick(
        section_specs.get("battery_type"),
        specs.get("battery"),
        specs.get("type")
    )

    phone = {

        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "brand": name.split()[0],

        "announcement_date": clean_text(specs.get("announced")),
        "release_date": clean_text(specs.get("status")),
        "release_year": extract_number(specs.get("announced")),

        "price_usd": extract_price(specs.get("price")),

        "display_inches": extract_number(specs.get("size")),
        "display_resolution": clean_text(specs.get("resolution")),
        "display_type": clean_text(display_type),
        "refresh_hz": extract_refresh(display_type),

        "battery_mah": extract_battery(battery_text),
        "battery_type": clean_text(battery_text),
        "fast_charge_w": extract_number(charging) or extract_number(battery_text),
        "wireless_charging": has_feature(charging, "wireless"),
        "reverse_charging": has_feature(charging, "reverse"),

        "camera_mp": extract_camera_mp(main_cam),
        "camera_features": clean_text(section_specs.get("main camera_features") or specs.get("features")),
        "front_camera_mp": extract_camera_mp(selfie_cam),
        "camera_count": main_cam.count("MP") if main_cam else None,
        "telephoto_camera": has_feature(main_cam, "telephoto"),
        "ultrawide_camera": has_feature(main_cam, "ultrawide"),

        "chipset": clean_text(specs.get("chipset")),
        "gpu": clean_text(specs.get("gpu")),
        "cpu_score": None,
        "gpu_score": None,

        "ram_gb": ram_gb,
        "storage_gb": storage_gb,

        "os": clean_text(specs.get("os")),

        "weight_g": extract_number(specs.get("weight")),
        "ip_rating": clean_text(specs.get("protection")),
        "fingerprint": clean_text(specs.get("fingerprint")),

        "network": clean_text(network),
        "network_5g": has_feature(network, "5g"),

        "wifi": clean_text(wlan),
        "wifi_version": extract_wifi_version(wlan),

        "bluetooth": clean_text(bluetooth),
        "bluetooth_version": extract_bluetooth_version(bluetooth),

        "esim": has_feature(specs.get("sim"), "esim"),
        "usb_type": clean_text(specs.get("usb")),
        "nfc": has_feature(specs.get("sensors"), "nfc"),
        "sd_card": has_feature(specs.get("memory"), "microSD"),

        "audio_jack": has_feature(specs.get("loudspeaker"), "3.5mm"),
        "speaker_type": clean_text(specs.get("loudspeaker")),

        "url": url
    }

    return phone


# -----------------------
# pipeline (UNCHANGED)
# -----------------------

def run():

    dataset = load_dataset()

    known = {p.get("slug") for p in dataset if p.get("slug")}

    brands = get_brands()
    print(f"brands found: {len(brands)}")

    total_added = 0
    total_skipped = 0
    total_errors = 0

    for brand in brands:

        print(f"\n===== BRAND: {brand} =====")

        phones = get_brand_phones(brand)

        for url in phones:

            try:
                phone = parse_phone(url)

                if not phone:
                    total_skipped += 1
                    continue

                slug = phone.get("slug")

                if not slug or slug in known:
                    total_skipped += 1
                    continue

                dataset.append(phone)
                known.add(slug)
                total_added += 1

                append_phone(phone, dataset)

                print(f"✅ added: {phone['name']}")

                time.sleep(0.6)

            except Exception as e:
                total_errors += 1
                print(f"❌ error parsing {url}: {e}")

    # final flush
    if BUFFER:
        tmp = TIMESTAMP_FILE + ".tmp"

        with open(tmp, "w") as f:
            json.dump(dataset, f, indent=2)

        os.replace(tmp, TIMESTAMP_FILE)

        BUFFER.clear()

    # 🔥 timestamp snapshot (ADDITION ONLY)
    save_timestamp(dataset)

    print("\n===== RUN SUMMARY =====")
    print(f"Total phones stored: {len(dataset)}")
    print(f"Added: {total_added}")
    print(f"Skipped: {total_skipped}")
    print(f"Errors: {total_errors}")


if __name__ == "__main__":
    run()
