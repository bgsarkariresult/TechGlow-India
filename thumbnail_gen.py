"""
TechGlow India — YouTube Thumbnail Generator (3 rotating styles)
================================================================
Kaam kaise karta hai:
  1. Asli product photo se product ka cutout banta hai (white background hatakar).
  2. Aapki face photos (assets/faces/*.png, transparent) se ek photo random chuni jaati hai.
  3. Background: Style A me Gemini se room-scene (bina text/bina insaan), baaki styles me
     code se banta hai. Gemini fail ho to code wala background automatically use hota hai.
  4. Saara text (Hindi headline, price, badges) Pillow se likha jaata hai, isliye
     spelling aur price hamesha sahi aate hain.

Styles:
  A = Banner   (red/yellow brush banners + 4 rang-birange badges, room background)
  B = Studio   (peela top band, "BRAND Review 2026" title, 6 feature capsules)  -- POCO-style
  C = Brand    (neela background, bada brand naam, peela brush banner, laal strip) -- Motorola-style

Channel naam badalna ho to env THUMB_CHANNEL_NAME set karo (default: TechGlow India).

Usage:
    from thumbnail_gen import generate_youtube_thumbnail
    path = generate_youtube_thumbnail(
        product_name="DREAME L50 Ultra CE Robot Vacuum and Mop",
        price="₹64,999", specs={...}, product_image_path="photo.jpg",
        output_path="bot_outputs/thumbnail.jpg", style=None,   # None = random
    )
"""

import glob
import json
import math
import os
import random
import re
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

# ==========================================
# CONFIG
# ==========================================
THUMB_WIDTH = 1280
THUMB_HEIGHT = 720
W, H = THUMB_WIDTH, THUMB_HEIGHT

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
FACES_DIR = ASSETS_DIR / "faces"
FONT_MAIN = ASSETS_DIR / "fonts" / "Poppins-Bold.ttf"          # Hindi + English + ₹
FONT_BIG = ASSETS_DIR / "fonts" / "ArchivoBlack-Regular.ttf"   # sirf English bade shabd

STYLES = ("A", "B", "C")
CHANNEL_NAME = os.getenv("THUMB_CHANNEL_NAME", "TechGlow India").strip() or "TechGlow India"

RED = (222, 18, 28)
DARK_RED = (170, 10, 20)
YELLOW = (255, 214, 10)
BLACK = (14, 14, 16)
WHITE = (255, 255, 255)
GREEN = (36, 190, 80)


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
        "washing machine", "refrigerator", "fridge", "robot"
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
        # poora shabd match ("headphones" me "phone" ya "playback" me "ac" nahi pakadna chahiye)
        score = sum(
            1 for kw in keywords
            if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"s?(?![a-z0-9])", text)
        )
        if score > 0:
            scores[cat] = score

    if not scores:
        return "gadget"  # default fallback

    return max(scores, key=scores.get)


# Category-wise default copy (Gemini text fail ho to ye use hota hai)
CATEGORY_COPY = {
    "mobile":     dict(tail="धमाकेदार फोन", big=("SMART", "PHONE"), label="SMARTPHONE REVIEW",
                       slogan=("हर पल बनाओ", "स्मार्ट!"), hook="खरीदने से पहले देखो!"),
    "tv":         dict(tail="सिनेमा जैसा मज़ा", big=("BIG", "SCREEN"), label="SMART TV REVIEW",
                       slogan=("घर को बनाओ", "थिएटर!"), hook="TV लेने से पहले देखो!"),
    "audio":      dict(tail="ज़बरदस्त साउंड", big=("BASS", "BLAST"), label="SOUND SYSTEM REVIEW",
                       slogan=("घर को बनाओ", "होम थिएटर!"), hook="साउंड का असली टेस्ट!"),
    "laptop":     dict(tail="पावरफुल लैपटॉप", big=("POWER", "LAPTOP"), label="LAPTOP REVIEW",
                       slogan=("काम को बनाओ", "फास्ट!"), hook="लैपटॉप लेने से पहले देखो!"),
    "printer":    dict(tail="प्रिंटिंग का बादशाह", big=("SMART", "PRINTER"), label="PRINTER REVIEW",
                       slogan=("ऑफिस को बनाओ", "स्मार्ट!"), hook="खरीदने से पहले देखो!"),
    "smartwatch": dict(tail="स्मार्ट वॉच", big=("SMART", "WATCH"), label="SMARTWATCH REVIEW",
                       slogan=("कलाई पर", "स्टाइल!"), hook="वॉच लेने से पहले देखो!"),
    "kitchen":    dict(tail="किचन का साथी", big=("SMART", "KITCHEN"), label="KITCHEN REVIEW",
                       slogan=("किचन को बनाओ", "स्मार्ट!"), hook="खरीदने से पहले देखो!"),
    "home":       dict(tail="स्मार्ट घर", big=("SMART", "HOME"), label="HOME GADGET REVIEW",
                       slogan=("घर को बनाओ", "स्मार्ट होम!"), hook="खरीदने से पहले देखो!"),
    "gadget":     dict(tail="कमाल का गैजेट", big=("SMART", "GADGET"), label="GADGET REVIEW",
                       slogan=("लाइफ को बनाओ", "स्मार्ट!"), hook="खरीदने से पहले देखो!"),
}
for _c in ("accessories", "women", "men", "travel", "automobile", "books"):
    CATEGORY_COPY[_c] = CATEGORY_COPY["gadget"]

# Gemini background ke liye scene (koi insaan/text/product nahi)
CATEGORY_SCENES = {
    "mobile": "a modern desk setup with soft bokeh lights",
    "tv": "a cozy modern living room with a plain wall",
    "audio": "a stylish modern living room with warm lights",
    "laptop": "a bright modern home-office desk area",
    "kitchen": "a clean modern kitchen with marble counter",
    "home": "a bright modern living room with large windows and plants",
}


