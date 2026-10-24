"""
TechGlow India — AI Thumbnail Generator (Pollinations.ai)
=========================================================
Free (no key needed) + optional POLLINATIONS_API_KEY for better limits / models.

Usage inside tech_review_bot.py:
    from thumbnail_gen import generate_youtube_thumbnail

    thumb_path = generate_youtube_thumbnail(
        product_name="POCO X8 Pro Max",
        price="₹18,999",
        specs={"ram": "12GB", "storage": "256GB", "camera": "108MP", "battery": "5000mAh"},
        output_path="bot_outputs/thumbnail.jpg",
        reference_face_path="assets/reference_face.jpg",   # optional – same face ke liye
    )
"""

import os
import re
import time
import random
import requests
from urllib.parse import quote
from PIL import Image
from io import BytesIO

# ==========================================
# CONFIG
# ==========================================
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "").strip()

# Classic free endpoint (no key required, rate-limited)
CLASSIC_BASE = "https://image.pollinations.ai/prompt"

# New unified endpoint (better models when key present)
GEN_BASE = "https://gen.pollinations.ai/image"

# YouTube recommended thumbnail size
THUMB_WIDTH = 1280
THUMB_HEIGHT = 720

# Reference face (same model face ke liye). Repo me assets/reference_face.jpg rakho.
DEFAULT_REFERENCE = "assets/reference_face.jpg"


def _clean_product_name(name: str) -> str:
    name = re.sub(r"[|–—\-].*$", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:45]


