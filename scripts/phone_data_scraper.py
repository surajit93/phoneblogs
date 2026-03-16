import requests
import cloudscraper
from bs4 import BeautifulSoup
import json
import os
import time
import re

BASE = "https://www.gsmarena.com"
MAKERS_URL = f"{BASE}/makers.php3"

DATA_FILE = "data/phones/phones.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PhoneBlogsBot/1.0)"
}

session = cloudscraper.create_scraper()
session.headers.update(HEADERS)

os.makedirs("data/phones", exist_ok=True)


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



def extract_number(text):

    if not text:
        return None

    m = re.search(r"\d+\.?\d*", text)

    return float(m.group()) if m else None


def parse_ram_storage(text):

    if not text:
        return None, None

    ram = re.search(r"(\d+)\s*GB\s*RAM", text)
    storage = re.search(r"(\d+)\s*GB", text)

    ram_gb = int(ram.group(1)) if ram else None
    storage_gb = int(storage.group(1)) if storage else None

    return ram_gb, storage_gb


def has_feature(text, keyword):

    if not text:
        return False

    return keyword.lower() in text.lower()


def extract_price(text):

    if not text:
        return None

    m = re.search(r"\$?\d{2,4}", text)

    if m:
        return float(m.group().replace("$", ""))

    return None


def extract_wifi_version(text):

    if not text:
        return None

    m = re.search(r"Wi[- ]?Fi\s*(\d)", text, re.I)

    return m.group(1) if m else None


def extract_bluetooth_version(text):

    if not text:
        return None

    m = re.search(r"(\d\.\d)", text)

    return m.group(1) if m else None


def load_dataset():

    if not os.path.exists(DATA_FILE):
        return []

    with open(DATA_FILE) as f:
        return json.load(f)


def save_dataset(data):

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# incremental writer (added earlier)

def append_phone(phone):

    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump([], f)

    with open(DATA_FILE, "r+") as f:

        try:
            data = json.load(f)
        except:
            data = []

        data.append(phone)

        f.seek(0)
        json.dump(data, f, indent=2)
        f.truncate()


# -----------------------
# brand discovery
# -----------------------

def get_brands():

    soup = fetch(MAKERS_URL)

    brands = []

    for a in soup.select("#list-brands li a"):

        href = a.get("href")

        if not href:
            continue

        brand_url = BASE + "/" + href

        brands.append(brand_url)

    if not brands:

        for a in soup.select("a[href*='-phones-']"):

            href = a.get("href")

            if not href:
                continue

            brand_url = BASE + "/" + href

            if brand_url not in brands:
                brands.append(brand_url)

    return brands


# -----------------------
# phone list per brand
# -----------------------

def get_brand_phones(url):

    phones = []

    page = 1

    while True:

        if page == 1:
            page_url = url
        else:
        
            # original pagination (kept for compatibility)
            page_url = url.replace(".php", f"-{page}.php")
        
            # GSMArena correct pagination
            parts = url.split("/")[-1].replace(".php", "").split("-")
        
            if len(parts) >= 3:
                brand_id = parts[-1]
                brand_slug = "-".join(parts[:-1])
        
                page_url = f"{BASE}/{brand_slug}-f-{page}-{brand_id}.php"


        soup = fetch(page_url)
        
        if soup is None:
            break


        items = soup.select(".makers ul li a")

        # fallback if mobile DOM breaks selector
        if not items:
            items = soup.select(".makers a")

        if not items:
            break

        for a in items:

            href = a.get("href")
            print("PHONE LINK:", href)
            print("candidate:", href)

            if not href:
                continue

            if "-phones-" in href:
                continue

            phones.append(BASE + "/" + href)

        page += 1

        time.sleep(0.6)

    return phones


# -----------------------
# parse phone page
# -----------------------

def parse_phone(url):

    soup = fetch(url)

    name_tag = soup.select_one("h1")

    if not name_tag:
        return None

    name = name_tag.text.strip()

    specs = {}

    for row in soup.select("#specs-list tr"):

        k = row.select_one(".ttl")
        v = row.select_one(".nfo")

        if not k or not v:
            continue

        key = k.text.strip().lower()
        val = v.text.strip()

        specs[key] = val


    ram_gb, storage_gb = parse_ram_storage(specs.get("internal"))

    charging = specs.get("charging")
    protection = specs.get("protection")
    network = specs.get("network")
    wlan = specs.get("wlan")
    bluetooth = specs.get("bluetooth")
    sim = specs.get("sim")
    usb = specs.get("usb")
    sensors = specs.get("sensors")
    camera_text = specs.get("camera")
    sound = specs.get("loudspeaker")

    phone = {

        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "brand": name.split()[0],

        "announcement_date": specs.get("announced"),
        "release_date": specs.get("status"),
        "release_year": extract_number(specs.get("announced")),

        "price_usd": extract_price(specs.get("price")),

        "display_inches": extract_number(specs.get("size")),
        "display_resolution": specs.get("resolution"),
        "display_type": specs.get("type"),
        "refresh_hz": extract_number(specs.get("refresh rate")),

        "battery_mah": extract_number(specs.get("battery")),
        "battery_type": specs.get("battery"),
        "fast_charge_w": extract_number(charging),
        "wireless_charging": has_feature(charging, "wireless"),
        "reverse_charging": has_feature(charging, "reverse"),

        "camera_mp": extract_number(camera_text),
        "camera_features": specs.get("features"),
        "front_camera_mp": extract_number(specs.get("selfie camera")),
        "camera_count": camera_text.count("MP") if camera_text else None,
        "telephoto_camera": has_feature(camera_text, "telephoto"),
        "ultrawide_camera": has_feature(camera_text, "ultrawide"),

        "chipset": specs.get("chipset"),
        "gpu": specs.get("gpu"),
        "cpu_score": None,
        "gpu_score": None,

        "ram_gb": ram_gb,
        "storage_gb": storage_gb,

        "os": specs.get("os"),

        "weight_g": extract_number(specs.get("weight")),
        "ip_rating": protection,
        "fingerprint": specs.get("fingerprint"),

        "network": network,
        "network_5g": has_feature(network, "5g"),
        "wifi": wlan,
        "wifi_version": extract_wifi_version(wlan),
        "bluetooth": bluetooth,
        "bluetooth_version": extract_bluetooth_version(bluetooth),
        "esim": has_feature(sim, "esim"),
        "usb_type": usb,
        "nfc": has_feature(sensors, "nfc"),
        "sd_card": has_feature(specs.get("memory"), "microSD"),

        "audio_jack": has_feature(sound, "3.5mm"),
        "speaker_type": sound,

        "url": url
    }

    return phone


# -----------------------
# pipeline
# -----------------------

def run():

    dataset = load_dataset()

    known = {p["slug"] for p in dataset}

    brands = get_brands()

    print("brands:", len(brands))

    for brand in brands:

        phones = get_brand_phones(brand)

        for url in phones:

            try:

                phone = parse_phone(url)

                if not phone:
                    continue

                if phone["slug"] in known:
                    continue

                dataset.append(phone)
                known.add(phone["slug"])

                append_phone(phone)

                print("added:", phone["name"])

                time.sleep(0.6)

            except Exception as e:
                print("error:", e)

    save_dataset(dataset)

    print("phones stored:", len(dataset))


if __name__ == "__main__":
    run()