# ==========================================
# SMALL HELPERS
# ==========================================
def _font(size: int, big: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BIG if big else FONT_MAIN
    try:
        return ImageFont.truetype(str(path), int(size))
    except Exception:
        return ImageFont.load_default()


def _is_latin(text: str) -> bool:
    return all(ord(ch) < 0x0900 or ord(ch) > 0x097F for ch in text)


def _clean_product_name(name: str) -> str:
    name = re.sub(r"\s+", " ", str(name or "Product")).strip()
    # lambe blog-title ka sirf product wala hissa lo (| ya : se pehle)
    name = re.split(r"\s[|–—]\s|:\s|\s[Ww]ith\s", name)[0].strip()
    if len(name) > 48:                      # shabd beech me na kate
        name = name[:48].rsplit(" ", 1)[0]
    return name


def _extract_price(price: str, specs: dict = None) -> str:
    """Sirf asli price lautata hai; na mile to khaali string (kabhi invent nahi karta)."""
    if price:
        m = re.search(r"₹\s?[\d,]+", str(price))
        if m:
            return m.group(0).replace(" ", "")
    if specs:
        for k, v in specs.items():
            if "price" in str(k).lower() or "₹" in str(v):
                m = re.search(r"₹\s?[\d,]+", str(v))
                if m:
                    return m.group(0).replace(" ", "")
    return ""


def _find_rating(specs: dict) -> str:
    """Rating tabhi lautata hai jab article ke specs me sach me ho."""
    for k, v in (specs or {}).items():
        if "rating" in str(k).lower() or "star" in str(k).lower():
            m = re.search(r"\b([0-5](?:\.\d)?)\b", str(v))
            if m and 0 < float(m.group(1)) <= 5:
                return f"{float(m.group(1)):g}"
    return ""


def _short_facts(specs: dict, limit: int = 6) -> list:
    """Specs se chhote, verified fact-text (badge/checklist ke liye)."""
    facts = []
    for k, v in (specs or {}).items():
        key = str(k).lower()
        val = re.sub(r"\s+", " ", str(v or "")).strip()
        if not val or "₹" in val or any(x in key for x in ("price", "rating", "star", "link", "url")):
            continue
        if len(val) <= 22:
            facts.append(val)
        if len(facts) >= limit:
            break
    return facts


def _split_two_lines(text: str, max_chars: int = 11):
    words = text.split()
    if len(text) <= max_chars or len(words) == 1:
        return (text[:max_chars + 3], "")
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(a), len(b))
        if best is None or score < best[0]:
            best = (score, a, b)
    return (best[1][:max_chars + 3], best[2][:max_chars + 3])


def _fit_font(draw, text, max_w, max_h, start, min_size=12, big=False):
    size = int(start)
    while size > min_size:
        f = _font(size, big)
        l, t, r, b = draw.textbbox((0, 0), text, font=f)
        if (r - l) <= max_w and (b - t) <= max_h:
            return f
        size -= 2
    return _font(min_size, big)


def _runs_width(draw, runs, font, stroke=0):
    return sum(draw.textlength(t, font=font) for t, _ in runs) + 2 * stroke


def _draw_runs(draw, runs, cx, cy, font, stroke=4, stroke_fill=BLACK):
    """Rang-birange text runs ko (cx, cy) par center karke likhta hai."""
    total = sum(draw.textlength(t, font=font) for t, _ in runs)
    x = cx - total / 2
    for text, color in runs:
        draw.text((x, cy), text, font=font, fill=color, anchor="lm",
                  stroke_width=stroke, stroke_fill=stroke_fill)
        x += draw.textlength(text, font=font)


def _fit_runs(draw, runs, max_w, max_h, start, big=False, stroke=4):
    size = int(start)
    while size > 14:
        f = _font(size, big)
        w = sum(draw.textlength(t, font=f) for t, _ in runs) + 2 * stroke
        l, t, r, b = draw.textbbox((0, 0), "".join(t for t, _ in runs), font=f)
        if w <= max_w and (b - t) <= max_h:
            return f
        size -= 2
    return _font(14, big)


