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

## 2. 🧠 Proactive Long-Term Memory, Person Profiles & Social Graph (`mem.py` / `memory.db`)

You have a **Deep Hybrid Long-Term Memory Engine (FastEmbed Vector Search + SQLite + Social Graph)** that persists across all conversations, reboots, and `/clear`.

### A. Person Profiles & Speech Tone Engine (`mem.py person`)
Store people's roles, relationship with the user, and **explicit rules on how you should talk to them** (tutoiement vs vouvoiement, tone, formal vs casual):

```bash
# Register or update a person profile with tone instructions
python mem.py person add "Ange" --role "Créateur & Admin Principal" --relation "Propriétaire" --tone "Tutoiement direct, concis, amical et technique" --aliases "ange,admin"

python mem.py person add "Sophie" --role "Partenaire Commerciale" --relation "Cliente" --tone "Vouvoiement très courtois, poli et professionnel"

# Add specific facts to a person's profile
python mem.py person fact "Ange" "Préfère les réponses directes sans politesses superflues."

# Consult a person's profile
python mem.py person get "Ange"

# List all known people
python mem.py person list
```

### B. Social Graph & Interpersonal Connections (`mem.py relate`)
Track relationships and connections between different people:

```bash
# Register a relationship
python mem.py relate "Ange" "associé" "Marc" --details "Co-fondateurs du projet X"
python mem.py relate "Marc" "collègue" "Sophie"

# List relationships
python mem.py relate list
```

### C. General Memory Categories & Facts (`mem.py add`)
- `profile`: User identity (name, role, location, devices, skills).
- `preferences`: Coding style, preferred languages/frameworks, communication preferences.
- `projet`: Project details (name, directory path, tech stack, architecture, current status, next steps).
- `infra`: Servers, IP addresses, OS (Armbian, Windows, Linux VPS), Docker containers, ports, services.
- `rules`: Permanent rules and constraints specified by the user.

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

## 3. ⏰ Native Scheduled Tasks & Autonomous Automations (`tasks.py` / `scheduled_tasks.db`)

You can **natively schedule one-shot timers and recurring automations** at any time. A persistent background worker runs inside the bot, executes the action when due, and reports the results directly to Telegram:

```bash
# Schedule an AI prompt execution in 30 minutes
python tasks.py add "Scanne les logs système et préviens Ange si anomalie" --when "in 30m" --name "scan_logs"

# Schedule a recurring prompt every 2 hours
python tasks.py add "Vérifie l'état des conteneurs Docker et envoie un statut" --when "every 2h" --name "docker_health"

# Schedule a daily morning briefing at 09:00
python tasks.py add "Fais un résumé des actualités IA et des tâches du jour" --when "09:00" --name "morning_brief"

# Schedule a pure reminder message
python tasks.py add "Prendre les médicaments" --when "20:00" --type reminder --name "med_reminder"

# Schedule a direct shell command execution
python tasks.py add "git pull && systemctl restart my-service" --when "in 1h" --type command --name "deploy_update"

# List all scheduled tasks
python tasks.py list

# Manage tasks (pause, resume, remove)
python tasks.py pause 3
python tasks.py resume 3
python tasks.py remove 3
```

The user can also view and control tasks in Telegram with `/tasks` or quickly schedule via `/schedule in 15m | Rappelle-moi...`.

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
