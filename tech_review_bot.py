import os
import re
import json
import time
import asyncio
import requests
import subprocess
from bs4 import BeautifulSoup
from g4f.client import Client
import edge_tts
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont

# PATCH: Fix moviepy ANTIALIAS issue
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from moviepy.editor import ImageClip, AudioFileClip, VideoFileClip
from playwright.sync_api import sync_playwright

# Google API Imports
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==========================================
# CONFIGURATION
# ==========================================
GEMINI_API_KEYS = [
    os.getenv("GEMINI_API_KEY_1", "").strip(),
    os.getenv("GEMINI_API_KEY_2", "").strip(),
    os.getenv("GEMINI_API_KEY_3", "").strip(),
]
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]  # sirf khali nahi wale keys

if not GEMINI_API_KEYS:
    print("⚠️ Warning: Koi bhi GEMINI_API_KEY_1/2/3 nahi mila. GitHub Secrets check karo!")

# Har key ke liye ek client bana lo (g4f k through), 1 fail ho to agla try hoga
GEMINI_CLIENTS = []
for idx, key in enumerate(GEMINI_API_KEYS, start=1):
    try:
        GEMINI_CLIENTS.append((f"KEY_{idx}", Client(api_key=key)))
    except Exception as e:
        print(f"⚠️ GEMINI_API_KEY_{idx} se client banane me error: {e}")

# Free/no-key fallback client (gpt-4o-mini ke liye)
fallback_client = Client()

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
MAX_CHUNK_CHARACTERS = 1000
MAX_RETRIES = 3

