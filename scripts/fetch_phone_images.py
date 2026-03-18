import os
import json
import time
import requests
import hashlib
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://www.gsmarena.com"

DATA_FILE = "data/phones/phones.json"
IMAGE_ROOT = "data/images"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (PhoneImageBot/2.0)"
}

session = requests.Session()
session.headers.update(HEADERS)

MAX_PER_TYPE = 5


# -----------------------
# 🔥 INIT FIX (YOUR ISSUE 1)
# -----------------------
os.makedirs("data", exist_ok=True)
os.makedirs("data/phones", exist_ok=True)
os.makedirs(IMAGE_ROOT, exist_ok=True)

# ensure phones.json exists
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)


# -----------------------
# helpers
# -----------------------

def fetch(url, retries=3):
    for _ in range(retries):
        try:
            r = session.get(url, timeout=10)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print("fetch error:", e)

        time.sleep(2)
    return None


def download(url, path, retries=3):
    for _ in range(retries):
        try:
            r = session.get(url, timeout=10)

            if r.status_code == 200 and len(r.content) > 5000:
                with open(path, "wb") as f:
                    f.write(r.content)

                print("DOWNLOADED:", path)
                return True
            else:
                print("SKIPPED (small/bad):", url)

        except Exception as e:
            print("download error:", e)

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
    if "angle" in t or "perspective" in t:
        return "angle"
    if "camera" in t:
        return "camera"
    if "display" in t or "screen" in t:
        return "display"
    if "color" in t or "variant" in t:
        return "variant"

    if "back" in u:
        return "back"
    if "side" in u:
        return "side"

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
# core logic
# -----------------------

def process_phone(phone):

    url = phone.get("url")
    slug = phone.get("slug")

    if not url or not slug:
        return

    print("\nProcessing:", slug)

    soup = fetch(url)
    if not soup:
        print("FAILED FETCH:", url)
        return

    folder = os.path.join(IMAGE_ROOT, slug)
    os.makedirs(folder, exist_ok=True)

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

    if main:
        src = main.get("src")

        if src:
            img_url = urljoin(BASE, src)
            img_url = img_url.replace("/thumb/", "/bigpic/")

            print("MAIN IMG:", img_url)

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
    # GALLERY
    # -----------------------
    gallery_link = soup.find("a", string=lambda x: x and "Pictures" in x)

    if gallery_link and gallery_link.get("href"):

        gallery_url = urljoin(BASE, gallery_link["href"])
        print("GALLERY:", gallery_url)

        gallery = fetch(gallery_url)

        if gallery:
            imgs = gallery.select("img")

            print("GALLERY IMAGES FOUND:", len(imgs))

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
    # HERO FALLBACK
    # -----------------------
    if not hero_image:
        for t in ["front", "angle", "back"]:
            if image_map[t]:
                hero_image = image_map[t][0]
                break

    # -----------------------
    # METADATA JSON
    # -----------------------
    meta = {
        "slug": slug,
        "hero": hero_image,
        "images": image_map
    }

    meta_path = os.path.join(folder, "images.json")

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print("METADATA SAVED:", slug)

    time.sleep(0.5)


# -----------------------
# pipeline
# -----------------------

def run():

    with open(DATA_FILE) as f:
        phones = json.load(f)

    print("TOTAL PHONES:", len(phones))

    for phone in phones:
        try:
            process_phone(phone)
        except Exception as e:
            print("error:", e)

    print("DONE")


if __name__ == "__main__":
    run()
