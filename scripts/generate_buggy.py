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
Buggy website mascot, cute small ladybug insect mascot,
natural crawling pose on six legs, never standing upright,
top-down or slight top angle like a real ladybug,
round red shell with small black spots,
small round head attached to body,
two large white cartoon eyes with black pupils,
one short antenna centered on head,
friendly simple face,
clean mascot design for tech website,
minimal shapes, flat colors, simple vector style,
white background, centered subject,
full body visible, no cropping,
same Buggy character repeated in a 4x5 grid with different facial expressions
"""

negative_prompt = """
mosquito, syringe, needle, robot, humanoid body,
standing upright, human legs, wings spread,
weird insect hybrid, horror insect,
cropped body, half body, cut off legs,
3d render, photorealistic bug
"""

# semantic names for expressions
EXPRESSIONS = [
    "happy",
    "sad",
    "angry",
    "shocked",
    "thinking",
    "laughing",
    "sleepy",
    "confused",
    "celebrating",
    "facepalm",
    "dancing",
    "excited",
    "scared",
    "victory",
    "detective",
    "rocket",
    "overheated",
    "cool",
    "crying",
    "glitch"
]

def generate_character_sheet():

    for attempt in range(10):

        print("Generating Buggy sheet (attempt)", attempt + 1)

        response = requests.post(
            API_URL,
            headers=headers,
            json={
                "inputs": prompt,
                "parameters": {
                    "negative_prompt": negative_prompt,
                    "guidance_scale": 8.5
                }
            }
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

    index = 0

    for r in range(rows):
        for c in range(cols):

            left = c * cell_w
            top = r * cell_h
            right = left + cell_w
            bottom = top + cell_h

            crop = image.crop((left, top, right, bottom))

            name = EXPRESSIONS[index]
            filename = os.path.join(OUTPUT_DIR, f"buggy_{name}.png")

            crop.save(filename)

            print("saved", filename)

            index += 1

def main():

    print("Generating Buggy character sheet...")

    sheet = generate_character_sheet()

    sheet_path = os.path.join(OUTPUT_DIR, "buggy_sheet.png")
    sheet.save(sheet_path)

    print("Character sheet saved:", sheet_path)

    print("Splitting expressions...")

    split_sheet(sheet)

    print("Done. Buggy expressions generated.")

if __name__ == "__main__":
    main()
