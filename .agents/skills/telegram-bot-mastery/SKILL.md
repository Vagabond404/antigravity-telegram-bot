---
name: telegram-bot-mastery
description: >-
  Complete operational guide and capability reference for the Antigravity Telegram Agent v4.1.
  Use this skill whenever operating through Telegram, sending files/photos/videos/audio to the user,
  storing or retrieving long-term cross-chat memories (personal info, preferences, projects, infra),
  capturing web screenshots, creating dynamic Telegram slash commands, managing MCP servers/plugins,
  or orchestrating multi-agent subagents.
---

# Antigravity Telegram Agent v4.1 — Complete Mastery Guide

You are powered by **Google Antigravity CLI (`agy`)** and connected in real time to **Telegram** through the **Antigravity Telegram Agent v4.1** gateway. This skill documents all your built-in capabilities and how to use them effectively.

---

## 1. 📤 Bidirectional Multimedia & File Delivery on Telegram (`tg_send.py`)

You can send **any file** (image, chart, screenshot, video, audio, voice note, PDF, ZIP archive, or source file) directly into the user's Telegram chat.

### Direct Delivery Commands
Use the Python interpreter with `tg_send.py`:

```bash
# Auto-detect media format (Photo, Video, Audio, Voice, Animation, or Document)
python tg_send.py --file "/absolute/path/to/file.ext" --caption "Clear description"

# Force a specific media type:
python tg_send.py --photo "/absolute/path/to/image.png" --caption "Generated image"
python tg_send.py --video "/absolute/path/to/video.mp4" --caption "Video preview"
python tg_send.py --audio "/absolute/path/to/audio.mp3" --caption "Audio file"
python tg_send.py --voice "/absolute/path/to/voice.ogg" --caption "Voice note"
python tg_send.py --document "/absolute/path/to/archive.zip" --caption "Project archive"
```

### Important Rules for `tg_send.py`
- **NEVER use `tg_send.py` to send intermediate text status messages** (e.g., "Searching...", "Step 1..."): the Telegram bot already streams your live thoughts, tool calls, and subagents in real time in an animated message bubble.
- **ALWAYS use `tg_send.py --file ...`** whenever you generate or prepare a visual or downloadable deliverable (image, PDF, screenshot, build artifact, export).

---

## 2. 🧠 Proactive Cross-Chat Long-Term Memory (`mem.py` / `memory.db`)

You have a **Hybrid Long-Term Memory Engine (FastEmbed Vector Search + SQLite)** that persists across all conversations, even after `/clear` or a server reboot.

### Official Memory Categories
- `profile`: User identity (name, role, location, devices, skills).
- `preferences`: Coding style, preferred languages/frameworks, communication preferences.
- `projet`: Project details (name, directory path, tech stack, architecture, current status, next steps).
- `infra`: Servers, IP addresses, OS (Armbian, Windows, Linux VPS), Docker containers, ports, services.
- `rules`: Permanent rules and constraints specified by the user.

### Proactive Memory Commands (`mem.py`)
Proactively store any important fact using a unique key (`--key`) so existing entries are cleanly updated (upserted) without creating duplicates:

```bash
# Store or update personal info / preferences / rules / infrastructure
python mem.py add "User operates an Armbian Linux server (192.168.110.200) and a Windows PC." --category infra --key "user_servers" --importance 5

# Store or update project state
python mem.py add "Project MyApp: located in /root/my-app, stack FastAPI + React, authentication completed." --category projet --key "projet_myapp" --importance 5

# Hybrid semantic + keyword search across long-term memory
python mem.py search "MyApp architecture"

# List all active memories (or filter by category)
python mem.py list
python mem.py list --category projet

# Delete an obsolete memory by ID
python mem.py delete 12
```

---

## 3. 🌐 Web Search, Scraping & Live Screenshots (`browser_tool.py` & MCP)

You have multiple tools to interact with the web:

1. **Native Antigravity tools**: `search_web` and `read_url_content`.
2. **Web MCP Servers (when enabled)**:
   - **Playwright MCP (`playwright`)**: Full headless browser automation (clicks, forms, JS SPAs, DOM snapshots).
   - **Firecrawl MCP (`firecrawl`)**: Deep web scraping and clean Markdown extraction.
3. **Built-in `browser_tool.py` utility**:
   ```bash
   # Fast DuckDuckGo web search
   python browser_tool.py search "FastAPI lifespan official documentation"

   # Extract a webpage as clean Markdown
   python browser_tool.py fetch "https://example.com"

   # Capture an HD webpage screenshot and send it directly to Telegram
   python browser_tool.py screenshot "https://example.com" --send-tg --caption "Live website preview"
   ```

---

## 4. 🕹️ Dynamic Telegram Slash Commands (`command_manager.py`)

You can create, list, or remove custom `/slash` commands on Telegram whenever requested by the user. They are automatically synchronized with Telegram's `/` command menu:

```bash
# Create a custom /audit command
python command_manager.py add audit "Audit project security and code quality" "Perform a comprehensive security and code quality audit on: {prompt}" --mode auto-approve --effort high

# List custom commands
python command_manager.py list

# Remove a custom command
python command_manager.py remove audit
```

---

## 5. 🤝 Multi-Agent & Subagent Orchestration (`invoke_subagent`)

When Multi-Agent mode is enabled:
- Use `invoke_subagent` to spawn parallel subagents (`research` for fast codebase/web exploration, `self` for parallel implementation tasks, or custom subagents via `define_subagent`).
- The Telegram interface automatically displays live subagent activity to the user.

---

## 6. 🔌 Antigravity CLI Ecosystem (`agy`), Auto-Update & Self-Healing

You can inspect or manage the Antigravity CLI environment at any time:
- **MCP Servers**: `agy mcp list`, `agy mcp add <name> -- <command>`, `agy mcp enable <name>`, `agy mcp disable <name>`
- **CLI Plugins**: `agy plugin list`, `agy plugin install <name>`
- **AI Models**: `agy models`
- **System Health**: `python server_watchdog.py` (monitors CPU, RAM, Disk, and active services).
