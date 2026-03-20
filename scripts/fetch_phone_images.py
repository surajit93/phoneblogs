import os
import json
import time
import requests
import hashlib
import re
import random
import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ✅ NEW: cloudscraper fallback
import cloudscraper

BASE = "https://www.gsmarena.com"

# 🔥 NEW: absolute base dir (ADDED - no removal)
BASE_DIR = os.getcwd()
print("[BASE DIR]", BASE_DIR)

DATA_FILE = "data/phones/phones_enriched.json"
IMAGE_ROOT = "data/images"

# 🔥 NEW: absolute path override (ADDED - no removal)
DATA_FILE = os.path.join(BASE_DIR, DATA_FILE)
IMAGE_ROOT = os.path.join(BASE_DIR, IMAGE_ROOT)
INDEX_FILE = os.path.join(BASE_DIR, "data/image_index.json")

print("[DATA FILE]", DATA_FILE)
print("[IMAGE ROOT]", IMAGE_ROOT)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

# ✅ CHANGED: use cloudscraper as PRIMARY
session = cloudscraper.create_scraper()
session.headers.update(HEADERS)

# ✅ fallback session
scraper = cloudscraper.create_scraper()
scraper.headers.update(HEADERS)

MAX_PER_TYPE = 5


# -----------------------
# INIT
# -----------------------
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "data/phones"), exist_ok=True)
os.makedirs(IMAGE_ROOT, exist_ok=True)

print("[DIR CHECK] data exists:", os.path.exists(os.path.join(BASE_DIR, "data")))
print("[DIR CHECK] images exists:", os.path.exists(IMAGE_ROOT))

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)

# -----------------------
# IMAGE INDEX INIT
# -----------------------
if not os.path.exists(INDEX_FILE):
    print("[INIT] Creating image index from existing files...")

    image_index = {}

    if os.path.exists(IMAGE_ROOT):
        for slug in os.listdir(IMAGE_ROOT):
            folder = os.path.join(IMAGE_ROOT, slug)
            if not os.path.isdir(folder):
                continue

            files = [f for f in os.listdir(folder) if f.endswith(".jpg")]

            image_index[slug] = {
                "downloaded": len(files),
                "files": files,
                "hashes": [],  # will be populated after first successful run
                "needs_hashing": True
            }

    with open(INDEX_FILE, "w") as f:
        json.dump(image_index, f, indent=2)
else:
    with open(INDEX_FILE) as f:
        image_index = json.load(f)

print("[INDEX LOADED] entries:", len(image_index))

# -----------------------
# DEBUG HELPERS
# -----------------------

def detect_block(text):
    t = text.lower()

    if "cloudflare" in t:
        return "CLOUDFLARE"
    if "attention required" in t:
        return "BLOCKED_PAGE"
    if "captcha" in t:
        return "CAPTCHA"

    return None


# -----------------------
# FETCH (UPGRADED + 429 FIX)
# -----------------------

def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            print(f"\n[FETCH] Attempt {attempt+1}: {url}")

            r = session.get(url, timeout=10)

            print("[STATUS]", r.status_code)
            print("[LENGTH]", len(r.text))

            # 🔥 429 HANDLING
            if r.status_code == 429:
                print("[RATE LIMITED - BACKOFF]")
                time.sleep(random.uniform(10, 20))
                continue

            block = detect_block(r.text)

            if block:
                print("[BLOCK DETECTED]", block)
                print("[SWITCHING TO CLOUDSCRAPER]")

                r = scraper.get(url, timeout=15)

                print("[CLOUDSCRAPER STATUS]", r.status_code)
                print("[CLOUDSCRAPER LENGTH]", len(r.text))

            if r.status_code == 200 and len(r.text) > 1000:
                soup = BeautifulSoup(r.text, "html.parser")

                title = soup.title.string if soup.title else "NO TITLE"
                print("[TITLE]", title)

                return soup

        except Exception as e:
            print("[FETCH ERROR]", e)

        time.sleep(random.uniform(3, 6))

    print("[FETCH FAILED]", url)
    return None


# -----------------------
# DOWNLOAD
# -----------------------

def download(url, path, retries=3):
    for attempt in range(retries):
        try:
            print(f"[DOWNLOAD] Attempt {attempt+1}: {url}")

            r = session.get(url, timeout=10)

            if r.status_code == 200:
                size = len(r.content)
                print("[SIZE]", size)

                if size < 5000:
                    print("[SKIP SMALL IMAGE]")
                    return False

                os.makedirs(os.path.dirname(path), exist_ok=True)

                with open(path, "wb") as f:
                    f.write(r.content)

                print("[SAVED]", path)
                return True

            else:
                print("[BAD STATUS]", r.status_code)

        except Exception as e:
            print("[DOWNLOAD ERROR]", e)

        time.sleep(1)

    return False