def build_thumbnail_prompt(product_name: str, price: str = "", specs: dict = None) -> str:
    """
    Demo image jaisa strong clickbait thumbnail prompt (short for free endpoint URL limits).
    Same Indian woman style + product + specs + rating + CTA.
    """
    specs = specs or {}
    product = _clean_product_name(product_name)

    # Key specs extract (keep short)
    ram = "12GB RAM"
    storage = "256GB"
    camera = "108MP"
    battery = "5000mAh"

    for k, v in (specs or {}).items():
        val = str(v)
        low = k.lower() + " " + val.lower()
        if "ram" in low and re.search(r"\d+\s*gb", val, re.I):
            ram = re.search(r"\d+\s*GB", val, re.I).group(0) + " RAM"
        if ("storage" in low or "rom" in low) and re.search(r"\d+\s*gb", val, re.I):
            storage = re.search(r"\d+\s*GB", val, re.I).group(0)
        if "camera" in low or "mp" in low:
            m = re.search(r"\d+\s*MP", val, re.I)
            if m:
                camera = m.group(0)
        if "battery" in low or "mah" in low:
            m = re.search(r"\d+\s*mAh", val, re.I)
            if m:
                battery = m.group(0)

    # Compact prompt — free endpoint has URL length + rate limits
    prompt = (
        f"YouTube thumbnail 16:9, TechGlow India style. "
        f"Beautiful young Indian woman long dark wavy hair, bright yellow top, "
        f"excited big smile, pointing both fingers at {product} smartphone. "
        f"Two phones on wooden table front and back view. "
        f"Huge bold yellow text '{product}'. "
        f"Yellow banner '{storage} | {ram}'. "
        f"Right side icons: {ram}, {storage}, {camera} Camera, {battery} Battery, 5G. "
        f"Bottom left 4.2/5 star badge. Bottom right 'Best 5G Phone Under Budget?'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )
    return prompt.strip()


def generate_youtube_thumbnail(
    product_name: str,
    price: str = "",
    specs: dict = None,
    output_path: str = "thumbnail.jpg",
    reference_face_path: str = None,
    seed: int = None,
    max_retries: int = 3,
) -> str | None:
    """
    Pollinations.ai se YouTube thumbnail generate karta hai.
    Returns: saved file path ya None (fail hone par)
    """
    prompt = build_thumbnail_prompt(product_name, price, specs)
    seed = seed if seed is not None else random.randint(1, 999999)

    # Reference face for consistency (optional)
    ref_path = reference_face_path or DEFAULT_REFERENCE
    use_img2img = False
    image_param = None

    if ref_path and os.path.exists(ref_path):
        # Local file ko temporarily public URL nahi bana sakte free me,
        # isliye abhi strong text description use karte hain.
        # Future: agar POLLINATIONS_API_KEY ho to media.pollinations.ai pe upload karke img2img.
        print(f"ℹ️ Reference face found ({ref_path}) — prompt me face description lock kiya gaya.")
        use_img2img = False  # pure free path me URL chahiye hoti hai

    print(f"🎨 Generating thumbnail for: {product_name}")
    print(f"   Seed: {seed} | Size: {THUMB_WIDTH}x{THUMB_HEIGHT}")

    # --- Try classic free endpoint first ---
    encoded = quote(prompt)
    classic_url = (
        f"{CLASSIC_BASE}/{encoded}"
        f"?width={THUMB_WIDTH}&height={THUMB_HEIGHT}"
        f"&seed={seed}&nologo=true&enhance=true"
    )

    # New endpoint (better when key present)
    gen_url = (
        f"{GEN_BASE}/{encoded}"
        f"?width={THUMB_WIDTH}&height={THUMB_HEIGHT}"
        f"&seed={seed}&nologo=true&model=flux"
    )
    if POLLINATIONS_API_KEY:
        gen_url += f"&key={POLLINATIONS_API_KEY}"

    urls_to_try = []
    if POLLINATIONS_API_KEY:
        urls_to_try.append(("gen+key", gen_url))
    urls_to_try.append(("classic-free", classic_url))
    if not POLLINATIONS_API_KEY:
        urls_to_try.append(("gen-no-key", gen_url))  # sometimes works

    last_error = None
    for attempt in range(1, max_retries + 1):
        for label, url in urls_to_try:
            try:
                print(f"🔄 Attempt {attempt}/{max_retries} via {label}...")
                headers = {"User-Agent": "TechGlow-India-Bot/1.0"}
                if POLLINATIONS_API_KEY and "gen.pollinations" in url:
                    headers["Authorization"] = f"Bearer {POLLINATIONS_API_KEY}"

                resp = requests.get(url, headers=headers, timeout=90, stream=True)

                if resp.status_code == 402:
                    # Free rate-limit hit — wait and retry
                    retry_after = int(resp.headers.get("Retry-After", 50))
                    print(f"⏳ Rate limit (402). Waiting {retry_after}s...")
                    time.sleep(min(retry_after, 60))
                    raise Exception("Rate limited (402)")

                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}")

                content_type = resp.headers.get("content-type", "").lower()
                if "image" not in content_type and "octet-stream" not in content_type:
                    raise Exception(f"Not an image (content-type: {content_type})")

                img_data = resp.content
                if len(img_data) < 15000:
                    raise Exception(f"Image too small ({len(img_data)} bytes)")

                # Validate + force exact size
                img = Image.open(BytesIO(img_data)).convert("RGB")
                if img.size != (THUMB_WIDTH, THUMB_HEIGHT):
                    img = img.resize((THUMB_WIDTH, THUMB_HEIGHT), Image.Resampling.LANCZOS)

                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                img.save(output_path, "JPEG", quality=92, optimize=True)
                print(f"✅ Thumbnail saved: {output_path} ({os.path.getsize(output_path)/1024:.0f} KB)")
                return output_path

            except Exception as e:
                last_error = e
                print(f"⚠️ {label} failed: {e}")
                time.sleep(2)

        # rate-limit friendly wait between full rounds
        time.sleep(5 + attempt * 2)

    print(f"❌ Thumbnail generation failed after all retries: {last_error}")
    return None


# ==========================================
# Quick test (python thumbnail_gen.py)
# ==========================================
if __name__ == "__main__":
    test_path = "test_thumbnail.jpg"
    result = generate_youtube_thumbnail(
        product_name="POCO X8 Pro Max 5G",
        price="₹18,999",
        specs={
            "ram": "12GB RAM",
            "storage": "256GB",
            "camera": "108MP Camera",
            "battery": "5000mAh",
        },
        output_path=test_path,
    )
    if result:
        print(f"\n🎉 Test successful → {result}")
    else:
        print("\n❌ Test failed")
