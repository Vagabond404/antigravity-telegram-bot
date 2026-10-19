# 🚀 Antigravity Telegram Agent v4.1

**The Universal, Multi-Agent, Multimedia & Self-Updating Telegram Gateway for Google Antigravity CLI (`agy`) — Cross-Platform for Linux (Ubuntu, Debian, Armbian, Oracle Cloud), macOS & Windows.**

Control the entire **Google Antigravity CLI (`agy`)** ecosystem—dynamic AI models, reasoning effort levels, parallel subagents, MCP servers, CLI plugins, persistent sessions, cross-chat long-term vector memory, bidirectional multimedia, and autonomous self-updates—directly from an **interactive Telegram Control Center**.

---

## ✨ What You Can Do With Antigravity Telegram Agent

### 🧠 1. Full Native Integration with Google Antigravity CLI (`agy`)
- **Live Dynamic Model Discovery (`agy models`)**: Automatically queries your authenticated Antigravity CLI to list all available models (`Gemini 4 Argon`, `Gemini 3.8 Flash`, `Claude Opus 5.5`, `Claude Sonnet 5.5`, `GPT-OSS 120B`, etc.) with automatic quota fallback if a model reaches its rate limit.
- **Granular Reasoning Effort (`--effort`)**: Switch effortlessly between `auto`, `low`, `medium`, `high`, `xhigh`, and `max` thinking depths.
- **Execution & Permission Modes**:
  - ⚡ `auto-approve` (`--dangerously-skip-permissions`) — Full autonomous execution.
  - ✏️ `accept-edits` (`--mode accept-edits`) — Auto-accept file edits while prompting for critical shell actions.
  - 📋 `plan` (`--mode plan`) — Read-only architectural planning before execution.
- **CLI Sandbox (`--sandbox`)**: Toggle isolated command execution with a single tap.
- **Session Persistence (`--conversation` / `--continue`)**: Browse recent conversations, resume any past session by ID, or start a fresh session via `/sessions`.
- **Remote Control (`agy remote-control`)**: Start, stop, or monitor the Antigravity Remote Control daemon from `/remote`.

### 🤝 2. Multi-Agent & Subagent Orchestration
- Native support for `invoke_subagent`, `define_subagent`, `manage_subagents`, and `send_message`.
- Launch specialized subagents in parallel (`research`, `self`, or custom-defined subagents) via `/teamwork` or natural prompts.
- Real-time Telegram streaming displays active tool calls, subagent spawns, and elapsed execution times inside an expandable live status message.

### 🧠 3. Cross-Chat Long-Term Vector Memory (`memory_manager.py` & `mem.py`)
- **Persistent Second Brain (`memory.db`)**: Powered by **FastEmbed (`BAAI/bge-small-en-v1.5`)** + **SQLite** with automatic keyword fallback.
- **Structured Categories with Key-Based Upsert**:
  - `profile` — Personal user details, identity, skills, and devices.
  - `preferences` — Coding standards, preferred languages, frameworks, and communication style.
  - `projet` — Per-project architecture, directory paths, tech stack, and progress across chats.
  - `infra` — Servers, IP addresses, OS details, Docker containers, and network topology.
  - `rules` — Permanent user rules enforced across every conversation.
- **Always-On Context Injection & Auto-Capture**: Core profile, preferences, rules, and active projects are automatically injected into every turn (even after `/clear` or a reboot), and key facts stated in chat are captured automatically.

### 🎓 4. Built-In AI Mastery Skill (`telegram-bot-mastery`)
- Comes pre-packaged with the **`telegram-bot-mastery`** skill ([`.agents/skills/telegram-bot-mastery/SKILL.md`](.agents/skills/telegram-bot-mastery/SKILL.md)) and root [`AGENTS.md`](AGENTS.md) rules.
- Automatically synced to `~/.gemini/config/skills/telegram-bot-mastery/SKILL.md` so the AI agent knows all its Telegram capabilities (sending files/media, managing long-term memory, capturing web screenshots, creating dynamic slash commands, and orchestrating subagents) regardless of the active workspace directory.