# ==========================================
# SHAPES (anti-aliased)
# ==========================================
def _gradient(size, c1, c2, vertical=True):
    w, h = size
    t = np.linspace(0, 1, h if vertical else w, dtype=np.float32)
    t = t[:, None] if vertical else t[None, :]
    c1 = np.array(c1, dtype=np.float32)
    c2 = np.array(c2, dtype=np.float32)
    arr = c1 + (c2 - c1) * t[..., None]
    if vertical:
        arr = np.repeat(arr, w, axis=1)
    else:
        arr = np.repeat(arr, h, axis=0)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def _paint_poly(canvas, pts, fill, ss=3):
    """Polygon ko anti-aliased banakar canvas (RGBA) par chipkata hai. fill = color ya (c1, c2) gradient."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = int(max(0, min(xs) - 2)), int(max(0, min(ys) - 2))
    x1, y1 = int(min(W, max(xs) + 3)), int(min(H, max(ys) + 3))
    if x1 <= x0 or y1 <= y0:
        return
    bw, bh = x1 - x0, y1 - y0
    mask = Image.new("L", (bw * ss, bh * ss), 0)
    ImageDraw.Draw(mask).polygon([((x - x0) * ss, (y - y0) * ss) for x, y in pts], fill=255)
    mask = mask.resize((bw, bh), Image.Resampling.LANCZOS)
    if isinstance(fill[0], tuple):
        layer = _gradient((bw, bh), fill[0], fill[1])
    else:
        layer = Image.new("RGB", (bw, bh), fill)
    canvas.paste(layer, (x0, y0), mask)


def _brush_pts(x0, y0, x1, y1, rng, rough=5, skew=0, torn_right=False):
    """Paint-brush jaisi khurdari patti ke polygon points."""
    pts = []
    n = max(3, int((x1 - x0) / 34))
    for i in range(n + 1):                                   # upar ka kinara
        pts.append((x0 + (x1 - x0) * i / n, y0 + rng.uniform(-rough, rough)))
    m = max(3, int((y1 - y0) / 13))
    for j in range(1, m + 1):                                # daaya kinara (spiky)
        spike = rng.uniform(-6, 16 if torn_right else 8)
        pts.append((x1 + spike, y0 + (y1 - y0) * j / m))
    for i in range(n, -1, -1):                               # neeche ka kinara
        pts.append((x0 + (x1 - x0) * i / n, y1 + rng.uniform(-rough, rough)))
    for j in range(m - 1, 0, -1):                            # baaya kinara (spiky)
        pts.append((x0 - rng.uniform(-6, 14), y0 + (y1 - y0) * j / m))
    if skew:
        yc, h = (y0 + y1) / 2, max(1, y1 - y0)
        pts = [(x + skew * (yc - y) / h, y) for x, y in pts]
    return pts


def _banner(canvas, box, fill, rng, rough=5, skew=6, torn_right=False, shadow=True):
    x0, y0, x1, y1 = box
    pts = _brush_pts(x0, y0, x1, y1, rng, rough=rough, skew=skew, torn_right=torn_right)
    if shadow:
        _paint_poly(canvas, [(x + 5, y + 6) for x, y in pts], (0, 0, 0))
    _paint_poly(canvas, pts, fill)


def _star_pts(cx, cy, r_out, r_in, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _rounded(canvas, box, radius, fill, outline=None, width=0, ss=3):
    x0, y0, x1, y1 = [int(v) for v in box]
    bw, bh = x1 - x0, y1 - y0
    mask = Image.new("L", (bw * ss, bh * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw * ss - 1, bh * ss - 1), radius * ss, fill=255)
    mask = mask.resize((bw, bh), Image.Resampling.LANCZOS)
    if isinstance(fill[0], tuple):
        layer = _gradient((bw, bh), fill[0], fill[1], vertical=False)
    else:
        layer = Image.new("RGB", (bw, bh), fill)
    canvas.paste(layer, (x0, y0), mask)
    if outline and width:
        ImageDraw.Draw(canvas).rounded_rectangle((x0, y0, x1, y1), radius, outline=outline, width=width)


def _icon(canvas, kind, cx, cy, r):
    """Chhote vector icons (star / tick / bolt / rupee) – safed gole ke andar."""
    d = ImageDraw.Draw(canvas)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE)
    if kind == "star":
        _paint_poly(canvas, _star_pts(cx, cy + 1, r * 0.72, r * 0.3), (255, 170, 0))
    elif kind == "tick":
        d.line([(cx - r * .45, cy + r * .02), (cx - r * .1, cy + r * .38), (cx + r * .5, cy - r * .38)],
               fill=GREEN, width=max(4, int(r * .28)), joint="curve")
    elif kind == "bolt":
        _paint_poly(canvas, [(cx + r * .1, cy - r * .7), (cx - r * .45, cy + r * .1), (cx - r * .02, cy + r * .1),
                             (cx - r * .15, cy + r * .72), (cx + r * .48, cy - r * .12), (cx + r * .04, cy - r * .12)],
                    (240, 130, 0))
    else:
        f = _font(int(r * 1.25))
        d.text((cx, cy), "₹", font=f, fill=(200, 20, 30), anchor="mm")


# ==========================================
# BACKGROUNDS
# ==========================================
def _bokeh(img, rng, n=18, colors=((255, 255, 255),), alpha=(30, 80), rmin=20, rmax=70):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(n):
        r = rng.randint(rmin, rmax)
        x, y = rng.randint(-20, W + 20), rng.randint(-20, H + 20)
        c = rng.choice(colors)
        d.ellipse((x - r, y - r, x + r, y + r), fill=c + (rng.randint(*alpha),))
    layer = layer.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(layer)


def _vignette(img, strength=0.55):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    a = np.clip((d - 0.55) / 0.9, 0, 1) ** 1.6 * strength * 255
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
    img.alpha_composite(layer)


def _bg_room_fallback(rng):
    """Gemini na chale to garam, ghar jaisa background (code se)."""
    img = _gradient((W, H), (246, 232, 214), (214, 180, 146)).convert("RGBA")
    floor_y = int(H * 0.66)
    floor = _gradient((W, H - floor_y), (186, 140, 100), (120, 82, 52)).convert("RGBA")
    img.alpha_composite(floor, (0, floor_y))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle((W - 330, 0, W, floor_y), fill=(255, 250, 235, 150))          # khidki ki roshni
    d.rectangle((40, 90, 300, floor_y - 40), fill=(150, 105, 70, 70))         # shelf jaisa hissa
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(28)))
    _bokeh(img, rng, n=14, colors=((255, 230, 180), (255, 255, 255)), alpha=(40, 90))
    return img


def _gemini_keys():
    keys = [os.getenv(f"GEMINI_API_KEY_{i}", "").strip() for i in (1, 2, 3)]
    return [k for k in keys if k]


def _ai_background(category: str):
    """Gemini se text-free, insaan-free room background. Fail ho to None."""
    if os.getenv("THUMB_AI_BACKGROUND", "true").strip().lower() in ("0", "false", "no", "off"):
        return None
    keys = _gemini_keys()
    if not keys:
        return None
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        print(f"ℹ️ google-genai import nahi hua: {exc}")
        return None

    scene = CATEGORY_SCENES.get(category, "a bright modern living room with plants")
    prompt = (
        f"Photorealistic wide 16:9 background photo of {scene}. Warm cinematic natural light, "
        "softly blurred depth of field, clean uncluttered centre and right side, light cream and warm wood tones. "
        "ABSOLUTELY NO people, NO text, NO letters, NO logos, NO products, NO screens with content."
    )
    model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image").strip()
    models = [model] + (["gemini-2.5-flash-image"] if model != "gemini-2.5-flash-image" else [])
    for model_name in models:
        for key_no, api_key in enumerate(keys, 1):
            try:
                print(f"🎨 Gemini background: model={model_name}, key={key_no}")
                client = genai.Client(api_key=api_key)
                resp = client.models.generate_content(
                    model=model_name, contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(aspect_ratio="16:9")),
                )
                for part in resp.parts:
                    if getattr(part, "inline_data", None) is not None:
                        im = part.as_image().convert("RGB")
                        im = ImageOps.fit(im, (W, H), method=Image.Resampling.LANCZOS)
                        return im.filter(ImageFilter.GaussianBlur(1.5)).convert("RGBA")
            except Exception as exc:
                print(f"⚠️ Gemini background fail ({model_name}, key {key_no}): {exc}")
                time.sleep(1.5)
    return None


def _bg_studio(rng):
    """Style B: upar peela band, neeche halka grey studio (POCO-style)."""
    band_h = 200
    img = _gradient((W, H), (206, 213, 224), (150, 158, 172)).convert("RGBA")
    floor = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(floor).ellipse((-200, 560, W + 200, H + 260), fill=(236, 238, 244, 230))
    img.alpha_composite(floor.filter(ImageFilter.GaussianBlur(30)))
    _bokeh(img, rng, n=10, colors=((255, 255, 255), (190, 215, 255)), alpha=(35, 80), rmin=24, rmax=70)
    band = _gradient((W, band_h), (255, 228, 24), (255, 204, 0)).convert("RGBA")
    img.alpha_composite(band, (0, 0))
    ImageDraw.Draw(img).rectangle((0, band_h, W, band_h + 4), fill=(190, 150, 0, 255))
    return img


def _bg_blue(rng):
    """Style C: gehra neela gradient + neeche lakdi ki table (Motorola-style)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - 820) / 900) ** 2 + ((yy - 300) / 620) ** 2)
    t = np.clip(d, 0, 1)[..., None]
    inner, outer = np.array([20, 120, 255], np.float32), np.array([4, 30, 140], np.float32)
    img = Image.fromarray((inner * (1 - t) + outer * t).astype(np.uint8), "RGB").convert("RGBA")
    _bokeh(img, rng, n=10, colors=((120, 190, 255), (255, 255, 255)), alpha=(25, 60), rmin=20, rmax=60)
    table_y = 648
    table = _gradient((W, H - table_y), (168, 112, 70), (92, 56, 30)).convert("RGBA")
    img.alpha_composite(table, (0, table_y))
    ImageDraw.Draw(img).rectangle((0, table_y, W, table_y + 3), fill=(215, 165, 120, 255))
    return img


