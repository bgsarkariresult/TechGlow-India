# TechGlow India — Tech Review वीडियो बॉट (GitHub पर ऑटोमैटिक)

यह बिलकुल उसी तरह काम करता है जैसे आपका news automation बॉट — PC/मोबाइल बंद हो तब भी GitHub अपने आप वीडियो बनाकर YouTube पर डाल देगा।

## रिपो में ये फाइलें डालनी हैं
```
tech_review_bot.py
requirements.txt
telegram_check.py
.github/workflows/tech-review-bot.yml
```

## स्टेप 1 — Secrets जोड़ें (Settings → Secrets and variables → Actions)

| Secret Name              | Value                                                    |
|---------------------------|-----------------------------------------------------------|
| `GEMINI_API_KEY_1`         | पहली Gemini key                                          |
| `GEMINI_API_KEY_2`         | दूसरी Gemini key                                         |
| `GEMINI_API_KEY_3`         | तीसरी Gemini key                                         |
| `TELEGRAM_BOT_TOKEN`       | अपने Telegram बॉट का token                               |
| `TELEGRAM_CHAT_ID`         | अपनी chat id                                             |
| `YT_CLIENT_SECRETS_JSON`   | `client_secrets.json` का पूरा raw कंटेंट (जैसा है वैसा)  |
| `YT_TOKEN_JSON`            | `token.json` का पूरा raw कंटेंट (जैसा है वैसा)           |

(अगर आपने news automation वाले बॉट में पहले से Telegram बॉट और YouTube token बना लिए हैं, तो वही दोबारा इस्तेमाल कर सकते हैं — बस secrets इस नए रिपो में भी डालनी होंगी।)

## स्टेप 2 — 2 तरीकों से चलाएं

**GitHub पेज से:** Actions → "TechGlow India - Tech Review Auto Bot" → Run workflow → `article_url` में tech-review वाला लिंक डालें → Run।

**Telegram से:** अपने बॉट को सीधे product review वाले पोस्ट का लिंक भेज दें — 5 मिनट के अंदर अपने आप वीडियो बनना शुरू हो जाएगा।

## जो सुधार किए गए हैं (पुराने बॉट से सीखे गए सबक)
- Gemini की 3 keys अपने आप rotate होती हैं (1 fail हो तो अगली अपने आप try होती है)।
- आवाज़ (TTS) के लिए 3 fallback: OpenAI.fm → Edge TTS → gTTS — तीनों में से एक चलेगी तो वीडियो बनेगा।
- हर स्टेज (script, audio, video, upload) पर सफलता/असफलता Telegram पर आएगी।
- `moviepy==1.0.3` version सोच-समझकर लिखी गई है, क्योंकि नई moviepy 2.x में यह कोड नहीं चलेगा।

## ध्यान रखें
- अगर Telegram पर "Gemini KEY_1/2/3 fail" जैसे मैसेज आएं तो अक्सर वजह **daily free quota (20 requests/day) खत्म होना** होती है — नई key बनाने से कोई फायदा नहीं, अगले दिन तक इंतज़ार करें या हर key अलग Google account से बनाएं।
