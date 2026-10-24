# 🚀 Antigravity Telegram Agent v5.0

**The Production-Grade, Autonomous Multi-Agent & Zero-Cold-Start Telegram Gateway for Google Antigravity CLI (`agy`) — Cross-Platform for Linux (Armbian, Ubuntu, Debian, Oracle Cloud), macOS & Windows.**

Control the entire **Google Antigravity CLI (`agy`)** ecosystem directly from Telegram with high performance:
- ⚡ **Warm `stream-json` Session**: Zero cold-start latency — process stays alive and processes turns continuously.
- 🤝 **Autonomous Multi-Agent Team (`/agents`)**: Specialist sub-agents (Code, Research, 3D Maker, Design) orchestrated autonomously with interactive creation and ZIP export/import.
- 📊 **Usage & Rolling Quota Dashboard (`/usage`)**: Real-time token tracking, rolling 5-hour reset countdown, live connection testing, and cooldown unlocks.
- 🛡️ **Desktop Sandboxing & Workspace Isolation**: Dedicated compartmentalized workspace (`workspace/`) preventing accidental modifications outside project boundaries.
- 🔄 **Zero-Data-Loss Self-Updater (`/update`)**: Safely updates from GitHub while preserving 100% of user databases, memories, settings, and custom agents.
- 🌐 **Full Bilingual Support**: Default English for international setups, seamless automatic French localization.

---

## ✨ Key Features in v5.0

### ⚡ 1. Zero Cold-Start Persistent Engine (`agy_session.py`)
- **Single Persistent Process**: Instead of spawning a new CLI process per message (which took 14+ seconds just for initialization), the bot maintains an active `stream-json` process over standard input/output.
- **Strict Turn Serialization**: Thread-safe FIFO asynchronous queue ensures prompt turns execute without race conditions or process deadlocks.
- **Warm Prompt Caching**: Preserves system prompt context across turns, enabling Google AI prompt cache hits and reducing input token overhead.

### 🤝 2. Autonomous Multi-Agent Orchestration Team (`agent_registry.py`, `/agents`)
- **Native Specialist Sub-Agents**: Sub-agents are defined as standard Markdown files in `.agents/agents/<name>.md` with YAML frontmatter (`name`, `model`, `tools`, `skills`, `description`).
- **Conversational Sub-Agent Creation**: Simply ask your agent in plain language:  
  *“Create a specialized sub-agent for Python FastAPI code architecture”* or *“Crée un sous-agent expert en modélisation 3D”*.
- **Interactive Button Confirmation**:
  - In `ask` mode (default): The orchestrator designs the sub-agent and presents interactive Telegram buttons:  
    `[✅ Confirm & Activate Agent]` and `[❌ Reject / Cancel]`.
  - In `auto` mode: The agent creates and activates sub-agents autonomously when required.
  - In `off` mode: Sub-agent creation is disabled.
- **Import & Export**:
  - Export your entire agent team to a `.zip` archive or individual `.md` file directly on Telegram.
  - Send any `.md` or `.zip` agent file to the bot in private chat to instantly install and register the sub-agent.
- **Strict Group Anti-Injection**: Group messages and unauthorized users are strictly forbidden from creating agents or modifying permissions.

### 📊 3. Real-Time Model Usage & Quota Tracker (`/usage`, `/quota`)
- **Dynamic Model Routing (`auto`)**: Automatically routes everyday quick queries to `gemini-3.8-flash` to preserve premium quotas (Argon, Claude) for heavy coding, mathematics, and complex reasoning.
- **Dashboard Metrics**:
  - Active model, current execution mode, and thinking effort level.
  - Daily & cumulative requests and token usage (Input, Output, Thinking).
  - **Rolling 5-Hour Reset Countdown**: Tracks Google Antigravity's 5-hour rolling quota cycle with estimated time remaining until refresh.
  - Per-model availability indicators (`🟢 Available` vs `⛔ Cooldown`).
- **One-Click Actions**:
  - `[🔄 Reset Cooldown Locks]`: Instantly unblocks all rate-limit cooldowns when your Google tokens are replenished.
  - `[⚡ Test Live Connection]`: Dispatches a lightweight 1-token test turn to verify live API token availability.
  - `[🎛️ Select AI Model]`: Fast shortcut to the model picker.

### 🛡️ 4. Desktop Sandboxing & Compartmentalization
- **Workspace Containment**: By default, the bot initializes in a dedicated `workspace/` compartment inside the installation directory rather than the user's home folder.
- **System Protection**: Prevents accidental reads or writes to sensitive personal directories (Desktop, Documents, Downloads) on Windows and Linux GUI desktops.
- **Native CLI Sandbox (`--sandbox`)**: Can be toggled on demand to enforce terminal sandboxing.
- **Flexible Path Expansion**: Additional project directories can be explicitly mounted via `/workspace` or `--add-dir`.