### 🔌 5. Curated MCP Server Catalog (Installable at Setup or in 1 Click via `/mcp`)
Install and toggle top **Model Context Protocol (MCP)** servers directly during setup (`setup_wizard.py`) or anytime from Telegram via `/mcp`:
1. **Playwright MCP** (`@playwright/mcp@latest`) — Full headless browser automation, clicks, forms, and DOM snapshots.
2. **Firecrawl MCP** (`firecrawl-mcp`) — Deep web scraping and clean Markdown extraction.
3. **Docker MCP** (`@quantgeekdev/docker-mcp`) — Manage Docker containers, images, volumes, and logs from Telegram.
4. **Context7 MCP** (`@upstash/context7-mcp`) — Inject up-to-date official documentation for any library or framework.
5. **Sequential Thinking MCP** (`@modelcontextprotocol/server-sequential-thinking`) — Structured multi-step problem decomposition.
6. **GitHub MCP** (`@modelcontextprotocol/server-github`) — Manage repositories, branches, Issues, and Pull Requests.

### 🖼️ 6. Bidirectional Multimedia & Automatic File Delivery
- **Incoming (User ➔ Agent)**: Send text, **photos**, **videos**, **voice notes**, **audio files**, or **documents/archives** (PDF, ZIP, source code). All media is downloaded into `tmp/` and passed into the agent's context.
- **Outgoing (Agent ➔ User)**: Any file generated or referenced by the agent (images, charts, videos, audio, voice notes, PDFs, ZIPs) is delivered directly to your Telegram chat via `tg_send.py` or automatic end-of-turn detection.

### 🏫 7. Stealth Group Privacy & Open-Ended Custom Missions (`/groups`)
- **Zero-Spam & Stealth Passive Listening**: When added to work, team, school, or public groups, the bot defaults to **Passive Listening Mode** (`can_read=True`, `can_write=False`)—it observes silently and **never** sends greeting spam, error messages, or permission denials in the group.
- **Strict Authorization Control**: Only the Primary Administrator can invite the bot into groups. If an unauthorized user adds the bot to a group, the bot **automatically leaves the group** immediately and notifies the Admin in private chat.
- **100% Open-Ended & Fully Customizable Missions**: Any group can be assigned any custom mission (monitoring questions, summarizing daily discussions, tracking homework/tasks, alerting on critical keywords, or acting as an interactive assistant).
- **Recent Message Log Buffer**: Maintains an in-memory ring buffer of recent group messages, automatically injected into the AI agent's context whenever you ask questions or assign tasks regarding the group.
- **Granular Permissions & Interactive Control Center (`/groups`)**: View all registered groups, toggle permissions (`can_read`, `can_write`), define/update custom missions, inspect recent messages history, or command the bot to leave with one click.

### 🛡️ 8. Hardware Resource Governor & Anti-Crash Protection (`resource_governor.py`)
- **Low-Spec Hardware Detection (TV Boxes, SBCs, Raspberry Pi, 2GB RAM)**: Automatically detects system RAM, CPU cores, and hardware architecture.
- **Anti-Crash Throttling & Priority Adjustment**:
  - Sets Unix process priority (`nice +5`) so the system UI never freezes.
  - Dynamically throttles or pauses background workers (log scanning, auto-update watcher) while an AI reasoning turn is actively executing.
  - Triggers memory garbage collection (`gc.collect()`) before and after every heavy agent turn to prevent Out-Of-Memory (OOM) process termination.

### 🔄 9. Zero-Data-Loss Autonomous Self-Updater (`updater.py` & `VERSION.json`)
- **Background GitHub Watcher**: Periodically checks `origin/main` on GitHub. When a new commit is pushed, the bot sends an interactive Telegram notification displaying the new version, changelog, commit list, and CLI compatibility status.
- **1-Click Telegram Approval**: Tap **`✅ Update Now`** (or run `/update` anytime) to trigger the automated update pipeline:
  1. **Backs up 100% of user data** (`.env`, `memory.db`, `settings.json`, `users.json`, `conversations.json`, `custom_commands.json`, `groups.json`, and skills) before touching any file.
  2. **Downloads & applies latest GitHub code** and restores/merges all user data and custom commands.
  3. **Updates Python dependencies** in `.venv`.
  4. **Verifies Antigravity CLI (`agy`) version** against `min_agy_version` in [`VERSION.json`](VERSION.json) and automatically runs `agy update` (or the official installer) if a newer CLI version is required.
  5. **Detached Hot-Restart**: Spawns an isolated background restarter process (`updater.py --restart-worker`) that cleanly restarts `antigravity-bot.service` (on Linux systemd) or relaunches `bot.py` and edits the Telegram message to confirm completion!

