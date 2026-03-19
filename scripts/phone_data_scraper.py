
import requests
import cloudscraper
from bs4 import BeautifulSoup
import json
import os
import time
import re

BASE = "https://www.gsmarena.com"
MAKERS_URL = f"{BASE}/makers.php3"

DATA_FILE = os.path.abspath("data/phones/phones.json")
print("WRITING TO:", DATA_FILE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PhoneBlogsBot/1.0)"
}

session = cloudscraper.create_scraper()
session.headers.update(HEADERS)

os.makedirs("data/phones", exist_ok=True)

# ensure file exists
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)

# -----------------------
# 🔥 NEW BUFFER SYSTEM
# -----------------------
BUFFER = []
FLUSH_SIZE = 20
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


# -----------------------
# 🔥 FIXED append with BUFFER
# -----------------------
"""
def append_phone(phone, dataset):

    BUFFER.append(phone)

    if len(BUFFER) >= FLUSH_SIZE:

        tmp = DATA_FILE + ".tmp"

        with open(tmp, "w") as f:
            json.dump(dataset, f, indent=2)

        os.replace(tmp, DATA_FILE)

        print(f"FLUSHED {len(BUFFER)} → TOTAL: {len(dataset)}")

        BUFFER.clear()
"""


def append_phone(phone, dataset):

    BUFFER.append(phone)

    if len(BUFFER) >= FLUSH_SIZE:

        tmp = DATA_FILE + ".tmp"

        with open(tmp, "w") as f:
            json.dump(dataset, f, indent=2)

        os.replace(tmp, DATA_FILE)

        print(f"FLUSHED {len(BUFFER)} → TOTAL: {len(dataset)}")

        # 🔥 SAFE incremental push
		os.system("git config user.name 'phoneblogs-bot'")
		os.system("git config user.email 'bot@users.noreply.github.com'")
		
		# 🔥 CRITICAL STEP
		os.system("git pull --rebase origin main || true")
		
		os.system("git add data/phones/phones.json")
		os.system("git commit -m 'incremental update' || true")
		
		# retry push (handles race conditions)
		os.system("git push origin HEAD:main || git pull --rebase origin main && git push origin HEAD:main")

        BUFFER.clear()

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

            print("PHONE LINK:", href)

            if not href:
                continue

            if "-phones-" in href:
                continue

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
# parse phone page
# -----------------------

def parse_phone(url):

    soup = fetch(url)

    if soup is None:
        return None

    name_tag = soup.select_one("h1")

    if not name_tag:
        return None

    name = name_tag.text.strip()

    if DEBUG:
        print("\n==============================")
        print("PARSING:", name)
        print("==============================")

    specs = {}

    for row in soup.select("#specs-list tr"):

        k = row.select_one(".ttl")
        v = row.select_one(".nfo")

        if not k or not v:
            continue

        key = k.text.strip().lower()
        val = v.text.strip()

        specs[key] = val

    section_specs = {}
    current_section = None

    for row in soup.select("#specs-list tr"):
        header = row.select_one("th")
        if header:
            current_section = header.text.strip().lower()
            continue

        k = row.select_one(".ttl")
        v = row.select_one(".nfo")

        if k and v and current_section:
            key = f"{current_section}_{k.text.strip().lower()}"
            section_specs[key] = v.text.strip()

    if DEBUG:
        print("\n--- ALL SPEC KEYS ---")
        print(sorted(specs.keys()))

        print("\n--- IMPORTANT RAW VALUES ---")
        print("battery:", specs.get("battery"))
        print("type:", specs.get("type"))
        print("camera:", specs.get("camera"))
        print("selfie camera:", specs.get("selfie camera"))
        print("network:", specs.get("network"))
        print("charging:", specs.get("charging"))

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

    raw_type = specs.get("type")

    display_type = section_specs.get("display_type") or (
        raw_type if raw_type and "mah" not in raw_type.lower() else specs.get("type")
    )

    battery_text = section_specs.get("battery_type") or (
        raw_type if raw_type and "mah" in raw_type.lower() else specs.get("battery")
    )

    network = section_specs.get("network_technology") or specs.get("technology") or network

    main_cam = (
        section_specs.get("main camera_single")
        or section_specs.get("main camera_dual")
        or section_specs.get("main camera_triple")
        or section_specs.get("main camera_quad")
        or specs.get("single")
        or specs.get("dual")
        or specs.get("triple")
        or specs.get("quad")
        or camera_text
    )

    selfie_cam = (
        section_specs.get("selfie camera_single")
        or specs.get("selfie camera")
    )

    charging = section_specs.get("battery_charging") or charging

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
        "display_type": display_type,
        "refresh_hz": extract_refresh(display_type),

        "battery_mah": extract_battery(battery_text),
        "battery_type": battery_text,
        "fast_charge_w": extract_number(charging),
        "wireless_charging": has_feature(charging, "wireless"),
        "reverse_charging": has_feature(charging, "reverse"),

        "camera_mp": extract_number(main_cam),
        "camera_features": section_specs.get("main camera_features") or specs.get("features"),
        "front_camera_mp": extract_number(selfie_cam),
        "camera_count": main_cam.count("MP") if main_cam else None,
        "telephoto_camera": has_feature(main_cam, "telephoto"),
        "ultrawide_camera": has_feature(main_cam, "ultrawide"),

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

    if DEBUG:
        print("\n--- FINAL OUTPUT SNAPSHOT ---")
        print(json.dumps(phone, indent=2))

    return phone


# -----------------------
# pipeline
# -----------------------

def run():

    dataset = load_dataset()

    # safe slug extraction (avoid KeyError)
    known = {p.get("slug") for p in dataset if p.get("slug")}

    brands = get_brands()

    print("brands:", len(brands))

    for brand in brands:

        phones = get_brand_phones(brand)

        for url in phones:

            try:

                phone = parse_phone(url)

                if not phone:
                    continue

                slug = phone.get("slug")

                if not slug or slug in known:
                    continue

                dataset.append(phone)
                known.add(slug)

                append_phone(phone, dataset)

                print("added:", phone["name"])

                time.sleep(0.6)

            except Exception as e:
                print("error:", e)

    # 🔥 FINAL FLUSH
    if BUFFER:
        tmp = DATA_FILE + ".tmp"

        with open(tmp, "w") as f:
            json.dump(dataset, f, indent=2)

        os.replace(tmp, DATA_FILE)

        print(f"FINAL FLUSH → TOTAL: {len(dataset)}")

        # 🔥 VERIFY WRITE
        print("---- VERIFY WRITE ----")
        try:
            with open(DATA_FILE, "r") as f:
                content = f.read()
                print("FILE LENGTH:", len(content))
                print("FILE SAMPLE:", content[:200])
        except Exception as e:
            print("VERIFY FAILED:", e)

    print("phones stored:", len(dataset))


if __name__ == "__main__":
    run()
	
