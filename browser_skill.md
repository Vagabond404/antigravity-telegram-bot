---
name: autonomous-browser
description: Headless browser automation, web search, DOM/Markdown extraction, and webpage screenshot tool with direct Telegram delivery.
---

# Autonomous Web Browser & Search Skill

This skill provides fast, cross-platform headless browser utilities to search the web, extract clean Markdown from webpages, and capture high-resolution screenshots delivered directly to the user's Telegram chat.

## 🛠️ Available Commands

### 1. 🔍 Instant Web Search
Run a clean web search without requiring an API key:
```bash
python browser_tool.py search "<search query>"
```

### 2. 📄 Webpage Extraction (DOM to Clean Markdown)
Extract the readable content of any webpage as clean Markdown:
```bash
python browser_tool.py fetch <url>
```

### 3. 📸 Webpage Screenshot & Direct Telegram Delivery
Capture a high-resolution PNG screenshot of a webpage and optionally send it straight to Telegram:
```bash
# Save screenshot locally
python browser_tool.py screenshot <url> --out ./tmp/capture.png

# Capture AND send directly to the user's Telegram chat
python browser_tool.py screenshot <url> --send-tg --caption "Live preview of <site>"
```