### 🌐 10. Default English Localization & Dynamic Language Detection (`i18n.py`, `/language`)
- **English by Default**: Fresh installations, system commands, default menus, and logs start in English (`en`) out of the box.
- **Dynamic Language Detection**: Automatically analyzes user messages (e.g. French vs English) and adapts notifications, buttons, and agent responses on the fly.
- **Explicit Language Control (`/language`)**: Switch interface language anytime between 🇬🇧 English and 🇫🇷 Français.

---

## ⚡ One-Command Installation

The automated installer sets up everything from scratch:
1. Checks/installs **Python 3**, **Node.js / `npx`** (for MCP servers), **FFmpeg**, and **SQLite**, and configures IPv4/DNS optimizations on Linux/Armbian.
2. Downloads and links the latest **Google Antigravity CLI (`agy`)** globally (`/usr/local/bin/agy` on Linux, `%LOCALAPPDATA%\agy\bin` on Windows).
3. Creates an isolated Python virtual environment (`.venv`) and installs all dependencies.
4. Launches the **Interactive Setup Wizard (`setup_wizard.py`)** to:
   - Authenticate your Google account with `agy`
   - Validate your `TELEGRAM_BOT_TOKEN`
   - Auto-detect your Telegram Admin User ID when you send `/start`
   - Install the default `telegram-bot-mastery` skill and your choice of recommended **MCP Servers** (Playwright, Firecrawl, Docker, Context7, Sequential Thinking, GitHub)
   - Optionally register a **24/7 background service** (`systemd` on Linux / Scheduled Task on Windows).

### 🐧 Linux & macOS (Ubuntu, Debian, Armbian, Oracle Cloud, Fedora, Arch)

```bash
git clone https://github.com/Vagabond404/antigravity-telegram-bot.git antigravity-telegram-bot && cd antigravity-telegram-bot && bash install.sh
```

### 🪟 Windows (Windows 10, Windows 11, Windows Server — PowerShell)

```powershell
git clone https://github.com/Vagabond404/antigravity-telegram-bot.git antigravity-telegram-bot; cd antigravity-telegram-bot; powershell -ExecutionPolicy Bypass -File .\install.ps1
```

---

## 🔄 Updating Your Server Without Losing Any Configuration

All personal configuration and memory files (`.env`, `users.json`, `settings.json`, `memory.db`, `conversations.json`) are excluded from Git via [`.gitignore`](.gitignore) and backed up automatically by [`updater.py`](updater.py).

- **From Telegram (v4.1+)**:
  Simply tap **`✅ Oui, mettre à jour maintenant`** when the bot notifies you of a new GitHub push, or type `/update` in your Telegram chat.
- **From Terminal (Linux / Armbian — e.g. when upgrading from an older version before v4.1)**:
  ```bash
  cd ~/antigravity-telegram-bot && git pull origin main && sudo apt-get install -y nodejs npm && ln -sf "$HOME/.local/bin/agy" /usr/local/bin/agy && (systemctl restart antigravity-bot 2>/dev/null || ./start_bot.sh)
  ```

---

## 🧭 Complete Telegram Commands Reference