# ==========================================
# Telegram Notifier — status + errors dono bhejta hai
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def notify_telegram(message: str):
    """GitHub Actions ke runner se seedha Telegram par message bhejta hai.
    Agar token/chat id set nahi hai to chup-chaap skip karega (crash nahi karega)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }, timeout=20)
    except Exception as e:
        print(f"⚠️ Telegram notify failed: {e}")

# ==========================================
# YOUTUBE AUTH
# ==========================================
def get_youtube_service():
    creds = None
    token_file = 'token.json'
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('client_secrets.json'):
                print("❌ 'client_secrets.json' missing.")
                notify_telegram("❌ 'client_secrets.json' missing hai, YouTube upload skip ho gaya.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

# ==========================================
# TECH REVIEW SCRAPER
# ==========================================
def extract_tech_review_content(url):
    print(f"🔍 Scraping Tech Review from: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        title = (
            soup.find('h1') or
            soup.find('h3', class_='post-title') or
            soup.find('h2') or
            soup.find('title')
        )
        title_text = title.get_text(strip=True) if title else "Tech Review Product"

        if '|' in title_text:
            title_text = title_text.split('|')[0].strip()
        elif '-' in title_text and len(title_text) > 40:
            title_text = title_text.split('-')[0].strip()

        body = (
            soup.find('div', class_='post-body') or
            soup.find('article') or
            soup.find('main') or
            soup.find('div', id='content') or
            soup.find('body')
        )

        content_text = ""
        specs = {}

        if body:
            for tag in body(['script', 'style', 'header', 'footer', 'nav', 'noscript', 'form']):
                tag.decompose()

            paragraphs = [p.get_text(strip=True) for p in body.find_all(['p', 'li', 'h2', 'h3', 'td', 'span']) if len(p.get_text(strip=True)) > 15]
            content_text = "\n".join(paragraphs)

            if len(content_text.strip()) < 100:
                content_text = body.get_text(separator=' ', strip=True)

            for p in body.find_all(['p', 'div', 'li', 'td', 'tr', 'span']):
                text = p.get_text(strip=True)
                if not text:
                    continue
                if ('Price' in text or '₹' in text or 'Rs' in text) and 'price' not in specs:
                    specs['price'] = text
                if ('Rating' in text or '★' in text) and 'rating' not in specs:
                    specs['rating'] = text
                if ('Battery' in text or 'mAh' in text or 'Playback' in text or 'Hours' in text) and 'battery' not in specs:
                    specs['battery'] = text
                if ('Pros' in text or 'Fayde' in text or 'Good' in text) and 'pros' not in specs:
                    specs['pros'] = text
                if ('Cons' in text or 'Kamiya' in text or 'Bad' in text) and 'cons' not in specs:
                    specs['cons'] = text
                if ('Driver' in text or 'Watt' in text or 'W' in text or 'Sound' in text) and 'audio' not in specs:
                    specs['audio'] = text

        if not content_text or len(content_text.strip()) < 50:
            print("⚠️ Warning: Extracted content is extremely short.")
            return None, None, None

        print(f"✅ Tech Review extracted successfully! ({len(content_text)} chars)")
        return title_text, content_text[:4000], specs
    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        return None, None, None

# ==========================================
# AI GENERATOR (Primary: gemini-3.6-flash → Fallback: gpt-4o-mini)
# ==========================================
def _parse_ai_json(raw_text):
    """AI response se JSON nikalta hai — ```json fence, raw {..}, ya plain text teeno tarah try karta hai."""
    json_data = None
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', raw_text)
    if json_match:
        try:
            json_data = json.loads(json_match.group(1))
        except Exception:
            pass
    if not json_data:
        json_match = re.search(r'\{[\s\S]*\}', raw_text)
        if json_match:
            try:
                json_data = json.loads(json_match.group())
            except Exception:
                pass
    if not json_data:
        try:
            json_data = json.loads(raw_text)
        except Exception:
            pass
    return json_data


def generate_youtube_assets_tech(title, content, specs, max_retries=3):
    print("🤖 Generating Tech Review YouTube Assets...")

    specs_text = "\n".join([f"- {k}: {v}" for k, v in specs.items() if v])
    product_name = title.split(':')[0] if ':' in title else title[:30]

    price = "₹2,699"
    for key, value in specs.items():
        if 'price' in key.lower() or '₹' in str(value):
            price_match = re.search(r'₹[\d,]+', str(value))
            if price_match:
                price = price_match.group()
                break

    # Updated stronger clickbait titles + engaging style
    base_prompt = f"""
You are a professional Tech Reviewer for YouTube channel 'TechGlow India'.

Create content for a YouTube video based on this Tech Review Blog Post:

PRODUCT NAME: {product_name}
TITLE: {title}
PRICE: {price}

SPECIFICATIONS:
{specs_text}

BLOG CONTENT:
{content}

CRITICAL RULES:
1. SEO TITLES must be HIGHLY CLICKBAIT (use 🔥, urgency, curiosity, shock, FOMO, "Don't Buy Before Watching", "Real Test", "Honest Truth" etc.)
2. VIDEO SCRIPT:
   - ALWAYS start with a STRONG, UNIQUE, ENGAGING HOOK (problem, shock, curiosity, urgency) — NEVER start with "नमस्ते दोस्तों" or generic greetings
   - Every video must have a DIFFERENT style of hook
   - Pure DEVANAGARI HINDI only
   - Total words: 500-750 (3-5 minute video)
   - Highly conversational, natural, energetic and engaging throughout
3. Make description, tags and hashtags also engaging and SEO-friendly

OUTPUT FORMAT (Strictly valid JSON only):
{{
  "seo_title": [
    "🔥 {product_name} Review 2026: खरीदने से पहले ये वीडियो ज़रूर देखो!",
    "{product_name} - मत खरीदो जब तक ये Review ना देख लो | Real Test",
    "सिर्फ {price} में इतना कुछ? {product_name} Full Honest Review"
  ],
  "video_script": "Complete script in pure Devanagari Hindi starting with a powerful unique hook",
  "seo_description": "SEO optimized engaging description",
  "tags": ["tag1", "tag2", "tag3"],
  "hashtags": "#hashtag1 #hashtag2 #hashtag3"
}}
"""

    # Step 1: Gemini — 3 KEY ROTATION
    for key_label, gclient in GEMINI_CLIENTS:
        for attempt in range(1, max_retries + 1):
            try:
                print(f"🔄 AI Attempt {attempt}/{max_retries} with gemini-3.6-flash ({key_label})...")

                response = gclient.chat.completions.create(
                    model="gemini-3.6-flash",
                    messages=[{"role": "user", "content": base_prompt}],
                    temperature=0.85
                )

                json_data = _parse_ai_json(response.choices[0].message.content.strip())

                if json_data and "video_script" in json_data:
                    print(f"✅ Successfully generated with {key_label} (gemini-3.6-flash)")
                    return json_data

            except Exception as e:
                print(f"⚠️ Attempt {attempt} with {key_label} (gemini-3.6-flash) failed: {e}")
                time.sleep(1.5)

        print(f"➡️ {key_label} fail ho gayi, agli key try kar rahe hain (agar available ho)...")
        notify_telegram(f"⚠️ Gemini {key_label} fail ho gayi, agli key try ho rahi hai...")

    # Step 2: Fallback model (free client, no key) — gpt-4o-mini
    print("🧠 Trying model: gpt-4o-mini (Fallback)")
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🔄 AI Attempt {attempt}/{max_retries} with gpt-4o-mini...")
            response = fallback_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": base_prompt}],
                temperature=0.85
            )
            json_data = _parse_ai_json(response.choices[0].message.content.strip())
            if json_data and "video_script" in json_data:
                print("✅ Successfully generated with gpt-4o-mini")
                return json_data
        except Exception as e:
            print(f"⚠️ Attempt {attempt} with gpt-4o-mini failed: {e}")
            time.sleep(1.5)

    print("❌ All AI models failed. Using emergency fallback data...")
    notify_telegram("❌ Script generation fail ho gaya (Gemini 3 keys + gpt-4o-mini dono fail), emergency fallback text use ho raha hai.")
    return {
        "seo_title": [
            f"🔥 {product_name} Review 2026: खरीदने से पहले ये वीडियो ज़रूर देखो!",
            f"{product_name} - मत खरीदो जब तक ये Review ना देख लो | Real Test",
            f"सिर्फ {price} में इतना कुछ? {product_name} Full Honest Review"
        ],
        "video_script": f"क्या आपको भी {product_name} खरीदने से पहले डर लगता है कि पैसा बर्बाद हो जाएगा? आज के वीडियो में हम इसकी पूरी सच्चाई खोलकर रख देंगे। कीमत, बैटरी, साउंड क्वालिटी और असली रिव्यू — सब कुछ बिना किसी लापरवाही के।",
        "seo_description": f"Complete honest review of {product_name}. Price, features, pros & cons. Watch before you buy!",
        "tags": ["Tech Review", product_name, "Honest Review", "2026"],
        "hashtags": f"#TechReview #{product_name.replace(' ', '')} #HonestReview #TechGlowIndia"
    }

# ==========================================
# SMART SCRIPT SPLITTER (Strict 1000 Chars Limit)
# ==========================================
def split_script_into_chunks(script, max_chars=MAX_CHUNK_CHARACTERS):
    paragraphs = [p.strip() for p in script.split('\n\n') if p.strip()]
    chunks = []
    current_chunk = ""

    for p in paragraphs:
        if len(current_chunk) + len(p) + 2 <= max_chars:
            current_chunk += (p + "\n\n")
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            if len(p) > max_chars:
                sentences = re.split(r'([।!?\n])', p)
                sub_chunk = ""
                for i in range(0, len(sentences), 2):
                    sentence = sentences[i]
                    punct = sentences[i+1] if i+1 < len(sentences) else ""
                    full_sentence = sentence + punct

                    if len(sub_chunk) + len(full_sentence) <= max_chars:
                        sub_chunk += full_sentence
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk.strip())
                        sub_chunk = full_sentence
                if sub_chunk:
                    chunks.append(sub_chunk.strip())
            else:
                current_chunk = p + "\n\n"

    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

# ==========================================
# VOICE GENERATOR (OpenAI.fm + Edge TTS Fallback)
# ==========================================
def generate_fable_voice_openai_fm(text_chunk, output_path):
    try:
        url = "https://www.openai.fm/api/generate"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Origin": "https://www.openai.fm",
            "Referer": "https://www.openai.fm/",
            "Accept": "*/*",
        }

        files = {
            "input": (None, text_chunk),
            "voice": (None, "fable"),
            "prompt": (None, "Speak clearly in a natural, friendly Indian Hindi male tone. Moderate pace, clear pronunciation."),
            "vibe": (None, "audio")
        }

        response = requests.post(url, files=files, headers=headers, timeout=90, stream=True)

        if response.status_code != 200:
            params = {
                "input": text_chunk,
                "voice": "fable",
                "prompt": "Speak clearly in a natural, friendly Indian Hindi male tone. Moderate pace, clear pronunciation."
            }
            response = requests.get(url, params=params, headers=headers, timeout=90, stream=True)

        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        if "audio" not in content_type and "mpeg" not in content_type and "wav" not in content_type and "octet-stream" not in content_type:
            raise Exception(f"Unexpected content-type: {content_type}")

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size = os.path.getsize(output_path)
        if file_size < 8000:
            raise Exception(f"Downloaded audio too small ({file_size} bytes) — incomplete response")

        return True

    except Exception as e:
        print(f"⚠️ OpenAI.fm Direct API Error: {e}")
        return False

def generate_edge_tts_voice(text, output_audio_path):
    voice = "hi-IN-MadhurNeural"

    async def _save():
        communicate = edge_tts.Communicate(text, voice, rate="+10%")
        await communicate.save(output_audio_path)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_save())
    loop.close()

def generate_male_voice(text, output_audio_path):
    print("🎙️ Generating Hindi Voiceover (OpenAI.fm Fable + Edge TTS Fallback)...")
    temp_dir = "temp_voice"
    os.makedirs(temp_dir, exist_ok=True)

    chunks = split_script_into_chunks(text, max_chars=MAX_CHUNK_CHARACTERS)
    print(f"🧩 Script split into {len(chunks)} part(s) [Limit: {MAX_CHUNK_CHARACTERS} chars/part].")

    audio_parts = []
    fable_failed = False

    for idx, chunk in enumerate(chunks, start=1):
        part_filename = os.path.join(temp_dir, f"part_{idx:03d}.mp3")
        success = False

        if not fable_failed:
            for attempt in range(1, MAX_RETRIES + 1):
                print(f"🎙️ Generating Part {idx}/{len(chunks)} ({len(chunk)} chars) with OpenAI.fm (Fable Voice) - Attempt {attempt}...")
                if generate_fable_voice_openai_fm(chunk, part_filename):
                    if os.path.getsize(part_filename) >= 8000:
                        success = True
                        break
                    else:
                        print(f"⚠️ Part {idx} file too small after download. Retrying...")
                time.sleep(2)

            if not success:
                print("⚠️ OpenAI.fm voice generation failed. Falling back to Edge TTS (hi-IN-MadhurNeural).")
                fable_failed = True

        if fable_failed or not success:
            try:
                print(f"🔊 Generating Part {idx}/{len(chunks)} via Edge TTS Fallback...")
                generate_edge_tts_voice(chunk, part_filename)
                if os.path.exists(part_filename) and os.path.getsize(part_filename) >= 4000:
                    success = True
                else:
                    raise Exception("Edge TTS ne khali/chhoti audio di")
            except Exception as e:
                print(f"⚠️ Edge TTS Part {idx} fail ({e}). Ab gTTS (Google) try kar rahe hain...")
                try:
                    tts = gTTS(text=chunk, lang="hi")
                    tts.save(part_filename)
                    if os.path.exists(part_filename) and os.path.getsize(part_filename) >= 4000:
                        success = True
                        print(f"✅ Part {idx} gTTS se ban gaya.")
                    else:
                        raise Exception("gTTS ne bhi khali/chhoti audio di")
                except Exception as e2:
                    print(f"❌ Part {idx} generation completely failed (OpenAI.fm + Edge TTS + gTTS teeno fail): {e2}")
                    notify_telegram(f"❌ Awaaz (TTS) fail ho gayi — OpenAI.fm, Edge TTS aur gTTS teeno fail (Part {idx}).")
                    return False

        audio_parts.append(part_filename)

    if audio_parts:
        print("🔗 Concatenating and Merging All Audio Parts sequentially...")
        list_file = os.path.join(temp_dir, "concat_list.txt")

        with open(list_file, "w", encoding="utf-8") as f:
            for p in audio_parts:
                clean_p = os.path.abspath(p).replace('\\', '/')
                f.write(f"file '{clean_p}'\n")

        try:
            cmd_concat = [
                'ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file,
                '-af', 'loudnorm=I=-16:LRA=11:TP=-1.5',
                '-ar', '44100',
                '-ac', '2',
                '-b:a', '128k',
                '-c:a', 'libmp3lame',
                '-write_xing', '0',
                '-y', output_audio_path
            ]
            subprocess.run(cmd_concat, capture_output=True, check=True)
            print(f"🔊 Final Audio merged successfully: {output_audio_path}")
        except Exception as e:
            print(f"❌ Audio Joining Error: {e}")
            notify_telegram(f"❌ Audio joining (ffmpeg) fail ho gaya: {e}")
            return False
        finally:
            for f in audio_parts + [list_file]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass

    return os.path.exists(output_audio_path)

# ==========================================
# WEBSITE RECORDER
# ==========================================
def record_website_video(url, output_clip_path, target_duration):
    print(f"📹 Recording Website for {target_duration:.1f}s...")
    temp_dir = "temp_rec"
    os.makedirs(temp_dir, exist_ok=True)

    keywords_to_highlight = [
        "Price", "₹", "Rating", "Camera", "Battery", "Display", "Review",
        "Pros", "Cons", "Verdict", "Buy", "Features", "Audio"
    ]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                record_video_dir=temp_dir,
                record_video_size={'width': 1920, 'height': 1080}
            )

            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            try:
                page.wait_for_selector('h1, h2, h3, .post-body, article', timeout=30000)
            except:
                pass

            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(3)

            # Zoom set to 1.7x
            page.evaluate("document.body.style.zoom = '1.7'")
            time.sleep(1)

            js_code = """
            (keywords) => {
                keywords.forEach(kw => {
                    const regex = new RegExp(`(${kw})`, 'gi');
                    const elements = document.querySelectorAll('p, li, span, td, h1, h2, h3, div, a, strong');
                    elements.forEach(el => {
                        if (el.children.length === 0 && el.innerText && regex.test(el.innerText)) {
                            el.innerHTML = el.innerText.replace(
                                regex,
                                '$1'
                            );
                        }
                    });
                });
            }
            """
            page.evaluate(js_code, keywords_to_highlight)
            time.sleep(1)

            start_time = time.time()
            max_duration = min(target_duration, 300)

            page_height = page.evaluate("document.body.scrollHeight")
            viewport_height = page.evaluate("window.innerHeight")
            total_scroll = page_height - viewport_height

            current_scroll = 0
            direction = 1

            while time.time() - start_time < max_duration:
                current_scroll += direction * 2

                if current_scroll > total_scroll:
                    current_scroll = total_scroll
                    direction = -1
                elif current_scroll < 0:
                    current_scroll = 0
                    direction = 1

                page.evaluate(f"window.scrollTo({{ top: {current_scroll}, behavior: 'auto' }})")
                time.sleep(0.05)

            rec_path = page.video.path()
            context.close()
            browser.close()

            if os.path.exists(rec_path):
                if os.path.exists(output_clip_path):
                    os.remove(output_clip_path)
                os.rename(rec_path, output_clip_path)
                return True
    except Exception as e:
        print(f"⚠️ Recording Error: {e}")
        return False

# ==========================================
# VIDEO CREATOR & COMPRESSOR
# ==========================================
def compress_video_1080p(input_path, output_path, target_size_mb=95):
    current_size = os.path.getsize(input_path) / (1024 * 1024)
    if current_size <= target_size_mb:
        return ensure_1080p_16x9(input_path, output_path)

    video_clip = VideoFileClip(input_path)
    duration = video_clip.duration
    video_clip.close()

    target_bitrate = (target_size_mb * 8 * 1024 * 1024 * 0.9) / duration
    target_bitrate_kbps = max(int(target_bitrate / 1000), 500)

    temp_compressed = output_path.replace('.mp4', '_compressed.mp4')

    try:
        video = VideoFileClip(input_path)
        video = video.resize(newsize=(1920, 1080))
        video.write_videofile(
            temp_compressed, fps=24, codec='libx264', audio_codec='aac',
            bitrate=f"{target_bitrate_kbps}k", audio_bitrate='64k',
            verbose=False, logger=None, threads=4, preset='medium'
        )
        video.close()

        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_compressed, output_path)
        return output_path
    except Exception as e:
        print(f"⚠️ Compression error: {e}")
        return ensure_1080p_16x9(input_path, output_path)

def ensure_1080p_16x9(input_path, output_path):
    try:
        video = VideoFileClip(input_path)
        if video.size != (1920, 1080):
            video = video.resize(newsize=(1920, 1080))
        video.write_videofile(
            output_path, fps=24, codec='libx264', audio_codec='aac',
            bitrate='2000k', audio_bitrate='128k', verbose=False, logger=None
        )
        video.close()
        return output_path
    except Exception as e:
        return input_path

def create_video(audio_path, post_url, video_title, output_video_path):
    temp_img_path = "temp_frame_1080p.png"
    web_clip_path = "temp_website_clip.mp4"
    temp_video_path = output_video_path.replace('.mp4', '_temp.mp4')

    try:
        audio = AudioFileClip(audio_path)
        duration = min(audio.duration, 300)
        if audio.duration > 300:
            audio = audio.subclip(0, 300)

        record_success = record_website_video(post_url, web_clip_path, duration)

        if record_success and os.path.exists(web_clip_path):
            bg_video = VideoFileClip(web_clip_path)
            if bg_video.size != (1920, 1080):
                bg_video = bg_video.resize(newsize=(1920, 1080))
            if bg_video.duration < duration:
                bg_video = bg_video.loop(duration=duration)
            else:
                bg_video = bg_video.subclip(0, duration)
            final_video = bg_video.set_audio(audio)
        else:
            img = Image.new('RGB', (1920, 1080), color=(15, 23, 42))
            draw = ImageDraw.Draw(img)
            draw.rectangle([(60, 50), (1860, 1030)], outline=(234, 179, 8), width=5)
            img.save(temp_img_path)
            final_video = ImageClip(temp_img_path).set_duration(duration).set_audio(audio)

        final_video.write_videofile(
            temp_video_path, fps=24, codec='libx264', audio_codec='aac',
            verbose=False, logger=None
        )

        final_video.close()
        audio.close()

        compressed_path = compress_video_1080p(temp_video_path, output_video_path, target_size_mb=95)
        if os.path.exists(temp_video_path) and temp_video_path != compressed_path:
            os.remove(temp_video_path)
        return True
    except Exception as e:
        print(f"❌ Video Error: {e}")
        return False

# ==========================================
# YOUTUBE UPLOADER
# ==========================================
def upload_to_youtube(video_path, title, description, tags):
    print("📤 Uploading to YouTube...")
    youtube = get_youtube_service()
    if not youtube:
        print("⚠️ Upload Skipped.")
        return None

    tags_list = tags if isinstance(tags, list) else tags.split(',')
    body = {
        'snippet': {
            'title': title[:100],
            'description': description[:5000],
            'tags': [t.strip() for t in tags_list[:20]],
            'categoryId': '28'
        },
        'status': {
            'privacyStatus': 'unlisted',
            'selfDeclaredMadeForKids': False
        }
    }
    try:
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
        video_id = response.get('id')
        video_url = f"https://youtu.be/{video_id}"
        print(f"✅ Uploaded! {video_url}")
        notify_telegram(f"✅ <b>Video ban kar YouTube pe upload ho gaya!</b>\n🎬 {title}\n🔗 {video_url}")
        return video_url
    except Exception as e:
        print(f"❌ Upload Failed: {e}")
        notify_telegram(f"❌ <b>YouTube upload fail</b> ho gaya.\n<code>{e}</code>")
        return None

# ==========================================
# MAIN FUNCTION
# ==========================================
def main():
    print("=" * 50)
    print("🚀 TechGlow India - Tech Review Auto Bot")
    print("=" * 50)

    import sys
    post_url = os.getenv("ARTICLE_URL", "").strip()
    if not post_url and len(sys.argv) > 1:
        post_url = sys.argv[1].strip()
    if not post_url:
        post_url = input("\n🔗 Enter Tech Review Post URL: ").strip()
    if not post_url:
        notify_telegram("⚠️ Koi article URL provide nahi hui.")
        return

    notify_telegram(f"🚀 <b>Tech review video automation shuru hua</b>\n🔗 {post_url}")

    blog_title, blog_content, specs = extract_tech_review_content(post_url)
    if not blog_content:
        notify_telegram(f"❌ Article scrape fail/short content.\n🔗 {post_url}")
        return

    ai_data = generate_youtube_assets_tech(blog_title, blog_content, specs)
    if not ai_data:
        notify_telegram("❌ AI script generation fail ho gaya, video nahi banaya.")
        return

    output_dir = "bot_outputs"
    os.makedirs(output_dir, exist_ok=True)

    filename_base = re.sub(r'[^\w\s-]', '', blog_title)[:30].strip().replace(" ", "_")
    txt_file = os.path.join(output_dir, f"{filename_base}_package.txt")
    audio_file = os.path.join(output_dir, f"{filename_base}_audio.mp3")
    video_file = os.path.join(output_dir, f"{filename_base}_video.mp4")

    titles = ai_data.get("seo_title", [])
    selected_title = titles[0] if isinstance(titles, list) and titles else blog_title

    seo_desc = f"{ai_data.get('seo_description', '')}\n\n{ai_data.get('hashtags', '')}"
    tags = ai_data.get("tags", [])

    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("=== TECH REVIEW CONTENT PACKAGE ===\n\n")
        f.write(f"SELECTED TITLE: {selected_title}\n\n")
        f.write("--- SPECIFICATIONS ---\n")
        for k, v in specs.items():
            f.write(f"{k}: {v}\n")
        f.write("\n--- SCRIPT ---\n")
        f.write(f"{ai_data.get('video_script')}\n\n")
        f.write("--- SEO DESCRIPTION ---\n")
        f.write(f"{seo_desc}\n\n")

    print(f"🎉 Package Saved: {txt_file}")

    script_text = ai_data.get("video_script", "")
    audio_ok = generate_male_voice(script_text, audio_file)

    if not audio_ok or not os.path.exists(audio_file):
        print("⚠️ Automation ruk gaya: audio nahi ban paayi.")
        return

    video_created = create_video(audio_file, post_url, selected_title, video_file)
    if not video_created or not os.path.exists(video_file):
        notify_telegram("❌ Video build fail ho gaya, YouTube upload skip.")
        return

    video_url = upload_to_youtube(video_file, selected_title, seo_desc, tags)

    print("\n✅ Process Finished!")
    if video_url:
        print(f"📹 YouTube: {video_url}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        err_text = traceback.format_exc()[-2500:]
        print(f"❌ FATAL ERROR: {e}\n{err_text}")
        notify_telegram(f"❌ <b>Automation CRASH ho gaya</b>\n<code>{e}</code>")
        raise
