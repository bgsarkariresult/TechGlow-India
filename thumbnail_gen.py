"""
TechGlow India — AI Thumbnail Generator (Pollinations.ai)
=========================================================
Multi-category support: Mobiles, TV, Audio, Laptops, Printers,
Smartwatches, Gadgets, Kitchen, Home, Accessories, Women, Men,
Travel, Car & Motorbike, Books etc.

Usage:
    from thumbnail_gen import generate_youtube_thumbnail

    thumb_path = generate_youtube_thumbnail(
        product_name="ultiads TJ-54/K Tower Multimedia System",
        price="₹6,999",
        specs={"power": "130W", "bass": "Deep Bass", "bt": "Bluetooth", "usb": "USB/SD"},
        category="audio",          # optional – auto-detect if not given
        output_path="bot_outputs/thumbnail.jpg",
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

CLASSIC_BASE = "https://image.pollinations.ai/prompt"
GEN_BASE = "https://gen.pollinations.ai/image"

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720

DEFAULT_REFERENCE = "assets/reference_face.jpg"


# ==========================================
# PRODUCT TYPE DETECTION
# ==========================================
CATEGORY_KEYWORDS = {
    "mobile": [
        "phone", "mobile", "smartphone", "iphone", "samsung", "xiaomi", "redmi",
        "poco", "realme", "oppo", "vivo", "oneplus", "nothing", "iqoo", "motorola",
        "pixel", "infinix", "tecno", "5g", "android"
    ],
    "tv": [
        "tv", "television", "smart tv", "led tv", "oled", "qled", "android tv",
        "google tv", "fire tv", "sony bravia", "samsung tv", "lg tv", "mi tv", "tcl"
    ],
    "audio": [
        "speaker", "tower", "soundbar", "earbuds", "earphone", "headphone",
        "neckband", "bluetooth speaker", "home theatre", "home theater",
        "multimedia system", "woofer", "bass", "audio", "tws", "buds"
    ],
    "laptop": [
        "laptop", "notebook", "macbook", "ultrabook", "chromebook", "gaming laptop",
        "thinkpad", "inspiron", "vivobook", "ideapad", "pavilion"
    ],
    "printer": [
        "printer", "inkjet", "laser printer", "all-in-one", "multifunction", "epson",
        "hp printer", "canon printer", "brother"
    ],
    "smartwatch": [
        "smartwatch", "smart watch", "watch", "fitness band", "fitness tracker",
        "galaxy watch", "apple watch", "amazfit", "noise", "boat watch", "fire-boltt"
    ],
    "gadget": [
        "gadget", "power bank", "charger", "cable", "adapter", "trimmer", "shaver",
        "camera", "action camera", "drone", "smart band", "neckband"
    ],
    "kitchen": [
        "mixer", "grinder", "juicer", "blender", "toaster", "kettle", "induction",
        "cooker", "pressure cooker", "air fryer", "microwave", "oven", "chimney",
        "gas stove", "roti maker", "sandwich maker"
    ],
    "home": [
        "home", "furniture", "bed", "sofa", "mattress", "curtain", "light", "bulb",
        "fan", "cooler", "ac", "air conditioner", "heater", "vacuum", "iron",
        "washing machine", "refrigerator", "fridge"
    ],
    "accessories": [
        "case", "cover", "screen guard", "tempered glass", "stand", "holder",
        "bag", "backpack", "wallet", "belt", "cap", "sunglass"
    ],
    "women": [
        "women", "woman", "ladies", "girl", "kurti", "saree", "lehenga", "dress",
        "western", "top", "jeans", "skirt", "lingerie", "bra", "panty", "nighty",
        "ethnic", "salwar", "suit"
    ],
    "men": [
        "men", "man", "male", "shirt", "tshirt", "t-shirt", "jeans men", "trouser",
        "blazer", "jacket", "shoes men", "formal", "casual wear men"
    ],
    "travel": [
        "travel", "suitcase", "trolley", "luggage", "backpack travel", "duffel",
        "travel bag", "neck pillow", "passport"
    ],
    "automobile": [
        "car", "bike", "motorbike", "scooter", "helmet", "car cover", "bike cover",
        "car accessory", "dashcam", "car charger", "tyre", "alloy"
    ],
    "books": [
        "book", "novel", "story", "comic", "magazine", "textbook", "guide", "exam"
    ],
}


def detect_category(product_name: str, specs: dict = None) -> str:
    """Product name + specs se category detect karta hai."""
    text = (product_name or "").lower()
    if specs:
        text += " " + " ".join(str(v).lower() for v in specs.values())

    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[cat] = score

    if not scores:
        return "gadget"  # default fallback

    return max(scores, key=scores.get)


def _clean_product_name(name: str) -> str:
    name = re.sub(r"[|–—\-].*$", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:50]


def _extract_price(price: str, specs: dict = None) -> str:
    if price and "₹" in str(price):
        m = re.search(r"₹[\d,]+", str(price))
        if m:
            return m.group(0)
    if specs:
        for v in specs.values():
            m = re.search(r"₹[\d,]+", str(v))
            if m:
                return m.group(0)
    return "₹999"


# ==========================================
# PROMPT BUILDERS (category-wise)
# ==========================================
def _base_girl() -> str:
    return (
        "Beautiful young Indian woman long dark wavy hair, bright yellow top, "
        "excited big open-mouth smile, pointing both index fingers at the product. "
    )


def build_mobile_prompt(product: str, price: str, specs: dict) -> str:
    ram = specs.get("ram", "8GB RAM")
    storage = specs.get("storage", "128GB")
    camera = specs.get("camera", "50MP")
    battery = specs.get("battery", "5000mAh")

    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"Two smartphones on wooden table front and back view of {product}. "
        f"Huge bold yellow text '{product}'. "
        f"Yellow banner '{storage} | {ram}'. "
        f"Right side icons: {ram}, {storage}, {camera} Camera, {battery} Battery, 5G. "
        f"Bottom left 4.2/5 star badge. Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_audio_prompt(product: str, price: str, specs: dict) -> str:
    power = specs.get("power", specs.get("watt", "130W"))
    return (
        f"YouTube thumbnail 16:9 ultra realistic, TechGlow India style. {_base_girl()}"
        f"Two tall glossy black tower multimedia speakers with glowing multi-color RGB LED rings "
        f"(blue cyan purple pink) standing on wooden table, remote control in front. "
        f"Huge bold yellow black banner text 'सिर्फ {price} में {product} तबाही!'. "
        f"Subtitle '{product}'. "
        f"Left red-yellow badge '{power} POWER DOUBLE TOWER BASS BLAST'. "
        f"Right side vertical feature badges: {power} Power Output, Deep Bass Experience, "
        f"Bluetooth Connectivity, USB / SD Support, FM Radio Function, Remote Control Included. "
        f"Bottom left banner 'घर को बनाओ होम थिएटर!'. Bottom right big red price tag '{price}'. "
        f"Bright yellow red black high contrast clickbait, photorealistic, no watermark."
    )


def build_tv_prompt(product: str, price: str, specs: dict) -> str:
    size = specs.get("size", "43 inch")
    res = specs.get("resolution", "4K")
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"Large modern {product} Smart TV on stand showing colorful content. "
        f"Huge bold yellow text '{product}'. "
        f"Yellow banner '{size} | {res} Ultra HD'. "
        f"Right side icons: {size}, {res}, Smart TV, Dolby Audio, Voice Control. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_laptop_prompt(product: str, price: str, specs: dict) -> str:
    cpu = specs.get("cpu", "Intel i5")
    ram = specs.get("ram", "16GB")
    ssd = specs.get("storage", "512GB SSD")
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"Open laptop and closed laptop of {product} on wooden desk. "
        f"Huge bold yellow text '{product}'. "
        f"Yellow banner '{cpu} | {ram} | {ssd}'. "
        f"Right side icons: {cpu}, {ram} RAM, {ssd}, Full HD, Long Battery. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_printer_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"{product} printer with paper coming out on desk. "
        f"Huge bold yellow text '{product}'. "
        f"Right side icons: Print, Scan, Copy, WiFi, Auto Duplex. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_smartwatch_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"{product} smartwatch on wrist and close-up of watch face. "
        f"Huge bold yellow text '{product}'. "
        f"Right side icons: AMOLED, SpO2, Heart Rate, 7 Days Battery, Bluetooth Calling. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_kitchen_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"{product} in modern kitchen setting on counter. "
        f"Huge bold yellow text '{product}'. "
        f"Right side icons: Powerful Motor, Easy Clean, 2 Year Warranty, Multiple Jars. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_home_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"{product} in stylish home living room setting. "
        f"Huge bold yellow text '{product}'. "
        f"Right side feature icons relevant to product. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_women_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. "
        f"Beautiful young Indian woman modelling or holding {product}, excited smile. "
        f"Huge bold yellow text '{product}'. "
        f"Right side icons: Premium Quality, Comfort Fit, Latest Design, Best Price. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_men_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. "
        f"Handsome young Indian man modelling or holding {product}, confident smile. "
        f"Huge bold yellow text '{product}'. "
        f"Right side icons: Premium Quality, Comfort Fit, Latest Design, Best Price. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_travel_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"{product} suitcase or travel bag in airport/travel setting. "
        f"Huge bold yellow text '{product}'. "
        f"Right side icons: Lightweight, Durable, Spacious, TSA Lock. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_automobile_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"{product} with car or bike in background. "
        f"Huge bold yellow text '{product}'. "
        f"Right side feature icons. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_books_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"Stack of books and close-up of {product} book cover. "
        f"Huge bold yellow text '{product}'. "
        f"Right side icons: Bestseller, Must Read, Latest Edition. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


def build_gadget_prompt(product: str, price: str, specs: dict) -> str:
    return (
        f"YouTube thumbnail 16:9, TechGlow India style. {_base_girl()}"
        f"{product} product prominently displayed on table. "
        f"Huge bold yellow text '{product}'. "
        f"Right side feature icons relevant to the gadget. "
        f"Bottom right red price '{price}'. "
        f"Bright yellow black high contrast clickbait, photorealistic, no watermark."
    )


PROMPT_BUILDERS = {
    "mobile": build_mobile_prompt,
    "tv": build_tv_prompt,
    "audio": build_audio_prompt,
    "laptop": build_laptop_prompt,
    "printer": build_printer_prompt,
    "smartwatch": build_smartwatch_prompt,
    "kitchen": build_kitchen_prompt,
    "home": build_home_prompt,
    "accessories": build_gadget_prompt,
    "women": build_women_prompt,
    "men": build_men_prompt,
    "travel": build_travel_prompt,
    "automobile": build_automobile_prompt,
    "books": build_books_prompt,
    "gadget": build_gadget_prompt,
}


def build_thumbnail_prompt(
    product_name: str,
    price: str = "",
    specs: dict = None,
    category: str = None,
) -> str:
    specs = specs or {}
    product = _clean_product_name(product_name)
    price = _extract_price(price, specs)

    if not category:
        category = detect_category(product_name, specs)

    builder = PROMPT_BUILDERS.get(category, build_gadget_prompt)
    prompt = builder(product, price, specs)

    print(f"📂 Detected category: {category}")
    return prompt.strip()


# ==========================================
# MAIN GENERATOR
# ==========================================
def generate_youtube_thumbnail(
    product_name: str,
    price: str = "",
    specs: dict = None,
    category: str = None,
    output_path: str = "thumbnail.jpg",
    reference_face_path: str = None,
    seed: int = None,
    max_retries: int = 3,
) -> str | None:
    """
    Pollinations.ai se YouTube thumbnail generate karta hai.
    Returns: saved file path ya None (fail hone par)
    """
    prompt = build_thumbnail_prompt(product_name, price, specs, category)
    seed = seed if seed is not None else random.randint(1, 999999)

    print(f"🎨 Generating thumbnail for: {product_name}")
    print(f"   Seed: {seed} | Size: {THUMB_WIDTH}x{THUMB_HEIGHT}")
    print(f"   Prompt length: {len(prompt)}")

    encoded = quote(prompt)
    classic_url = (
        f"{CLASSIC_BASE}/{encoded}"
        f"?width={THUMB_WIDTH}&height={THUMB_HEIGHT}"
        f"&seed={seed}&nologo=true&enhance=true"
    )
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
        urls_to_try.append(("gen-no-key", gen_url))

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

        time.sleep(5 + attempt * 2)

    print(f"❌ Thumbnail generation failed after all retries: {last_error}")
    return None


# ==========================================
# Quick test
# ==========================================
if __name__ == "__main__":
    print("=" * 60)
    print("Testing Audio (Speaker) thumbnail...")
    result = generate_youtube_thumbnail(
        product_name="ultiads TJ-54/K Tower Multimedia System",
        price="₹6,999",
        specs={
            "power": "130W",
            "bass": "Deep Bass",
            "bt": "Bluetooth",
            "usb": "USB/SD",
            "fm": "FM Radio",
        },
        category="audio",
        output_path="/home/workdir/artifacts/test_audio_thumb.jpg",
        seed=42,
    )
    if result:
        print(f"\n🎉 Audio test successful → {result}")
    else:
        print("\n❌ Audio test failed")