| Command | Description |
| :--- | :--- |
| `/start` | Welcome dashboard, live status, and automatic Admin claim on first run |
| `/settings` | 🎛️ **Interactive Control Center** (Models, Effort, Mode, Multi-Agent, MCP, Plugins, Update, etc.) |
| `/models` | 🧠 Switch AI model in real time (`agy models`) |
| `/effort` | 💡 Set reasoning effort level (`auto`, `low`, `medium`, `high`, `xhigh`, `max`) |
| `/mode` | 🛡️ Switch execution mode (`auto-approve`, `accept-edits`, `plan`) & Sandbox |
| `/agents` | 🤝 Toggle Multi-Agent orchestration and select `--agent` profile |
| `/mcp` | 🔌 Manage MCP servers & install **Playwright, Firecrawl, Docker, Context7** in 1 click |
| `/plugins` | 🧩 Manage and import Antigravity CLI plugins (`agy plugin`) |
| `/remote` | 🌐 Start, stop, or inspect `agy remote-control` daemon |
| `/sessions` | 💬 Browse conversation history and resume any previous session (`--conversation`) |
| `/workspace` | 📂 Change primary workspace directory or add secondary directories (`--add-dir`) |
| `/update` | 🔄 Check GitHub & Antigravity CLI for updates and install in 1 click with hot-restart |
| `/update_cli` | ⬆️ Force a self-update of the Antigravity CLI binary (`agy update`) |
| `/memory` | 🧠 View or search your cross-chat Long-Term Vector Memory (`Mem0`) |
| `/remember <fact>` | 📌 Save a permanent fact to Long-Term Memory |
| `/forget <id>` | 🗑️ Delete a memory entry by ID |
| `/commands` | 🕹️ List, create (`/commands add`), or delete (`/commands remove`) custom Telegram commands |
| `/goal <objective>` | 🎯 Run a deep, autonomous long-running workflow until 100% completion |
| `/teamwork <task>` | 👥 Spawn a coordinated team of specialized subagents in parallel |
| `/boost <problem>` | 🚀 Activate maximum reasoning (`max`) and rigorous multi-angle verification |
| `/plan <topic>` | 📐 Generate a comprehensive architectural plan before writing code |
| `/grill_me <idea>` | 🎤 Interactive step-by-step design interview to refine requirements |
| `/status` | 📊 Host telemetry, CLI binary status, active session ID, and token usage |
| `/services` | 🩺 Check system health (CPU, RAM, Disk, Uptime) and service status |
| `/autoheal` | 🤖 Configure autonomous log scanning & AI self-healing for Docker and systemd |
| `/groups` | 🏫 Manage Telegram groups & channels (toggle passive silent mode, active mode, leave chat) |
| `/homework` | 📚 View pending homework assignments, due dates, and mark assignments as completed |
| `/users` | 👥 Role-Based Access Control (Approve/Block users, manage permissions) |
| `/clear` | 🧹 Reset the active conversation session (long-term memory is preserved) |
| `/abort` | 🛑 Immediately stop the currently running agent turn |
| `/help` | 📚 Complete interactive command guide |

---

## 🛠️ Built-In Agent CLI Utilities

The AI agent can invoke these local CLI tools autonomously during any task:

### 1. `tg_send.py` — Proactive Telegram Media Delivery
```bash
# Auto-detect file type (Photo, Video, Audio, Voice, GIF, Document)
python tg_send.py --file "./output/chart.png" --caption "Generated performance chart"

# Explicit media type flags
python tg_send.py --photo "./preview.jpg" --caption "UI screenshot"
python tg_send.py --video "./demo.mp4" --caption "Recorded demo"
python tg_send.py --audio "./track.mp3"
python tg_send.py --voice "./note.ogg"
python tg_send.py --document "./report.pdf"
```

### 2. `mem.py` — Cross-Chat Long-Term Memory CLI
```bash
# Upsert a memory by category and unique key
python mem.py add "Main server runs Armbian Linux at 192.168.110.200" --category infra --key "armbian_server" --importance 5
python mem.py add "Project Alpha: /root/alpha, FastAPI + React" --category projet --key "projet_alpha" --importance 5

# Search or list memories
python mem.py search "Project Alpha"
python mem.py list --category projet
python mem.py delete 3
```

### 3. `browser_tool.py` — Headless Web Search, Markdown Extraction & Screenshots
```bash
python browser_tool.py search "Google Antigravity CLI documentation"
python browser_tool.py fetch "https://example.com"
python browser_tool.py screenshot "https://example.com" --send-tg --caption "Live webpage screenshot"
```

### 4. `command_manager.py` — Dynamic Telegram Command Creator
```bash
python command_manager.py add deploy "Deploy current project" "Run deployment pipeline and verify health for: {prompt}" --mode auto-approve --effort high
python command_manager.py list
python command_manager.py remove deploy
```

---

## 🔒 Security & Privacy (Public-Repository Safe)

- **Zero Hardcoded Secrets**: All tokens, user IDs, memories, and runtime settings are stored in `.env`, `users.json`, `settings.json`, and `memory.db`, which are strictly ignored by Git via [`.gitignore`](.gitignore).
- **First-Admin Auto-Claim**: If `ALLOWED_USER_ID` is left empty in `.env`, the very first user who sends `/start` to the bot is automatically registered as the Primary Administrator and locks access.
- **Role-Based Access Control (RBAC)**: Unknown users are blocked by default and can request access via an inline button, sending an instant approval/rejection prompt (`✅ Approve` / `🚫 Block`) to the Administrator on Telegram.
