import os
import json
import time
import requests
import hashlib
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ✅ NEW: cloudscraper fallback
import cloudscraper

BASE = "https://www.gsmarena.com"

# 🔥 NEW: absolute base dir (ADDED - no removal)
BASE_DIR = os.getcwd()
print("[BASE DIR]", BASE_DIR)

DATA_FILE = "data/phones/phones.json"
IMAGE_ROOT = "data/images"

# 🔥 NEW: absolute path override (ADDED - no removal)
DATA_FILE = os.path.join(BASE_DIR, DATA_FILE)
IMAGE_ROOT = os.path.join(BASE_DIR, IMAGE_ROOT)

print("[DATA FILE]", DATA_FILE)
print("[IMAGE ROOT]", IMAGE_ROOT)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

# ✅ CHANGED: use cloudscraper as PRIMARY (no removal, just override)
session = cloudscraper.create_scraper()
session.headers.update(HEADERS)

# ✅ fallback session (kept as-is)
scraper = cloudscraper.create_scraper()
scraper.headers.update(HEADERS)

MAX_PER_TYPE = 5


# -----------------------
# INIT
# -----------------------
# 🔥 UPDATED: use BASE_DIR paths (NO removal, only replacement with absolute-safe)
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "data/phones"), exist_ok=True)
os.makedirs(IMAGE_ROOT, exist_ok=True)

print("[DIR CHECK] data exists:", os.path.exists(os.path.join(BASE_DIR, "data")))
print("[DIR CHECK] images exists:", os.path.exists(IMAGE_ROOT))

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)


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
# FETCH (UPGRADED)
# -----------------------

def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            print(f"\n[FETCH] Attempt {attempt+1}: {url}")

            r = session.get(url, timeout=10)

            print("[STATUS]", r.status_code)
            print("[LENGTH]", len(r.text))

            block = detect_block(r.text)

            if block:
                print("[BLOCK DETECTED]", block)
                print("[SWITCHING TO CLOUDSCRAPER]")

                r = scraper.get(url, timeout=15)

                print("[CLOUDSCRAPER STATUS]", r.status_code)
                print("[CLOUDSCRAPER LENGTH]", len(r.text))

            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")

                title = soup.title.string if soup.title else "NO TITLE"
                print("[TITLE]", title)

                return soup

        except Exception as e:
            print("[FETCH ERROR]", e)

        time.sleep(2)

    print("[FETCH FAILED]", url)
    return None


# -----------------------
# DOWNLOAD (LOGGING)
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

                # 🔥 NEW: ensure parent dir exists before write
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
# 🔥 NEW: extract from main anchor
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

    for img in imgs:
        src = img.get("src")

        if not src:
            continue

        img_url = urljoin(BASE, src)

        if is_bad_image(img_url):
            continue

        h = hash_url(img_url)
        if h in seen_hashes:
            continue

        filename = get_next_filename(folder, "angle")
        path = os.path.join(folder, filename)

        if download(img_url, path):
            image_map["angle"].append(filename)
            seen_hashes.add(h)


# -----------------------
# 🔥 NEW: fallback guess
# -----------------------

