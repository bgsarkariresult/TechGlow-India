import numpy as np

# ==========================================
# PATCH BLOCK A  -> CONFIGURATION section me (MAX_RETRIES ke neeche) paste karo
# ==========================================
HINGLISH_SCRIPT = ""          # AI se aaya Hinglish script yahan store hota hai (captions ke liye)

IMAGE_SCENE_SECONDS = 9.0     # ek image kitni der dikhe
FRAME_W, FRAME_H = 1920, 1080
IMAGE_BOX = (1000, 580)       # image ka max size (width, height)
IMAGE_CENTER_Y = 380          # image ka center (upar se)
CAPTION_TOP_Y = 740           # caption box ka top (image ke neeche, alag)


# ==========================================
# PATCH BLOCK C -> purane make_product_caption_card() aur
#                  build_product_caption_overlays() ki jagah ye paste karo
#                  (extract_product_images, to_hinglish, split_caption_segments waise hi rahenge)
# ==========================================
def _make_views(images):
    """Har photo ke 4 'view': full, center crop, top-left crop, bottom-right crop.
    Order: pehle sab full photos, phir crops -> repeat kam lagta hai."""
    rounds = [[], [], [], []]
    anchors = [None, (0.5, 0.5), (0.15, 0.15), (0.85, 0.85)]
    for i, path in enumerate(images, start=1):
        rounds[0].append(path)
        try:
            with Image.open(path) as src:
                src = src.convert("RGB")
                w, h = src.size
                cw, ch = int(w * 0.7), int(h * 0.7)
                if cw < 400 or ch < 280:
                    continue  # chhoti image ke crop dhundhle dikhenge
                for r in (1, 2, 3):
                    ax, ay = anchors[r]
                    left, top = int((w - cw) * ax), int((h - ch) * ay)
                    p = os.path.join("temp_product_images", f"view_{i:02d}_{r}.jpg")
                    src.crop((left, top, left + cw, top + ch)).save(p, "JPEG", quality=92)
                    rounds[r].append(p)
        except Exception as e:
            print(f"ℹ️ Crop view skipped for image {i}: {e}")
    return [p for rnd in rounds for p in rnd]


def make_zoom_image_clip(image_path, start, duration, zoom_in=True):
    """Product image apne asli size me (koi patti/blur nahi), dheere zoom in ya zoom out."""
    with Image.open(image_path) as src:
        src = src.convert("RGB")
        scale = min(IMAGE_BOX[0] / src.width, IMAGE_BOX[1] / src.height, 1.6)
        size = (max(2, int(src.width * scale)), max(2, int(src.height * scale)))
        fitted = src.resize(size, Image.Resampling.LANCZOS)
    base_w, base_h = fitted.size
    z0, z1 = (1.0, 1.12) if zoom_in else (1.12, 1.0)

    def scale_at(t):
        p = min(1.0, max(0.0, t / max(duration, 0.1)))
        return z0 + (z1 - z0) * p

    clip = ImageClip(np.array(fitted)).set_start(start).set_duration(duration)
    clip = clip.resize(scale_at)
    clip = clip.set_position(lambda t: (
        FRAME_W / 2 - base_w * scale_at(t) / 2,
        IMAGE_CENTER_Y - base_h * scale_at(t) / 2,
    ))
    fade = min(0.4, duration / 4)
    return clip.fadein(fade).fadeout(fade)


def make_caption_box_image(text, index):
    """Image se alag chhota caption box: kaala background, peeli border, safed text."""
    path = os.path.join("temp_product_images", f"caption_box_{index:03d}.png")
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 54)
    except Exception:
        font = ImageFont.load_default()
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    max_text_w = 1500
    lines, line = [], ""
    for word in (text or "").split():
        trial = (line + " " + word).strip()
        if probe.textbbox((0, 0), trial, font=font)[2] > max_text_w and line:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    lines = lines[:2] or [""]
    line_h = 70
    pad_x, pad_y = 48, 24
    text_w = max(probe.textbbox((0, 0), l, font=font)[2] for l in lines)
    box_w, box_h = text_w + 2 * pad_x, len(lines) * line_h + 2 * pad_y
    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, box_w - 1, box_h - 1), radius=24,
                        fill=(5, 9, 18, 235), outline=(250, 204, 21, 255), width=5)
    y = pad_y
    for l in lines:
        w = d.textbbox((0, 0), l, font=font)[2]
        d.text(((box_w - w) / 2, y), l, fill=(255, 255, 255, 255), font=font)
        y += line_h
    img.save(path)
    return path


def build_product_caption_overlays(article_url, script_text, duration, product_title=""):
    """Peeche website scroll (existing). Uske upar:
       - product image (9 sec, zoom in / zoom out alternate, crops se variety)
       - image ke neeche alag Hinglish caption box (apni speed se badalta hai)"""
    images = extract_product_images(article_url, product_title=product_title)
    if not images or duration <= 0:
        return []

    views = _make_views(images)
    overlays = []

    # --- image scenes ---
    n_scenes = max(1, round(duration / IMAGE_SCENE_SECONDS))
    scene_len = duration / n_scenes
    for k in range(n_scenes):
        try:
            overlays.append(make_zoom_image_clip(
                views[k % len(views)], k * scene_len, scene_len, zoom_in=(k % 2 == 0)))
        except Exception as e:
            print(f"ℹ️ Image scene {k + 1} skipped: {e}")

    # --- Hinglish captions (AI wala Hinglish, nahi mila to purana to_hinglish) ---
    caption_source = (HINGLISH_SCRIPT or "").strip() or to_hinglish(script_text)
    segments = split_caption_segments(caption_source, max_words=6)
    if segments:
        weights = [max(1, len(s.split())) for s in segments]
        total = sum(weights)
        start = 0.0
        for i, seg in enumerate(segments):
            seg_dur = duration * weights[i] / total
            if i == len(segments) - 1:
                seg_dur = max(0.05, duration - start)
            try:
                p = make_caption_box_image(seg, i + 1)
                c = ImageClip(p).set_start(start).set_duration(seg_dur)
                c = c.set_position(("center", CAPTION_TOP_Y))
                if seg_dur > 0.5:
                    c = c.fadein(0.12)
                overlays.append(c)
            except Exception as e:
                print(f"ℹ️ Caption {i + 1} skipped: {e}")
            start += seg_dur

    print(f"🎬 Added {len(overlays)} overlay clips (zoom images + Hinglish captions).")
    return overlays


# ==========================================
# PATCH BLOCK B -> generate_youtube_assets_tech() me 3 chhote badlav
# ==========================================
# B1) function ki pehli line (def ke neeche) me ye add karo:
#         global HINGLISH_SCRIPT
#         HINGLISH_SCRIPT = ""
#
# B2) base_prompt ke OUTPUT FORMAT JSON me "video_script" ke baad ye line add karo:
#         "hinglish_script": "Exactly the same script as video_script, same sentences and order, but written in natural Hinglish using Roman letters. Keep English words (product names, German engineering, battery, display, price) in normal English spelling. No Devanagari.",
#
# B3) dono jagah (Gemini loop aur gpt-4o-mini loop) jahan ye line hai:
#         if json_data and "video_script" in json_data:
#     uske theek neeche (andar) ye add karo:
#         HINGLISH_SCRIPT = json_data.get("hinglish_script", "") or ""