# ==========================================
# PRODUCT + FACE
# ==========================================
def _white_bg_cutout(img: Image.Image):
    """Safed background wali product photo se background hatata hai. Fail ho to None."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    scale = min(1.0, 900 / max(w, h))
    if scale < 1:
        rgb = rgb.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        w, h = rgb.size
    marker = (255, 0, 255)
    work = rgb.copy()
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    for s in seeds:
        px = work.getpixel(s)
        if min(px) >= 225 and work.getpixel(s) != marker:
            ImageDraw.floodfill(work, s, marker, thresh=28)
    arr = np.array(work)
    bg = (arr[..., 0] == 255) & (arr[..., 1] == 0) & (arr[..., 2] == 255)
    if bg.mean() < 0.12:                      # background hataya hi nahi gaya (safed nahi tha)
        return None
    alpha = Image.fromarray((~bg * 255).astype(np.uint8), "L")
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    coverage = (np.array(alpha) > 128).mean()
    if coverage < 0.05 or coverage > 0.85:
        return None
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    bbox = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
    return out.crop(bbox) if bbox else None


def _photo_card(img: Image.Image):
    """Cutout na ban sake to photo ko saaf rounded card me dikhata hai."""
    im = img.convert("RGB")
    im.thumbnail((700, 700), Image.Resampling.LANCZOS)
    pad = 12
    card = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card.width - 1, card.height - 1), 30, fill=255)
    card.paste((255, 255, 255, 255), (0, 0), mask)
    inner = Image.new("L", im.size, 0)
    ImageDraw.Draw(inner).rounded_rectangle((0, 0, im.width - 1, im.height - 1), 22, fill=255)
    card.paste(im.convert("RGBA"), (pad, pad), inner)
    return card


def _prepare_product(path):
    if not path or not os.path.isfile(path):
        return None, "none"
    try:
        with Image.open(path) as src:
            src = ImageOps.exif_transpose(src)
            cut = _white_bg_cutout(src)
            if cut is not None:
                return cut, "cutout"
            return _photo_card(src), "card"
    except Exception as exc:
        print(f"⚠️ Product photo process nahi hui: {exc}")
        return None, "none"


def _glow(canvas, cx, cy, rx, ry, color, alpha=150, blur=40):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=color + (alpha,))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def _place_product(canvas, prod, kind, box, outline=True):
    """Product ko box ke andar bada karke, box ke neeche-beech me rakhta hai. (x, y, w, h) lautata hai."""
    bx0, by0, bx1, by1 = box
    bw, bh = bx1 - bx0, by1 - by0
    scale = min(bw / prod.width, bh / prod.height)
    size = (max(2, int(prod.width * scale)), max(2, int(prod.height * scale)))
    p = prod.resize(size, Image.Resampling.LANCZOS)
    x = int(bx0 + (bw - size[0]) / 2)
    y = int(by1 - size[1])
    # zameen par parchhai
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((x - 10, by1 - 18, x + size[0] + 10, by1 + 22), fill=(0, 0, 0, 120))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
    if kind == "cutout" and outline:
        a = p.getchannel("A").filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(1))
        halo = Image.new("RGBA", p.size, (255, 255, 255, 0))
        halo.putalpha(a.point(lambda v: int(v * 0.55)))
        canvas.alpha_composite(halo, (x, y))
    canvas.alpha_composite(p, (x, y))
    return x, y, size[0], size[1]


def _neon_rings(canvas, cx, cy, rx, colors=((60, 120, 255), (150, 70, 255), (255, 70, 200))):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, col in enumerate(colors):
        r = rx * (1 - i * 0.17)
        ry = r * 0.27
        d.ellipse((cx - r, cy - ry, cx + r, cy + ry), outline=col + (255,), width=5)
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(7)))
    canvas.alpha_composite(layer)


def _pick_face(reference_face_path, rng):
    if reference_face_path and os.path.isfile(reference_face_path):
        return reference_face_path
    files = sorted(glob.glob(str(FACES_DIR / "*.png")) + glob.glob(str(FACES_DIR / "*.webp")))
    return rng.choice(files) if files else None


def _place_face(canvas, path, max_h=575, max_w=440, x=-12, bottom=H + 8):
    if not path:
        return None
    try:
        face = Image.open(path).convert("RGBA")
    except Exception as exc:
        print(f"⚠️ Face photo load nahi hui: {exc}")
        return None
    bbox = face.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    if bbox:
        face = face.crop(bbox)
    s = min(max_h / face.height, max_w / face.width)
    face = face.resize((int(face.width * s), int(face.height * s)), Image.Resampling.LANCZOS)
    # photo ka daayan kinara kata hua ho (kapde/ungli seedhi line me kati) to use halka fade kar do
    arr = np.array(face.getchannel("A"))
    if (arr[:, -2] > 128).sum() > 12:
        fade = min(44, face.width // 6)
        ramp = np.ones(face.width, dtype=np.float32)
        ramp[-fade:] = np.linspace(1.0, 0.0, fade)
        arr = (arr.astype(np.float32) * ramp[None, :]).astype(np.uint8)
        face.putalpha(Image.fromarray(arr, "L"))
    fx, fy = x, bottom - face.height
    a = face.getchannel("A")
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", face.size, (0, 0, 0, 0))
    sh.putalpha(a.point(lambda v: int(v * 0.5)))
    shadow.alpha_composite(sh, (fx + 8, fy + 8))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    rim = Image.new("RGBA", face.size, (255, 255, 255, 0))
    rim.putalpha(a.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(1)))
    canvas.alpha_composite(rim, (fx, fy))
    canvas.alpha_composite(face, (fx, fy))
    return fx, fy, face.width, face.height


# ==========================================
# TEXT COPY (Gemini + safe fallback)
# ==========================================
def _default_copy(product, category, specs):
    base = CATEGORY_COPY.get(category, CATEGORY_COPY["gadget"])
    facts = _short_facts(specs)
    badges = []
    icons = ["tick", "bolt", "tick", "bolt"]
    defaults = [("Best", "Features"), ("Value for", "Money"), ("Full", "Review"), ("Honest", "Opinion")]
    for i in range(4):
        badges.append(_split_two_lines(facts[i]) if i < len(facts) else defaults[i])
    checks = (facts + ["पूरा रिव्यू", "असली टेस्ट", "सच्ची राय"])[:3]
    return dict(
        tail=base["tail"], hook=base["hook"], big1=base["big"][0], big2=base["big"][1],
        label=base["label"], slogan_a=base["slogan"][0], slogan_b=base["slogan"][1],
        badges=badges, icons=icons, checks=checks,
    )


def _llm_copy(product, price, category, specs):
    """Gemini se chhota Hindi copy. Sirf supplied facts; kuch bhi invent nahi."""
    keys = _gemini_keys()
    if not keys or os.getenv("THUMB_AI_COPY", "true").strip().lower() in ("0", "false", "no", "off"):
        return None
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return None
    facts = "\n".join(f"- {k}: {v}" for k, v in (specs or {}).items()
                      if v and len(str(v)) <= 100 and "₹" not in str(v))[:900]
    prompt = f"""You write short text for an Indian tech-review YouTube thumbnail.