def hash_url(url):
    return hashlib.md5(url.encode()).hexdigest()


def classify(text, url=None):
    t = (text or "").lower()
    u = (url or "").lower()

    if "front" in t:
        return "front"
    if "back" in t or "rear" in t:
        return "back"
    if "side" in t or "profile" in t:
        return "side"
    if "angle" in t:
        return "angle"
    if "camera" in t:
        return "camera"
    if "display" in t:
        return "display"
    if "color" in t:
        return "variant"

    if "back" in u:
        return "back"

    return "misc"


def get_next_filename(folder, img_type):
    existing = [f for f in os.listdir(folder) if f.startswith(img_type)]
    return f"{img_type}_{len(existing)+1}.jpg"


def is_bad_image(url):
    url = url.lower()

    if "thumb" in url:
        return True
    if "logo" in url:
        return True
    if "gif" in url:
        return True
    if "svg" in url:
        return True

    return False


# -----------------------
# 🔥 MAIN IMAGE PAGE EXTRACTION (FIXED FILTERING)
# -----------------------

def extract_from_main_anchor(soup, folder, image_map, seen_hashes):

    main_a = soup.select_one(".specs-photo-main a")

    if not main_a:
        print("[NO MAIN ANCHOR]")
        return

    href = main_a.get("href")
    if not href:
        return

    img_page_url = urljoin(BASE, href)

    print("[MAIN IMAGE PAGE]", img_page_url)

    img_page = fetch(img_page_url)
    if not img_page:
        return

    imgs = img_page.select("img")

    print("[MAIN PAGE IMG COUNT]", len(imgs))

    slug_base = os.path.basename(folder).split("(")[0].lower().replace("-", "")

    for img in imgs:
        src = img.get("src")
        if not src:
            continue

        img_url = urljoin(BASE, src)

        # 🔥 STRICT FILTER
        if "/vv/pics/" not in img_url and "/bigpic/" not in img_url:
            continue

        if slug_base not in img_url.lower().replace("-", ""):
            continue

        if is_bad_image(img_url):
            continue

        if len(image_map["angle"]) >= MAX_PER_TYPE:
            break

        h = hash_url(img_url)
        if h in seen_hashes:
            continue

        filename = get_next_filename(folder, "angle")
        path = os.path.join(folder, filename)

        if download(img_url, path):
            image_map["angle"].append(filename)
            seen_hashes.add(h)


# -----------------------
# FALLBACK
# -----------------------

def fallback_guess_images(base_url, folder, image_map, seen_hashes):
    print("[FALLBACK - FINAL ROBUST]")

    gallery_url = base_url.replace(".php", "-pictures.php")
    soup = fetch(gallery_url) or fetch(base_url)

    if not soup:
        return

    collected = []

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue

        img_url = urljoin(BASE, src)

        # strict allow
        if not any(x in img_url for x in ["/vv/pics/", "/bigpic/"]):
            continue

        if is_bad_image(img_url):
            continue

        # 🔥 reject broken URLs like trailing dash
        if re.search(r"-\.jpg$", img_url):
            continue

        collected.append(img_url)

    # remove duplicates but keep order
    seen = set()
    final_urls = []
    for u in collected:
        if u not in seen:
            seen.add(u)
            final_urls.append(u)

    # 🔥 download
    for img_url in final_urls:
        if len(image_map["angle"]) >= MAX_PER_TYPE:
            break

        h = hash_url(img_url)
        if h in seen_hashes:
            continue

        filename = get_next_filename(folder, "angle")
        path = os.path.join(folder, filename)

        if download(img_url, path):
            image_map["angle"].append(filename)
            seen_hashes.add(h)


# -----------------------
# CORE
# -----------------------

