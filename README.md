# 🤖 Antigravity Telegram Agent v5.0

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Antigravity CLI](https://img.shields.io/badge/antigravity-v1.3.0%2B-orange.svg)](https://github.com/google)
[![Tests Status](https://img.shields.io/badge/tests-32%20passed-brightgreen.svg)](#running-tests)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey.svg)](#installation--quick-start)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **The Production-Grade, Autonomous Multi-Agent & Zero-Cold-Start Gateway for Google Antigravity CLI (`agy`).**  
> Control your autonomous developer environment directly through Telegram with interactive thinking bubbles, visual token gauges, dynamic MCP integration, account-tier adaptation, and deep vector memory.

---

## 📑 Table of Contents

- [Architectural Overview](#-architectural-overview)
- [Key Features](#-key-features)
  - [1. Zero Cold-Start Persistent Engine](#1-zero-cold-start-persistent-engine)
  - [2. Model Usage & Rolling Quota Dashboard (`/usage`)](#2-model-usage--rolling-quota-dashboard-usage)
  - [3. Google Account Tier Adaptation (Free vs Pro vs Ultra)](#3-google-account-tier-adaptation)
  - [4. Dynamic MCP Tool Integration (No More Empty Shells)](#4-dynamic-mcp-tool-integration)
  - [5. Autonomous Multi-Agent Swarm (`/agents`)](#5-autonomous-multi-agent-swarm-agents)
  - [6. Universal Dynamic Internationalization (`i18n`)](#6-universal-dynamic-internationalization-i18n)
  - [7. Long-Term Vector Memory (`mem.py`)](#7-long-term-vector-memory-mempy)
  - [8. Desktop Workspace Isolation & Sandboxing](#8-desktop-workspace-isolation--sandboxing)
  - [9. Zero-Data-Loss Self-Updater (`/update`)](#9-zero-data-loss-self-updater-update)
- [Telegram Command Matrix](#-telegram-command-matrix)
- [Installation & Quick Start](#-installation--quick-start)
  - [Prerequisites](#prerequisites)
  - [Linux (Ubuntu, Debian, Armbian, Raspberry Pi)](#-linux-ubuntu-debian-armbian-raspberry-pi)
  - [Windows 10 / 11 / Server](#-windows-10--11--server)
  - [Cloud VPS (Oracle Cloud Always-Free, AWS, GCP)](#-cloud-vps-oracle-cloud-always-free-aws-gcp)
- [Configuration Reference](#-configuration-reference)
  - [Environment Variables (`.env`)](#environment-variables-env)
  - [Settings Schema (`settings.json`)](#settings-schema-settingsjson)
- [Running Tests](#-running-tests)
- [Troubleshooting & FAQ](#-troubleshooting--faq)
- [Security Model](#-security-model)
- [License](#-license)

---

## 🏛️ Architectural Overview

Antigravity Telegram Agent bridges Telegram's asynchronous Bot API with Google's Antigravity CLI (`agy`) using a stateful, warm `stream-json` process architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                 Telegram Mobile & Desktop App               │
└──────────────────────────────┬──────────────────────────────┘
                               │ Long-Polling / Webhook
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 bot.py (Telegram Gateway)                   │
│  - User Authentication & Admin Verification                 │
│  - Interactive Inline Keyboards & Real-time Progress Bubble │
│  - Image / Document / Voice Ingestion & Translation         │
└──────┬───────────────────────┬───────────────────────┬──────┘
       │                       │                       │
       ▼                       ▼                       ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│  agent_runner│       │  memory_mgr  │       │  i18n Engine │
│  - Fallbacks │       │  (SQLite &   │       │  (Dynamic    │
│  - Tier Gate │       │   Mem0 Vec)  │       │   Translate) │
└──────┬───────┘       └──────────────┘       └──────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│               agy_session.py (Warm Process)                 │
│  - Single `agy --stream-json` persistent subprocess         │
│  - Thread-safe FIFO asynchronous turn queue                 │
│  - Live streaming of internal reasoning (Thinking)         │
│  - Real-time tool execution & subagent event parsing        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│            Google Antigravity CLI Execution Core            │
│  - Claude 3.7 Sonnet / Argon 4 / Gemini 2.5 Pro / Flash     │
│  - Dynamic MCP Servers (File, Browser, Databases, GitHub)   │
│  - Multi-Agent Delegation (.agents/agents/*.md)             │
│  - Workspace Isolation (workspace/)                         │
└─────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 1. Zero Cold-Start Persistent Engine

Traditional CLI wrappers spawn a fresh process for each user turn, incurring 12–18 seconds of initialization latency. 

Antigravity Telegram Agent maintains an active **warm `stream-json` session** (`agy_session.py`):
- **Instant Response**: Turns execute immediately over stdin/stdout pipes with zero process spawning overhead.
- **Warm Prompt Caching**: Preserves system prompt context across turns, maximizing Google AI prompt cache hits and reducing input token costs.
- **Live Thought Streaming**: Thinking processes, tool calls (`read_file`, `run_command`, etc.), and subagent invocations stream directly into an interactive Telegram message bubble in real time.
- **Thread-Safe FIFO Queue**: Requests are strictly serialized to prevent deadlocks or race conditions.

---

### 2. Model Usage & Rolling Quota Dashboard (`/usage`)

Antigravity uses three distinct token quota tracks: **Gemini Flash**, **Gemini Pro / Argon**, and **Claude (Sonnet/Opus)**. When high-tier models hit their quota limits, the agent prevents lockups:

- **Visual Token Gauges**: Detailed ASCII/Unicode progress bars indicating token consumption and remaining headroom per model family:
  ```text
  📊 AI Model Quota & Usage Dashboard
  Current Tier: PRO (Auto-detected)

  ⚡ Gemini Flash:
  [████████████████████░░░░░░░░░░] 67% (201,450 / 300,000 req)
  Status: 🟢 Available

  🧠 Gemini Pro / Argon 4:
  [████████████████████████░░░░░░] 80% (39,800 / 50,000 req)
  Status: 🟢 Available

  🎭 Claude 3.7 Sonnet / Opus:
  [██████████████████████████████] 100% (Exhausted)
  Status: ⛔ Cooldown (Resets in: 3h 14m)
  ```
- **Dynamic Error Parsing**: Automatically parses exact retry cooldowns from API error payloads (e.g. `"rate limit reached, retry in 3h 42m"` or `"resets in 4h"`), ensuring countdown timers remain accurate without freezing.
- **Cross-Family Fallback Ladder**: If Claude credits run out, the agent gracefully falls back through:
  $$\text{Claude 3.7 Sonnet} \longrightarrow \text{Claude 3.5 Sonnet} \longrightarrow \text{Gemini 2.5 Pro / Argon} \longrightarrow \text{Gemini 3.8 Flash}$$
  The agent will never stall with a "no credits left" dead-end.
- **One-Click Unlocks**:
  - `[🔄 Reset Cooldown Locks]`: Clears lockouts once Google tokens refresh.
  - `[⚡ Test Live Connection]`: Sends a lightweight 1-token probe to verify live API reachability.

---

### 3. Google Account Tier Adaptation

Google Antigravity features depend on your Google account subscription. The agent automatically adapts to your tier (`free`, `pro`, `ultra`, or `auto`):

| Feature / Model | Free Tier | Pro Tier | Ultra Tier |
|---|:---:|:---:|:---:|
| **Gemini 3.8 Flash** | ✅ Unlimited | ✅ High Quota | ✅ Priority |
| **Gemini 2.5 Pro** | ⚠️ Restricted / Low RPM | ✅ Full Access | ✅ High Quota |
| **Argon 4 Experimental** | ❌ Unavailable | ✅ Enabled | ✅ Priority |
| **Claude 3.7 Sonnet / Opus** | ❌ Unavailable | ✅ Included | ✅ High Quota |
| **Multi-Agent Swarm (`/agents`)** | ❌ Single Agent only | ✅ Full Swarm | ✅ Full Swarm |
| **Thinking Effort (`max`)** | Low / Medium | Medium / High / Max | High / Max / Extreme |

- **Safe Model Filtering**: The `/models` picker automatically hides models not permitted on the active tier, preventing API permission errors.
- **Configurable Tier**: Set via `/settings` $\rightarrow$ `Tier` or in `.env` (`ACCOUNT_TIER=free|pro|ultra|auto`).

---

### 4. Dynamic MCP Tool Integration

> **No more "empty shell" MCP servers!**

In standard CLI setups, MCP servers configured in `~/.gemini/config/mcp_config.json` might be listed in the CLI catalog but remain unannounced to the agent's LLM prompt context.

Antigravity Telegram Agent dynamically parses `mcp_config.json` on startup:
1. Detects all registered MCP servers (e.g., `playwright`, `supabase`, `systeme-io`, `filesystem`, `github`).
2. Synthesizes tool execution contracts into the runtime system prompt.
3. Automatically instructs the agent on how to call tools via `call_mcp_tool` with exact arguments and schemas.
4. When asked *"Which MCP tools do you have access to?"*, the agent accurately lists all active servers and their operational capabilities.

---

### 5. Autonomous Multi-Agent Swarm (`/agents`)

Orchestrate a team of specialist AI subagents directly from Telegram:

- **Markdown-Native Subagents**: Subagents live as standard Markdown files in `.agents/agents/<name>.md` with structured YAML frontmatter:
  ```markdown
  ---
  name: backend_architect
  description: Specialist in FastAPI, PostgreSQL, and distributed microservices.
  model: claude-3-7-sonnet
  tools: [read_file, write_file, edit_file, run_command]
  skills: [fastapi-pro, python-pro]
  ---
  You are an elite backend architect specializing in scalable microservices...
  ```
- **Natural Language Creation**: Say: *"Create a specialist subagent for Vue.js frontend design"*. The agent generates the manifest and presents Telegram confirmation buttons:
  - `[✅ Confirm & Activate Agent]`
  - `[❌ Reject / Cancel]`
- **ZIP Export & Import**: Export your entire agent team to a `.zip` archive via Telegram, or send any `.md` / `.zip` file into chat to instantly install and register new subagents.
- **Anti-Prompt Injection in Groups**: Group chats are strictly barred from modifying subagents or executing privilege escalation.

---

### 6. Universal Dynamic Internationalization (`i18n`)

- **Default English System**: All code, configuration files, terminal logs, installer wizards, and system prompts are in English by default.
- **Automatic Language Detection**: Detects user language from inbound messages (English, French, Spanish, German, Japanese, etc.).
- **Persistent Locale Engine (`locales/<lang>.json`)**: Localized UI strings are cached to disk.
- **Autonomous AI Self-Translation**: If a user interacts in a language without an existing translation file, the LLM translates the missing interface tokens in the background and commits the new `locales/<lang>.json` automatically.

---

### 7. Long-Term Vector Memory (`mem.py`)

A persistent cross-session memory layer backed by SQLite and semantic embeddings:

- **Structured Knowledge Categories**:
  - `profile`: Identity, company, hardware, and personal context.
  - `preferences`: Architectural choices, indentation, styling rules.
  - `projet`: Current projects, repositories, stack, and milestone status.
  - `infra`: Servers, VPS endpoints, Docker containers, ports.
  - `rules`: Strict operational rules applied to every conversation turn.
- **CLI & Telegram Interface**:
  ```bash
  python mem.py add "Primary production VPS is 192.168.1.100 running Ubuntu 24.04" --category infra --key prod_vps
  python mem.py search "production IP"
  ```
- Context survives across `/clear`, conversation switching, and host reboots.

---

### 8. Desktop Workspace Isolation & Sandboxing

- **Workspace Containment**: By default, commands and file modifications are confined to `workspace/` inside the bot directory.
- **Desktop Shield**: Prevents accidental edits to sensitive user directories (`Desktop`, `Documents`, `Downloads`, `/etc/`).
- **Path Expansion**: Safely mount additional external project directories via `/workspace` or `--add-dir`.

---

### 9. Zero-Data-Loss Self-Updater (`/update`)

- **Automatic GitHub Monitoring**: Checks for new upstream commits on `origin/main`.
- **Atomic Backup**: Automatically archives `.env`, `settings.json`, `memory.db`, `groups.json`, and `.agents/` before applying updates.
- **Hot Daemon Reload**: Restarts the systemd daemon or background process cleanly without dropping the active Telegram connection.

---

## 📱 Telegram Command Matrix

| Command | Arguments | Permission | Description |
|---|---|:---:|---|
| `/start` | None | Anyone / Admin | Initializes bot session, authenticates admin, displays main menu. |
| `/help` | None | All | Comprehensive command guide and usage examples. |
| `/settings` | None | Admin | Interactive Control Center (Model, Effort, Mode, Tier, Sandboxing). |
| `/usage` | None | Admin | Real-time token progress gauges, rolling reset countdown, connection test. |
| `/quota` | None | Admin | Alias for `/usage`. |
| `/models` | `[model_id]` | Admin | Select or view active LLM (`gemini-3.8-flash`, `argon-4`, `claude-3-7-sonnet`). |
| `/effort` | `[level]` | Admin | Set reasoning thinking level (`auto`, `low`, `medium`, `high`, `xhigh`, `max`). |
| `/mode` | `[mode]` | Admin | Set execution mode (`auto-approve`, `accept-edits`, `plan`). |
| `/tier` | `[tier]` | Admin | Switch Google Account Tier (`free`, `pro`, `ultra`, `auto`). |
| `/agents` | None | Admin | Multi-agent swarm management (view, toggle, export, import). |
| `/mcp` | None | Admin | Model Context Protocol servers catalog and diagnostic inspection. |
| `/plugins` | None | Admin | Browse and manage Google Antigravity CLI plugins. |
| `/workspace`| `[path]` | Admin | Inspect or switch active project workspace path. |
| `/status` | None | Admin | System health, CPU/RAM utilization, CLI version, and process status. |
| `/sessions` | None | Admin | Conversation history list, session resume, or thread creation. |
| `/clear` | None | Admin | Start fresh turn context while preserving persistent long-term memory. |
| `/abort` | None | Admin | Immediately terminate and cancel a long-running execution turn. |
| `/memory` | `[query]` | Admin | Search long-term vector memory facts. |
| `/remember`| `<fact>` | Admin | Proactively store a fact into persistent memory. |
| `/forget` | `<id>` | Admin | Remove a specific memory record by its key or ID. |
| `/groups` | None | Admin | Group monitoring, stealth mode, permissions, and group missions. |
| `/language`| `[code]` | All | Toggle language (English, Français, Español, etc.). |
| `/update` | None | Admin | Check for GitHub updates and apply with automatic zero-data-loss backup. |
| `/autoheal` | None | Admin | Autonomous log scanner and self-healing engine status. |

---

## ⚡ Installation & Quick Start

### Prerequisites

1. **Python 3.10+**: Verify with `python --version` (or `python3 --version`).
2. **Google Antigravity CLI (`agy`)**: Install and authenticate Google Antigravity on your host:
   ```bash
   agy --version
   agy auth login
   ```
3. **Telegram Bot Token**: Create a bot and receive an API token via [@BotFather](https://t.me/BotFather).

---

### 🐧 Linux (Ubuntu, Debian, Armbian, Raspberry Pi)

Run the automated one-line installer:

```bash
# 1. Clone the repository
git clone https://github.com/Vagabond404/antigravity-telegram-bot.git antigravity-bot
cd antigravity-bot

# 2. Run the automated installer
bash install.sh
```

The installer will:
- Create an isolated Python virtual environment (`.venv`).
- Install all dependencies (`requirements.txt`).
- Launch the interactive configuration wizard (`setup_wizard.py`).
- Set up an autostarting background systemd service (`antigravity-bot.service`).

To manage the daemon:
```bash
sudo systemctl status antigravity-bot
sudo systemctl restart antigravity-bot
sudo journalctl -u antigravity-bot -f
```

---

### 🪟 Windows (10 / 11 / Server)

Open PowerShell as Administrator:

```powershell
# 1. Clone the repository
git clone https://github.com/Vagabond404/antigravity-telegram-bot.git antigravity-bot
cd antigravity-bot

# 2. Run the PowerShell installer
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

To launch the bot anytime:
```powershell
.\start_bot.bat
```

---

### ☁️ Cloud VPS (Oracle Cloud Always-Free, AWS, GCP)

Deploy directly to an Oracle Cloud Always-Free ARM64/AMD64 VM from your Windows workstation:

```powershell
.\Deploy-ToOracleCloud.ps1 -ServerIp "YOUR_SERVER_IP" -SshUser "ubuntu" -SshKeyPath "C:\path\to\id_rsa"
```

Or run `setup_oracle.sh` directly on your cloud instance:
```bash
bash setup_oracle.sh
```

---

## ⚙️ Configuration Reference

### Environment Variables (`.env`)

Copy `.env.example` to `.env`:

```env
# ==============================================================================
# Antigravity Telegram Agent Configuration
# ==============================================================================

# Required: Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# Optional: Primary Administrator Telegram User ID (Leave empty for auto-claim on /start)
ALLOWED_USER_ID=987654321

# Optional: Custom path to Antigravity CLI binary (leave empty for auto-discovery)
AGY_BIN_PATH=

# Optional: Default Agent Workspace Directory
WORKSPACE_DIR=workspace

# Optional: Account Tier (free | pro | ultra | auto)
ACCOUNT_TIER=auto

# Optional: System Language (en | fr | es | de | auto)
DEFAULT_LANGUAGE=en
```

### Settings Schema (`settings.json`)

Runtime user preferences are automatically managed through `/settings` and saved in `settings.json`:

```json
{
  "active_model": "auto",
  "thinking_effort": "high",
  "execution_mode": "auto-approve",
  "account_tier": "auto",
  "subagent_autonomy": "ask",
  "workspace_sandboxing": true,
  "language": "en"
}
```

---

## 🧪 Running Tests

The test suite contains 32 comprehensive tests verifying session state handling, cross-family quota fallbacks, MCP prompt injections, account tier filters, and dynamic i18n:

```bash
# Set PYTHONPATH and execute pytest
python -m pytest tests -v
```

Expected output:
```text
============================= test session starts =============================
tests/test_agent_registry.py::test_seed_default_agents PASSED            [  3%]
tests/test_agent_registry.py::test_save_and_get_agent PASSED             [  6%]
...
tests/test_safety_and_routing.py::test_parse_cooldown_from_error PASSED  [ 90%]
tests/test_safety_and_routing.py::test_account_tier_model_filtering PASSED [ 93%]
tests/test_safety_and_routing.py::test_dynamic_language_and_locale_persistence PASSED [ 96%]
tests/test_safety_and_routing.py::test_mcp_servers_prompt_injection PASSED [100%]
============================= 32 passed in 1.79s ==============================
```

---

## ❓ Troubleshooting & FAQ

### Q: Why did Claude say my credits ran out and tell me to wait 4 hours?
> **Answer**: High-reasoning models (Claude 3.7 Sonnet / Opus) share an aggressive token quota window in Google Antigravity.  
> 1. Use `/usage` to view your live countdown timer.  
> 2. Antigravity Telegram Agent v5.0 automatically falls back to **Gemini 2.5 Pro** or **Gemini 3.8 Flash** so your work continues uninterrupted.  
> 3. Once your credits refresh, tap `[🔄 Reset Cooldown Locks]` in `/usage`.

### Q: My MCP servers show in `/mcp`, but the agent says it has no tools.
> **Answer**: Ensure your MCP servers are configured in `~/.gemini/config/mcp_config.json`. In v5.0, the agent dynamically parses this file and injects complete tool schemas and instructions into the system prompt automatically.

### Q: Can someone else message my bot and execute commands on my computer?
> **Answer**: **No.** The bot enforces strict single-admin authentication (`ALLOWED_USER_ID`). Messages from unauthorized users are silently dropped without response or CLI execution.

### Q: How do I switch languages?
> **Answer**: Simply speak to the bot in your preferred language (e.g., French, German, Spanish), or send `/language fr` to change the interface buttons and menus.

---

## 🔐 Security Model

1. **Privileged Access Control**: All actions, commands, and subagent controls are locked to `ALLOWED_USER_ID`.
2. **Group Anti-Injection**: When added to Telegram groups, the bot operates in stealth observation mode. Group members cannot trigger subagent creation, install tools, or access host files.
3. **Local Workspace Boundary**: File writes are constrained within `workspace/` by default.
4. **Secret Isolation**: Personal tokens, `.env`, SQLite databases (`memory.db`), and user caches are strictly excluded from git tracking via `.gitignore`.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

Developed with ❤️ for the Google Antigravity & AI Developer Community.
