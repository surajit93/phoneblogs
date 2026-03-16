# scripts/generate_buggy.py

import os
import requests
import time
from PIL import Image
from io import BytesIO

HF_TOKEN = os.getenv("HF_TOKEN")

if not HF_TOKEN:
    raise ValueError("HF_TOKEN not set")

API_URL = "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0"

headers = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

OUTPUT_DIR = "site/assets/buggy"
os.makedirs(OUTPUT_DIR, exist_ok=True)

prompt = """
Buggy mascot character sheet, cute ladybird tech insect mascot,
round head, two big white eyes with black pupils,
one antenna, six legs, red shell with black dots,
simple cartoon vector style, flat colors,
white background, brand mascot style,
character sheet showing 20 different expressions,
grid layout, same mascot repeated,
happy, sad, angry, shocked, thinking, laughing,
sleepy, confused, celebrating, facepalm,
dancing, excited, scared, victory,
detective, rocket riding, overheating,
cool sunglasses, crying, pixel glitch
"""

def generate_character_sheet():

    for _ in range(10):

        response = requests.post(
            API_URL,
            headers=headers,
            json={"inputs": prompt}
        )

        if response.status_code == 200:
            return Image.open(BytesIO(response.content))

        if "loading" in response.text.lower():
            print("Model loading... retrying")
            time.sleep(10)
            continue

        raise Exception(response.text)

    raise Exception("Model failed to load")

def split_sheet(image, rows=4, cols=5):

    width, height = image.size
    cell_w = width // cols
    cell_h = height // rows

    count = 0

    for r in range(rows):
        for c in range(cols):

            left = c * cell_w
            top = r * cell_h
            right = left + cell_w
            bottom = top + cell_h

            crop = image.crop((left, top, right, bottom))

            filename = os.path.join(OUTPUT_DIR, f"buggy_{count}.png")
            crop.save(filename)

            print("saved", filename)

            count += 1

def main():

    print("Generating Buggy character sheet...")

    sheet = generate_character_sheet()

    sheet_path = os.path.join(OUTPUT_DIR, "buggy_sheet.png")
    sheet.save(sheet_path)

    print("Character sheet saved:", sheet_path)

    print("Splitting expressions...")

    split_sheet(sheet)

    print("Done. 20 Buggy expressions generated.")

if __name__ == "__main__":
    main()
