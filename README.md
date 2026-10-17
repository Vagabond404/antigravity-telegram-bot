# 🚀 Antigravity Telegram Agent v4.0

**Pont universel, multi-agent et multimédia entre Telegram et Google Antigravity CLI (`agy`) — Compatible Windows, Linux & macOS.**

Contrôlez intégralement **Antigravity CLI** (modèles dynamiques, niveaux de réflexion, sous-agents parallèles, serveurs MCP, plugins, sessions persistantes, Remote Control, mémoire vectorielle et multimédia bidirectionnel) directement depuis une interface **Telegram interactive ultra-intuitive**.

---

## ✨ Fonctionnalités Principales

### 🧠 100% Adapté à la dernière version d'Antigravity CLI (`agy`)
- **Modèles Dynamiques (`agy models`)** : Récupération en temps réel des modèles disponibles sur votre compte Antigravity (`Gemini 4 Argon`, `Gemini 3.8 Flash`, `Claude Opus 5.5`, `Claude Sonnet 5.5`, `GPT-OSS 120B`, etc.) et changement en un clic depuis Telegram.
- **Niveaux de Raisonnement (`--effort`)** : `auto`, `low`, `medium`, `high`, `xhigh`, `max`.
- **Modes d'Exécution (`--permission-mode`)** :
  - 🚀 `auto-approve` (`--dangerously-skip-permissions`) — Autonomie complète.
  - ✏️ `accept-edits` — Édition automatique des fichiers, confirmation pour les commandes critiques.
  - 📋 `plan` — Planification et lecture seule avant action.
- **Mode Sandbox (`--sandbox`)** : Isolation sécurisée de l'exécution des commandes terminal.
- **Orchestration Multi-Agents & Sous-Agents** :
  - Support natif des outils `invoke_subagent`, `define_subagent`, `manage_subagents`, `send_message` et du profil `--agent` (`default`, `research`, `self`, ou profil personnalisé).
  - Suivi en temps réel dans Telegram des sous-agents lancés en parallèle.
- **Continuité des Sessions (`--conversation` / `--continue`)** :
  - Basculez entre vos conversations passées, reprenez une session précise ou démarrez une session vierge via `/sessions`.
- **Gestionnaire MCP (`agy mcp`) & Plugins (`agy plugin`)** :
  - Listez, ajoutez ou supprimez des serveurs MCP et des plugins Antigravity directement depuis Telegram (`/mcp`, `/plugins`).
- **Remote Control (`agy remote-control`) & Auto-Update (`agy update`)** :
  - Activez le démon de contrôle distant Antigravity ou mettez à jour le binaire `agy` depuis Telegram (`/remote`, `/update_cli`).

### 🎛️ Centre de Contrôle Telegram Ultra-Intuitif
Gérez **absolument tous les paramètres** sans jamais toucher à un fichier de configuration grâce au tableau de bord interactif `/settings` :
- `/settings` — Tableau de bord complet (2 pages interactives)
- `/models` — Sélecteur dynamique de modèle IA
- `/effort` — Sélecteur de profondeur de réflexion (`auto` à `max`)
- `/mode` — Sélecteur du mode de permissions + Sandbox
- `/agents` — Configuration Multi-Agents & profils de sous-agents
- `/sessions` — Historique et reprise des sessions Antigravity
- `/mcp` — Gestion des serveurs Model Context Protocol (MCP)
- `/plugins` — Gestion des plugins Antigravity CLI
- `/remote` — Démarrage/Arrêt du serveur `agy remote-control`
- `/workspace` — Changement du dossier de travail (`--add-dir` inclus)

### 🖼️ Multimédia Bidirectionnel Complet
- **Entrant (Utilisateur ➔ Agent)** : Envoyez du texte, des **photos**, des **vidéos**, des **messages vocaux**, des **fichiers audio** ou n'importe quel **document** (PDF, code, archive, etc.). Les fichiers sont téléchargés proprement et transmis au contexte de l'agent.
- **Sortant (Agent ➔ Utilisateur)** : L'agent peut vous envoyer n'importe quel fichier généré ou demandé (**images**, **vidéos**, **audios**, **notes vocales**, **documents**) via l'outil intégré `tg_send.py` ou par détection automatique en fin de tour.

### 🛡️ Stabilité Maximale & File d'Attente Intelligente
- **Zéro Crash / Zéro Message Perdu** : Verrou d'exécution asynchrone (`turn_execution_lock`) qui met proprement en file d'attente les messages envoyés pendant que l'agent réfléchit, avec possibilité d'interrompre à tout moment via `/stop`.
- **Protection des Prompts Longs** : Passage automatique par fichier temporaire pour les instructions volumineuses afin d'éviter toute limite de ligne de commande sous Windows et Linux.

---

## ⚡ Installation en Une Seule Commande (Windows & Linux)

L'installateur automatique s'occupe de **tout** :
1. Vérifie/installe Python 3 et crée un environnement virtuel isolé (`.venv`).
2. Installe toutes les dépendances Python requises.
3. Télécharge et installe automatiquement la dernière version d'**Antigravity CLI (`agy`)**.
4. Lance l'**Assistant Interactif (`setup_wizard.py`)** qui vous aide à :
   - Connecter votre compte **Antigravity CLI**
   - Renseigner et vérifier votre **`TELEGRAM_BOT_TOKEN`**
   - Détecter automatiquement votre **ID Administrateur Telegram** (en envoyant simplement `/start` à votre bot)
   - Activer le démarrage automatique en arrière-plan (`systemd` sur Linux / Tâche planifiée sur Windows).