### 🧠 5. Cross-Chat Long-Term Vector Memory (`mem.py`, `memory_manager.py`)
- **Persistent Second Brain**: SQLite + Vector Embeddings with automatic keyword fallback.
- **Categorized Knowledge**:
  - `profile`: User identity, background, and devices.
  - `preferences`: Coding standards, preferred styles, and workflows.
  - `projet`: Active projects, directory paths, tech stacks, and progress.
  - `infra`: Servers, IP addresses, Docker containers, and network topologies.
  - `rules`: Permanent directives enforced across every conversation.
- Context is retained across sessions and automatically restored even after `/clear` or system reboots.

### 🔄 6. Zero-Data-Loss Self-Updater (`updater.py`, `/update`)
- **Automatic GitHub Monitoring**: Checks for new commits on `origin/main` in the background.
- **Zero-Data-Loss Backup**: Automatically backs up all sensitive configuration and user data (`.env`, `settings.json`, `memory.db`, `groups.json`, `model_quotas.json`, `custom_commands.json`, `.agents/agents/`) before applying git updates.
- **Detached Hot-Restart**: Restarts the systemd daemon or bot process cleanly without dropping the active Telegram session.

---

## ⚡ Quick Start

### Prerequisites
- Python 3.10+
- Google Antigravity CLI (`agy`) installed and authenticated (`agy` command working)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)

---

### 🐧 Linux (Armbian, Ubuntu, Debian, Oracle Cloud) & macOS

```bash
# 1. Clone the repository
git clone https://github.com/Vagabond404/antigravity-telegram-bot.git antigravity-bot
cd antigravity-bot

# 2. Run the automated installer
bash install.sh
```

The installer will:
1. Set up an isolated Python virtual environment (`.venv`).
2. Install all required dependencies.
3. Launch the setup wizard to configure your Telegram Token and Admin ID.
4. Optionally configure a 24/7 background systemd service (`antigravity-bot.service`).

---

### 🪟 Windows (10 / 11 / Server)

Open PowerShell as Administrator:

```powershell
# 1. Clone the repository
git clone https://github.com/Vagabond404/antigravity-telegram-bot.git antigravity-bot
cd antigravity-bot

# 2. Run the installation script
.\install.ps1
```

To run manually at any time:
```powershell
.\start_bot.bat
```

---

## 📱 Telegram Commands Reference

| Command | Description |
|---|---|
| `/start` | Launch the bot, initialize permissions, and show the quickstart menu. |
| `/settings` | Open the interactive Control Center (Model, Effort, Mode, Sandbox, Autonomy). |
| `/usage` (or `/quota`) | View live AI model usage, token consumption, and rolling 5-hour reset timer. |
| `/models` | Select the active AI model (`auto`, `gemini-4-argon`, `claude-sonnet-5-5`, etc.). |
| `/agents` (or `/subagents`) | Manage your autonomous multi-agent team (view, toggle, export, import). |
| `/effort` | Configure thinking reasoning effort (`auto`, `low`, `medium`, `high`, `xhigh`, `max`). |
| `/mode` | Set execution mode (`auto-approve`, `accept-edits`, `plan`). |
| `/mcp` | Enable, disable, or install Model Context Protocol (MCP) servers. |
| `/plugins` | Browse and manage Antigravity CLI plugins. |
| `/workspace` | Inspect or switch the active workspace directory. |
| `/status` | View host health, RAM/CPU load, CLI version, and active session tokens. |
| `/sessions` | Switch between conversation sessions or start a new thread. |
| `/clear` | Clear current turn context while keeping persistent memory intact. |
| `/abort` | Immediately stop and cancel a running execution. |
| `/memory` | Manage long-term vector memory (`/remember`, `/forget`). |
| `/groups` | Manage Telegram groups, stealth mode, permissions, and custom missions. |
| `/language` | Switch interface language between 🇬🇧 English and 🇫🇷 Français. |
| `/update` | Verify and apply updates from GitHub with zero data loss. |

---

## 🤖 Multi-Agent Team Workflow Example

You can direct the agent team naturally:

```text
User: "Crée un sous-agent expert en microcontrôleur ESP32 et circuits imprimés"
Agent: "Voici la proposition pour le sous-agent 'esp32_hardware_expert'..."
[ Telegram interactive buttons appear: [✅ Confirm & Activate Agent] [❌ Cancel] ]
```

Once confirmed, the main orchestrator will delegate hardware, firmware, or pinout queries to the specialist agent automatically!

---

## 🔒 Security & Privacy Architecture

1. **Owner-Only Authentication**: The bot only accepts commands and private prompts from the designated `ALLOWED_USER_ID`. Unauthorized users receive zero responses.
2. **Stealth Group Privacy**: In Telegram groups, the bot operates silently in read-only mode by default without spamming or acknowledging unauthorized messages. Group messages can never trigger agent creation, tool installations, or privilege changes.
3. **Workspace Isolation**: Default execution is anchored to `workspace/`. Tools cannot read or edit files outside the designated workspace path unless explicitly allowed.
4. **Credential Protection**: `.env`, database files (`memory.db`), session caches, and personal sub-agents are strictly git-ignored and automatically backed up across updates.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