def fallback_guess_images(base_url, folder, image_map, seen_hashes):

    print("[FALLBACK IMAGE GUESS]")

    base = base_url.split("/")[-1].replace(".php", "")

    for i in range(1, 6):
        guess = f"https://fdn2.gsmarena.com/vv/bigpic/{base}-{i}.jpg"

        if is_bad_image(guess):
            continue

        h = hash_url(guess)
        if h in seen_hashes:
            continue

        filename = get_next_filename(folder, "angle")
        path = os.path.join(folder, filename)

        if download(guess, path):
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
    print("PROCESSING:", slug)

    soup = fetch(url)

    if not soup:
        print("[NO SOUP]")
        return

    folder = os.path.join(IMAGE_ROOT, slug)

    # 🔥 EXTRA SAFETY (ADDED, not replacing)
    os.makedirs(folder, exist_ok=True)
    print("[FOLDER PATH]", folder)

    seen_hashes = set()

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

    # -----------------------
    # MAIN IMAGE
    # -----------------------
    main = soup.select_one(".specs-photo-main img")

    if not main:
        print("[NO MAIN IMAGE SELECTOR FOUND]")
    else:
        src = main.get("src")

        print("[MAIN RAW SRC]", src)

        if src:
            img_url = urljoin(BASE, src)
            img_url = img_url.replace("/thumb/", "/bigpic/")

            print("[MAIN IMG URL]", img_url)

            if not is_bad_image(img_url):

                h = hash_url(img_url)

                if h not in seen_hashes:

                    filename = get_next_filename(folder, "front")
                    path = os.path.join(folder, filename)

                    if download(img_url, path):
                        image_map["front"].append(filename)
                        seen_hashes.add(h)
                        hero_image = filename

    # -----------------------
    # EXTRA MAIN PAGE
    # -----------------------
    extract_from_main_anchor(soup, folder, image_map, seen_hashes)

    # -----------------------
    # GALLERY
    # -----------------------
    gallery_link = soup.find("a", string=lambda x: x and "Pictures" in x)

    if not gallery_link:
        print("[NO GALLERY LINK FOUND]")
    else:
        gallery_url = urljoin(BASE, gallery_link.get("href"))
        print("[GALLERY URL]", gallery_url)

        gallery = fetch(gallery_url)

        if not gallery:
            print("[GALLERY FETCH FAILED]")
        else:
            imgs = gallery.select("img")

            print("[GALLERY IMG COUNT]", len(imgs))

            for img in imgs:

                src = img.get("src")
                alt = img.get("alt", "")

                if not src:
                    continue

                img_url = urljoin(BASE, src)
                img_url = img_url.replace("/thumb/", "/bigpic/")

                if is_bad_image(img_url):
                    continue

                h = hash_url(img_url)
                if h in seen_hashes:
                    continue

                img_type = classify(alt, img_url)

                if len(image_map[img_type]) >= MAX_PER_TYPE:
                    continue

                filename = get_next_filename(folder, img_type)
                path = os.path.join(folder, filename)

                if download(img_url, path):
                    image_map[img_type].append(filename)
                    seen_hashes.add(h)

    # -----------------------
    # FALLBACK
    # -----------------------
    total_images = sum(len(v) for v in image_map.values())

    if total_images <= 1:
        print("[USING FALLBACK IMAGE GUESS]")
        fallback_guess_images(url, folder, image_map, seen_hashes)

    # -----------------------
    # HERO
    # -----------------------
    if not hero_image:
        for t in ["front", "angle", "back"]:
            if image_map[t]:
                hero_image = image_map[t][0]
                break

    # -----------------------
    # METADATA
    # -----------------------
    meta = {
        "slug": slug,
        "hero": hero_image,
        "images": image_map
    }

    meta_path = os.path.join(folder, "images.json")

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print("[METADATA SAVED]", slug)

    time.sleep(0.5)


# -----------------------
# PIPELINE
# -----------------------

BATCH_SIZE = 50

def run():
    with open(DATA_FILE) as f:
        phones = json.load(f)

    print("TOTAL PHONES:", len(phones))

    # 🔥 track progress
    progress_file = os.path.join(BASE_DIR, "data/progress.txt")

    start = 0
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            start = int(f.read().strip())

    end = start + BATCH_SIZE
    batch = phones[start:end]

    print(f"[BATCH] {start} → {end}")

    for phone in batch:
        try:
            process_phone(phone)
        except Exception as e:
            print("[ERROR]", e)

    # 🔥 save progress
    with open(progress_file, "w") as f:
        f.write(str(end))

    print("DONE BATCH")


if __name__ == "__main__":
    run()
