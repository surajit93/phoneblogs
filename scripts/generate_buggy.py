# scripts/generate_buggy.py

import os
import requests
import time
from PIL import Image, ImageDraw
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

BASE_FILE = os.path.join(OUTPUT_DIR, "buggy_base.png")

prompt = """
Buggy mascot for tech website, cute friendly ladybug mascot,
simple round body with glossy red shell and small black spots,
large expressive cartoon eyes on the front,
small smiling face,
one tiny antenna,
six tiny legs underneath body,
clean modern mascot design,
flat vector illustration style,
high contrast colors,
minimal shapes, smooth lines,
centered on canvas, full body visible,
white background,
professional brand mascot
"""

negative_prompt = """
mosquito, needle, syringe, scary insect,
realistic bug texture, hairy insect,
photorealistic insect,
standing upright insect,
humanoid bug,
cropped body,
half insect,
macro photography
"""

EXPRESSIONS = {
    "happy": "smile",
    "sad": "sad",
    "angry": "angry",
    "shocked": "shock",
    "cool": "cool",
    "sleepy": "sleepy",
    "thinking": "thinking"
}


def generate_buggy():

    if os.path.exists(BASE_FILE):
        print("Buggy base already exists, skipping generation.")
        return Image.open(BASE_FILE)

    for attempt in range(10):

        print("Generating Buggy (attempt)", attempt + 1)

        response = requests.post(
            API_URL,
            headers=headers,
            json={
                "inputs": prompt,
                "parameters": {
                    "negative_prompt": negative_prompt,
                    "guidance_scale": 8.5,
                    "width": 1024,
                    "height": 1024
                }
            }
        )

        if response.status_code == 200:

            image = Image.open(BytesIO(response.content))
            image.save(BASE_FILE)

            print("Buggy base saved:", BASE_FILE)
            return image

        if "loading" in response.text.lower():
            print("Model loading, retrying...")
            time.sleep(10)
            continue

        raise Exception(response.text)

    raise Exception("Model failed to generate Buggy")


def draw_expression(canvas, mode):

    draw = ImageDraw.Draw(canvas)

    w, h = canvas.size

    eye_y = int(h * 0.35)
    mouth_y = int(h * 0.55)

    if mode == "smile":
        draw.arc((w*0.4, mouth_y, w*0.6, mouth_y+40), 0, 180, width=6)

    elif mode == "sad":
        draw.arc((w*0.4, mouth_y+20, w*0.6, mouth_y+60), 180, 360, width=6)

    elif mode == "angry":
        draw.line((w*0.35, eye_y-20, w*0.45, eye_y-10), width=6)
        draw.line((w*0.65, eye_y-20, w*0.55, eye_y-10), width=6)

    elif mode == "shock":
        draw.ellipse((w*0.47, mouth_y, w*0.53, mouth_y+35), outline="black", width=6)

    elif mode == "cool":
        draw.rectangle((w*0.35, eye_y-10, w*0.65, eye_y+10), fill="black")

    elif mode == "sleepy":
        draw.line((w*0.4, eye_y, w*0.45, eye_y), width=6)
        draw.line((w*0.55, eye_y, w*0.6, eye_y), width=6)

    elif mode == "thinking":
        draw.arc((w*0.45, mouth_y, w*0.55, mouth_y+20), 0, 180, width=6)


def build_expressions(base_img):

    for name, mode in EXPRESSIONS.items():

        canvas = base_img.copy()

        draw_expression(canvas, mode)

        filename = os.path.join(OUTPUT_DIR, f"buggy_{name}.png")

        canvas.save(filename)

        print("created", filename)


def main():

    base_img = generate_buggy()

    build_expressions(base_img)

    print("Buggy mascot generation complete.")


if __name__ == "__main__":
    main()