def process_phone(phone):

    url = phone.get("url")
    slug = phone.get("slug")

    if not url or not slug:
        return

    print("\n==============================")
    if slug in image_index and image_index[slug].get("needs_hashing"):
        print("[CONVERTING LEGACY DATA]", slug)

        folder = os.path.join(IMAGE_ROOT, slug)
        existing_files = [f for f in os.listdir(folder) if f.endswith(".jpg")]

        seen_hashes = set()

        for f in existing_files:
            fake_hash = hashlib.md5(f.encode()).hexdigest()
            seen_hashes.add(fake_hash)

        image_index[slug] = {
            "downloaded": len(existing_files),
            "files": existing_files,
            "hashes": list(seen_hashes),
            "last_updated": datetime.date.today().isoformat(),
            "needs_hashing": False
        }

        with open(INDEX_FILE, "w") as f:
            json.dump(image_index, f, indent=2)

        return
    
    # 🔥 SKIP IF ALREADY DOWNLOADED ENOUGH
    if slug in image_index and image_index[slug].get("downloaded", 0) >= 5:
        print("[SKIP - ALREADY DOWNLOADED]", slug)
        return

    soup = fetch(url)

    if not soup:
        print("[NO SOUP]")
        return

    folder = os.path.join(IMAGE_ROOT, slug)
    os.makedirs(folder, exist_ok=True)
    print("[FOLDER PATH]", folder)
    # 🔥 RESUME SUPPORT
    existing_files = [f for f in os.listdir(folder) if f.endswith(".jpg")]

    if len(existing_files) >= 5:
        print("[SKIP - FOLDER COMPLETE]", slug)

        seen_hashes = set()
        for f in existing_files:
            fake_hash = hashlib.md5(f.encode()).hexdigest()
            seen_hashes.add(fake_hash)

        image_index[slug] = {
            "downloaded": len(existing_files),
            "files": existing_files,
            "hashes": list(seen_hashes),
            "last_updated": datetime.date.today().isoformat(),
            "needs_hashing": False
        }

        with open(INDEX_FILE, "w") as f:
            json.dump(image_index, f, indent=2)

        return

    seen_hashes = set(image_index.get(slug, {}).get("hashes") or [])

    # 🔥 ALSO TRACK URL HASHES FROM INDEX (if exists)
    """
    if slug in image_index:
        existing_files = image_index[slug].get("files", [])
        for f in existing_files:
            seen_hashes.add(f)
    """
    
    image_map = {
        "front": [],
        "back": [],
        "side": [],
        "angle": [],
        "camera": [],
        "display": [],
        "variant": [],
        "misc": []
    }

    hero_image = None

    main = soup.select_one(".specs-photo-main img")

    if main:
        src = main.get("src")

        if src:
            img_url = urljoin(BASE, src)

            # normalize only if valid
            if "/thumb/" in img_url:
                img_url = img_url.replace("/thumb/", "/bigpic/")

            # 🔥 reject malformed
            if re.search(r"-\.jpg$", img_url):
                img_url = None

            if img_url and not is_bad_image(img_url):
                h = hash_url(img_url)

                if h not in seen_hashes:
                    filename = get_next_filename(folder, "front")
                    path = os.path.join(folder, filename)

                    if download(img_url, path):
                        image_map["front"].append(filename)
                        seen_hashes.add(h)
                        hero_image = filename

    extract_from_main_anchor(soup, folder, image_map, seen_hashes)

    total_images = sum(len(v) for v in image_map.values())

    if total_images == 0:
        print("[USING FALLBACK IMAGE GUESS]")
        fallback_guess_images(url, folder, image_map, seen_hashes)

    if not hero_image:
        for t in ["front", "angle", "back"]:
            if image_map[t]:
                hero_image = image_map[t][0]
                break

    meta = {
        "slug": slug,
        "hero": hero_image,
        "images": image_map
    }

    with open(os.path.join(folder, "images.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print("[METADATA SAVED]", slug)
    # -----------------------
    # UPDATE INDEX
    # -----------------------
    files = [f for f in os.listdir(folder) if f.endswith(".jpg")]

    image_index[slug] = {
        "downloaded": len(files),
        "files": files,
        "hashes": list(seen_hashes),
        "last_updated": datetime.date.today().isoformat(),
        "needs_hashing": False
    }

    with open(INDEX_FILE, "w") as f:
        json.dump(image_index, f, indent=2)

    print("[INDEX UPDATED]", slug, "→", len(files))

    # 🔥 RATE CONTROL
    time.sleep(random.uniform(1.5, 3.5))


# -----------------------
# PIPELINE
# -----------------------

BATCH_SIZE = 50

def run():
    with open(DATA_FILE) as f:
        phones = json.load(f)

    print("TOTAL PHONES:", len(phones))

    progress_file = os.path.join(BASE_DIR, "data/progress.txt")

    start = 0
    
    if os.path.exists(progress_file):
        try:
            with open(progress_file) as f:
                content = f.read().strip()
    
                if content.isdigit():
                    start = int(content)
                else:
                    print("[INVALID PROGRESS FILE - RESETTING]")
                    start = 0
    
        except Exception as e:
            print("[PROGRESS READ ERROR]", e)
            start = 0

    end = start + BATCH_SIZE
    batch = phones[start:end]

    print(f"[BATCH] {start} → {end}")

    for phone in batch:
        try:
            process_phone(phone)
        except Exception as e:
            print("[ERROR]", e)

    with open(progress_file, "w") as f:
        f.write(str(end))

    print("DONE BATCH")


if __name__ == "__main__":
    run()