Product: {product}
Category: {category}
Price: {price or "unknown"}
Verified facts:
{facts or "none"}

Return ONLY JSON with these keys:
"tail": Hindi (Devanagari) 2-3 words, max 16 chars, completes the line "सिर्फ ₹PRICE में ___!" e.g. "स्मार्ट सफाई"
"hook": Hindi (Devanagari) max 24 chars, curiosity line e.g. "खरीदने से पहले देखो!"
"big1": ONE English word, UPPERCASE, max 7 letters
"big2": ONE English word, UPPERCASE, max 9 letters
"label": English product type, UPPERCASE, max 24 chars e.g. "ROBOT VACUUM & MOP"
"slogan_a": Hindi max 14 chars, "slogan_b": Hindi max 12 chars (together a catchy line like "घर को बनाओ" + "स्मार्ट होम!")
"badges": list of 4 objects {{"l1": max 11 chars, "l2": max 11 chars}} — 4 different real features from the verified facts
"checks": list of 3 short strings, max 18 chars each, from the verified facts

RULES: use ONLY the verified facts. Never invent ratings, numbers, awards, warranty or performance claims.
Do not mention price inside badges. Keep everything short and bold."""
    for api_key in keys[:2]:
        try:
            client = genai.Client(api_key=api_key)
            resp = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL_NAME", "gemini-3.6-flash").strip() or "gemini-3.6-flash",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.6),
            )
            raw = (resp.text or "").strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception as exc:
            print(f"⚠️ Gemini thumbnail-copy fail: {exc}")
            time.sleep(1)
    return None


def _build_copy(product, price, category, specs):
    copy = _default_copy(product, category, specs)
    ai = _llm_copy(product, price, category, specs)
    if not ai:
        return copy

    def ok(val, n):
        return isinstance(val, str) and 0 < len(val.strip()) <= n

    for key, n in (("tail", 18), ("hook", 26), ("slogan_a", 16), ("slogan_b", 14)):
        if ok(ai.get(key), n):
            copy[key] = ai[key].strip()
    for key, n in (("big1", 8), ("big2", 10), ("label", 26)):
        v = ai.get(key)
        if ok(v, n) and _is_latin(v):
            copy[key] = v.strip().upper()
    if isinstance(ai.get("badges"), list):
        for i, b in enumerate(ai["badges"][:4]):
            if isinstance(b, dict) and ok(b.get("l1"), 13) and (not b.get("l2") or ok(b.get("l2"), 13)):
                copy["badges"][i] = (b["l1"].strip(), (b.get("l2") or "").strip())
    if isinstance(ai.get("checks"), list):
        for i, c in enumerate(ai["checks"][:3]):
            if ok(c, 20):
                copy["checks"][i] = c.strip()
    return copy


# ==========================================
# STYLE RENDERERS
# ==========================================
def _brand_tag(canvas):
    _rounded(canvas, (12, 12, 262, 66), 14, BLACK, outline=WHITE, width=2)
    d = ImageDraw.Draw(canvas)
    f = _fit_font(d, CHANNEL_NAME.upper(), 218, 30, 26, big=True)
    d.text((137, 39), CHANNEL_NAME.upper(), font=f, fill=WHITE, anchor="mm")


def _centered(d, text, box, color, start, big=False, stroke=3, stroke_fill=BLACK):
    x0, y0, x1, y1 = box
    f = _fit_font(d, text, (x1 - x0) - 2 * stroke - 8, (y1 - y0) - 8, start, big=big)
    d.text(((x0 + x1) / 2, (y0 + y1) / 2 + 1), text, font=f, fill=color, anchor="mm",
           stroke_width=stroke, stroke_fill=stroke_fill)


def _price_runs(price, tail):
    if price:
        return [("सिर्फ ", WHITE), (price, YELLOW), (f" में {tail}!", WHITE)]
    return [(f"{tail}!", YELLOW)]


def render_style_a(canvas, ctx, rng):
    d = ImageDraw.Draw(canvas)
    cp, price, name = ctx["copy"], ctx["price"], ctx["name"]
    # --- top: red headline banner + yellow product-name strip ---
    _banner(canvas, (276, 26, 1040, 118), (RED, DARK_RED), rng, skew=8)
    _draw_runs(d, _price_runs(price, cp["tail"]), 660, 74,
               _fit_runs(d, _price_runs(price, cp["tail"]), 700, 72, 66), stroke=4)
    _banner(canvas, (292, 116, 1030, 176), YELLOW, rng, rough=3, skew=6)
    _centered(d, name, (300, 120, 1022, 172), BLACK, 38, stroke=0)
    # --- centre-left: big words ---
    _banner(canvas, (360, 238, 800, 346), (BLACK, (45, 45, 50)), rng, skew=14)
    _centered(d, cp["big1"], (372, 240, 790, 344), WHITE, 92, big=True, stroke=3, stroke_fill=BLACK)
    _banner(canvas, (336, 350, 790, 448), (RED, DARK_RED), rng, skew=14)
    _centered(d, cp["big2"], (350, 352, 780, 446), WHITE, 82, big=True, stroke=5, stroke_fill=BLACK)
    _banner(canvas, (352, 448, 760, 516), YELLOW, rng, rough=3, skew=10)
    _centered(d, cp["label"], (362, 452, 750, 512), BLACK, 34, stroke=0)
    # --- right: 4 badges ---
    palette = [((120, 50, 200), (170, 70, 230)), ((30, 100, 220), (60, 150, 245)),
               ((20, 160, 70), (60, 200, 100)), ((240, 110, 10), (255, 160, 40))]
    badges = []
    rating = ctx["rating"]
    if rating:
        badges.append((f"{rating} Star", "Rating", "star"))
    for i, (l1, l2) in enumerate(cp["badges"]):
        badges.append((l1, l2, cp["icons"][i % len(cp["icons"])]))
    for i, (l1, l2, ic) in enumerate(badges[:4]):
        y0 = 138 + i * 92
        _rounded(canvas, (1066, y0, 1272, y0 + 78), 22, palette[i], outline=(255, 255, 255), width=3)
        _icon(canvas, ic, 1102, y0 + 39, 20)
        lines = [t for t in (l1, l2) if t]
        f = _fit_font(d, max(lines, key=len), 124, 30, 26)
        if len(lines) == 2:
            d.text((1134, y0 + 24), lines[0], font=f, fill=WHITE, anchor="lm")
            d.text((1134, y0 + 54), lines[1], font=f, fill=WHITE, anchor="lm")
        else:
            d.text((1134, y0 + 39), lines[0], font=f, fill=WHITE, anchor="lm")
    # --- bottom ---
    _banner(canvas, (0, 618, 560, 714), (BLACK, (35, 35, 40)), rng, rough=4, skew=0, torn_right=True)
    runs = [(cp["slogan_a"] + " ", WHITE), (cp["slogan_b"], YELLOW)]
    _draw_runs(d, runs, 280, 668, _fit_runs(d, runs, 500, 64, 52, stroke=0), stroke=0)
    if price:
        _banner(canvas, (650, 636, 1262, 716), (RED, DARK_RED), rng, skew=8)
        runs = [(price, WHITE), (" | ", WHITE), ("Buy Now!", YELLOW)]
        _draw_runs(d, runs, 956, 678, _fit_runs(d, runs, 560, 66, 54), stroke=3)
    else:
        _banner(canvas, (650, 636, 1262, 716), (RED, DARK_RED), rng, skew=8)
        _draw_runs(d, [("Full Review ", WHITE), ("2026", YELLOW)], 956, 678, _font(50), stroke=3)


def _brand_of(name: str):
    """Naam ke pehle shabd se brand aur baaki model nikalta hai."""
    parts = name.split()
    if len(parts) >= 2 and re.fullmatch(r"[A-Za-z][A-Za-z0-9&+-]{1,14}", parts[0]):
        return parts[0], " ".join(parts[1:])
    return "", name


_SPEC_TOKEN = re.compile(r"^\(?\d+\s?(GB|TB)\)?$|^5G$|^4G$|^\(.*\)$", re.I)


def _name_runs(name):
    """Naam me model laal, storage/5G jaise tukde kaale rang me."""
    runs = []
    for tok in name.split():
        color = BLACK if _SPEC_TOKEN.match(tok) else RED
        runs.append((tok + " ", color))
    return runs


def _pill_icon(canvas, kind, cx, cy, r, ring):
    d = ImageDraw.Draw(canvas)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(18, 22, 40), outline=ring, width=4)
    k = r * 0.5
    if kind == "star":
        _paint_poly(canvas, _star_pts(cx, cy + 1, k * 1.2, k * 0.5), (255, 190, 20))
    elif kind == "bolt":
        _paint_poly(canvas, [(cx + k * .2, cy - k * 1.2), (cx - k * .8, cy + k * .2), (cx - k * .05, cy + k * .2),
                             (cx - k * .3, cy + k * 1.2), (cx + k * .85, cy - k * .25), (cx + k * .1, cy - k * .25)],
                    (255, 214, 10))
    elif kind == "rupee":
        d.text((cx, cy), "₹", font=_font(int(r * 1.2)), fill=YELLOW, anchor="mm")
    else:
        d.line([(cx - k * .9, cy), (cx - k * .2, cy + k * .7), (cx + k * .95, cy - k * .7)],
               fill=(70, 230, 110), width=max(4, int(r * .26)), joint="curve")


def render_style_b(canvas, ctx, rng):
    """Peela band + title box + 6 feature capsules (POCO-style)."""
    d = ImageDraw.Draw(canvas)
    cp, price, name = ctx["copy"], ctx["price"], ctx["name"]
    brand, model = _brand_of(name)
    # --- top row ---
    if brand:
        _rounded(canvas, (12, 12, 214, 92), 10, (255, 196, 0), outline=(190, 140, 0), width=2)
        _centered(d, brand.upper(), (18, 16, 208, 88), BLACK, 46, stroke=0)
    title = f"{brand} Review 2026".strip() if brand else "Full Review 2026"
    _rounded(canvas, (236, 14, 946, 106), 14, BLACK)
    _centered(d, title, (248, 18, 934, 102), WHITE, 70, stroke=0)
    _rounded(canvas, (974, 20, 1268, 90), 10, BLACK)
    f = _fit_font(d, CHANNEL_NAME, 270, 40, 36)
    d.text((1121, 55), CHANNEL_NAME, font=f, fill=WHITE, anchor="mm")
    # --- product name (model laal, 5G / storage kaala) ---
    runs = _name_runs(name)
    f = _fit_runs(d, runs, 1180, 78, 84, stroke=0)
    _draw_runs(d, runs, 640, 150, f, stroke=0)
    # --- feature capsules ---
    items = []
    if ctx["rating"]:
        items.append((f"{ctx['rating']} Star", "Rating", "star"))
    for i, (l1, l2) in enumerate(cp["badges"]):
        items.append((l1, l2, cp["icons"][i % len(cp["icons"])]))
    if price:
        items.append((price, "Price in India", "rupee"))
    items = items[:6]
    rings = [(150, 90, 230), (40, 130, 255), (60, 200, 90), (255, 160, 30), (235, 60, 150), (30, 200, 215)]
    n, ph = len(items), 64
    gap = min(12, (418 - n * ph) / max(1, n - 1)) if n > 1 else 0
    for i, (l1, l2, ic) in enumerate(items):
        y0 = 208 + i * (ph + gap)
        _rounded(canvas, (1066, y0, 1270, y0 + ph), 30, ((16, 20, 36), (30, 34, 58)), outline=rings[i % 6], width=3)
        _pill_icon(canvas, ic, 1099, y0 + ph / 2, 23, rings[i % 6])
        f1 = _fit_font(d, l1, 116, 28, 26)
        if l2:
            d.text((1134, y0 + 21), l1, font=f1, fill=WHITE, anchor="lm")
            f2 = _fit_font(d, l2, 116, 24, 20)
            d.text((1134, y0 + 46), l2, font=f2, fill=(200, 206, 225), anchor="lm")
        else:
            d.text((1134, y0 + ph / 2), l1, font=f1, fill=WHITE, anchor="lm")
    # --- bottom texts ---
    d.text((26, 640), "Review & Check:", font=_font(54), fill=YELLOW, anchor="lm", stroke_width=5, stroke_fill=BLACK)
    d.text((26, 692), "Best for 2026?", font=_font(58), fill=WHITE, anchor="lm", stroke_width=5, stroke_fill=BLACK)
    f = _font(60)
    d.text((1000, 676), "CHECK PRICE!" if price else "CHECK HERE!", font=f, fill=RED, anchor="mm",
           stroke_width=5, stroke_fill=WHITE)


def render_style_c(canvas, ctx, rng):
    """Neela background + bada brand naam + peela brush banner + laal strip (Motorola-style)."""
    d = ImageDraw.Draw(canvas)
    cp, price, name = ctx["copy"], ctx["price"], ctx["name"]
    brand, model = _brand_of(name)
    brand_text = (brand or "NEW REVIEW").upper()
    _centered(d, brand_text, (500, 6, 1250, 104), WHITE, 96, big=True, stroke=3, stroke_fill=(10, 30, 110))
    # --- yellow brush banner with model name ---
    _banner(canvas, (470, 108, 1262, 250), YELLOW, rng, rough=9, skew=10)
    _centered(d, model.upper(), (492, 114, 1244, 246), BLACK, 118, big=True, stroke=0)
    # --- red strip: price | storage | rating ---
    parts = []
    if price:
        parts.append(price)
    for fct in _short_facts(ctx["specs"], 6):
        if re.fullmatch(r"\d+\s?(GB|TB)(\s?(SSD|ROM|Storage))?", fct, re.I):
            tag = fct.upper().replace(" ", "")
            core = re.match(r"\d+(?:GB|TB)", tag).group(0)
            if core not in model.upper().replace(" ", ""):      # naam me pehle se ho to dohrana nahi
                parts.append(tag)
            break
    if ctx["rating"]:
        parts.append(f"{ctx['rating']} STAR RATING")
    if not parts:
        parts = ["FULL REVIEW 2026"]
    text = " | ".join(parts[:3])
    _banner(canvas, (560, 244, 1226, 328), (RED, DARK_RED), rng, rough=6, skew=12)
    _centered(d, text, (582, 248, 1206, 324), WHITE, 66, big=False, stroke=3, stroke_fill=BLACK)


# ==========================================
# MAIN GENERATOR
# ==========================================
def generate_youtube_thumbnail(
    product_name: str, price: str = "", specs: dict = None, category: str = None,
    output_path: str = "thumbnail.jpg", reference_face_path: str = None,
    seed: int = None, max_retries: int = 3, product_image_path: str = None,
    style: str = None,
) -> str | None:
    """1280x720 thumbnail banata hai. Kuch bhi fail ho to bhi ek achha thumbnail banta hai."""
    try:
        specs = specs or {}
        rng = random.Random(seed)
        style = (style or os.getenv("THUMB_STYLE", "") or rng.choice(STYLES)).strip().upper()
        if style not in STYLES:
            style = rng.choice(STYLES)
        name = _clean_product_name(product_name)
        category = category or detect_category(product_name, specs)
        price_text = _extract_price(price, specs)
        rating = _find_rating(specs)
        print(f"🎨 Thumbnail style={style}, category={category}, price={price_text or '—'}, rating={rating or '—'}")

        copy = _build_copy(name, price_text, category, specs)
        prod, kind = _prepare_product(product_image_path)
        print(f"🖼️ Product image mode: {kind}")

        # --- background ---
        if style == "A":
            canvas = _ai_background(category) or _bg_room_fallback(rng)
        elif style == "B":
            canvas = _bg_studio(rng)
        else:
            canvas = _bg_blue(rng)
        canvas = canvas.convert("RGBA")
        _vignette(canvas, {"A": 0.35, "B": 0.2, "C": 0.3}[style])

        # --- product ---
        boxes = {"A": (796, 170, 1050, 590), "B": (450, 208, 1050, 630), "C": (690, 338, 1270, 668)}
        glow = {"A": ((255, 240, 200), 120), "B": ((255, 255, 255), 130), "C": ((140, 200, 255), 150)}
        bx = boxes[style]
        gcol, galpha = glow[style]
        _glow(canvas, (bx[0] + bx[2]) // 2, (bx[1] + bx[3]) // 2, (bx[2] - bx[0]) // 2 + 30,
              (bx[3] - bx[1]) // 2 + 10, gcol, galpha, 45)
        if prod is not None:
            if style == "A":
                _neon_rings(canvas, (bx[0] + bx[2]) // 2, bx[3] - 20, 360)
            px, py, pw, ph = _place_product(canvas, prod, kind, bx)

        # --- face ---
        face_path = _pick_face(reference_face_path, rng)
        if style == "C":
            _place_face(canvas, face_path, max_h=660, max_w=480, x=-22)    # C me chehra bada
        elif style == "B":
            _place_face(canvas, face_path, max_h=600, max_w=430)
        else:
            _place_face(canvas, face_path)

        # --- text layers ---
        ctx = dict(copy=copy, price=price_text, name=name, rating=rating, category=category, specs=specs)
        {"A": render_style_a, "B": render_style_b, "C": render_style_c}[style](canvas, ctx, rng)
        if style != "B":                       # B me channel tag upar-daayen already hai
            _brand_tag(canvas)

        out = canvas.convert("RGB")
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        quality = 94
        out.save(output_path, "JPEG", quality=quality, optimize=True)
        while os.path.getsize(output_path) > 1_900_000 and quality > 60:   # YouTube limit 2MB
            quality -= 6
            out.save(output_path, "JPEG", quality=quality, optimize=True)
        print(f"✅ Thumbnail saved: {output_path} ({os.path.getsize(output_path) // 1024} KB)")
        return output_path
    except Exception as exc:
        import traceback
        print(f"❌ Thumbnail generation failed: {exc}\n{traceback.format_exc()[-1500:]}")
        return None


# ==========================================
# Quick test:  python thumbnail_gen.py [photo.jpg] [A|B|C]
# ==========================================
if __name__ == "__main__":
    import sys
    photo = sys.argv[1] if len(sys.argv) > 1 else None
    st = sys.argv[2] if len(sys.argv) > 2 else None
    res = generate_youtube_thumbnail(
        product_name="DREAME L50 Ultra CE Robot Vacuum and Mop",
        price="₹64,999",
        specs={"Rating": "4.2 out of 5", "Station": "All-in-One Auto Station", "Control": "Smart App Control",
               "Type": "Vacuum & Mop"},
        output_path="bot_outputs/test_thumb.jpg", product_image_path=photo, style=st, seed=7,
    )
    print("OK" if res else "FAILED", res or "")