### 🐧 Linux & macOS (Ubuntu, Debian, Armbian, Oracle Cloud, Fedora, Arch)

Depuis un terminal, clonez le dépôt et lancez `install.sh` :

```bash
git clone https://github.com/Vagabond404/antigravity-telegram-bot.git antigravity-telegram-bot && cd antigravity-telegram-bot && bash install.sh
```

*(Ou si vous êtes déjà dans le dossier du projet :)*
```bash
bash install.sh
```

### 🪟 Windows (Windows 10, Windows 11, Windows Server)

Ouvrez **PowerShell** et exécutez :

```powershell
git clone https://github.com/Vagabond404/antigravity-telegram-bot.git antigravity-telegram-bot; cd antigravity-telegram-bot; powershell -ExecutionPolicy Bypass -File .\install.ps1
```

*(Ou si vous êtes déjà dans le dossier du projet :)*
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Vous pouvez ensuite lancer le bot à tout moment en double-cliquant sur **`start_bot.bat`** (Windows) ou via **`./start_bot.sh`** (Linux/macOS).

---

## 🧭 Commandes Telegram Disponibles

| Commande | Description |
| :--- | :--- |
| `/start` | Accueil, statut en direct et réclamation automatique du rôle Admin au 1er lancement |
| `/settings` | 🎛️ **Centre de Contrôle complet** (Modèles, Effort, Mode, Agents, MCP, Plugins, etc.) |
| `/models` | 🧠 Changer de modèle IA en direct (`agy models`) |
| `/effort` | ⚡ Ajuster l'effort de raisonnement (`auto`, `low`, `medium`, `high`, `xhigh`, `max`) |
| `/mode` | 🛡️ Changer le mode d'approbation (`auto-approve`, `accept-edits`, `plan`) et Sandbox |
| `/agents` | 🤝 Configurer l'orchestration Multi-Agents et le profil `--agent` |
| `/sessions` | 💬 Gérer l'historique des conversations et reprendre une session (`--conversation`) |
| `/mcp` | 🔌 Lister, ajouter ou supprimer des serveurs MCP (`agy mcp`) |
| `/plugins` | 🧩 Gérer les plugins Antigravity CLI (`agy plugin`) |
| `/remote` | 🌐 Démarrer ou arrêter une session `agy remote-control` |
| `/workspace` | 📂 Changer le répertoire de travail principal ou ajouter des dossiers (`--add-dir`) |
| `/new` | 🔄 Démarrer une nouvelle conversation vierge |
| `/stop` | 🛑 Interrompre immédiatement l'exécution en cours |
| `/goal <objectif>` | 🎯 Lancer une mission autonome approfondie jusqu'à complétion |
| `/plan <sujet>` | 📐 Générer un plan d'architecture détaillé avant exécution |
| `/grill_me <idée>` | 🎤 Entretien interactif pas-à-pas pour cadrer un projet |
| `/boost <tâche>` | 🚀 Activer le raisonnement maximal et la vérification rigoureuse |
| `/teamwork <projet>` | 👥 Mobiliser des sous-agents spécialisés en parallèle |
| `/memories` | 🧠 Explorer le Second Cerveau SQLite & graphe de connaissances |
| `/vault` | 📓 Explorer les notes Markdown (Obsidian Vault) |
| `/status` | 📊 Tableau de bord télémétrique du système hôte (CPU, RAM, Disque, Réseau) |
| `/access` | 👥 Gérer les utilisateurs et permissions (Administrateurs / Invités) |

---

## 📤 Envoi de Fichiers par l'Agent (`tg_send.py`)

L'agent dispose d'un utilitaire CLI dédié lui permettant de vous envoyer proactivement n'importe quel média pendant ou à la fin de sa réflexion :

```bash
# Envoyer un message texte formaté HTML
python tg_send.py "<b>Opération terminée !</b>"

# Envoyer une image / capture d'écran
python tg_send.py --photo "./capture.png" --caption "Voici l'aperçu généré"

# Envoyer une vidéo, un audio, une note vocale ou un document
python tg_send.py --video "./demo.mp4" --caption "Vidéo de démonstration"
python tg_send.py --audio "./musique.mp3"
python tg_send.py --voice "./note.ogg"
python tg_send.py --document "./rapport.pdf"

# Détection automatique du type de média selon l'extension
python tg_send.py --file "./resultat.png" --caption "Envoyé automatiquement"
```

---

## 🔒 Sécurité & Confidentialité (Dépôt Public)

- **Aucune donnée personnelle dans le code** : Tous les identifiants, tokens et préférences locales sont stockés exclusivement dans `.env`, `users.json` et `settings.json`, qui sont ignorés par Git via `.gitignore`.
- **Premier Administrateur Automatique (Auto-Claim)** : Si aucun `ALLOWED_USER_ID` n'est défini dans `.env`, le tout premier utilisateur qui envoie `/start` au bot devient automatiquement l'Administrateur principal et verrouille l'accès.
- **Contrôle d'Accès par Rôles (RBAC)** : Les utilisateurs inconnus sont bloqués par défaut et peuvent demander un accès invité validé par l'administrateur via des boutons Telegram interactifs (`✅ Accepter` / `🚫 Bloquer`).
