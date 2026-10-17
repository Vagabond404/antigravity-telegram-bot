---
name: telegram-bot-mastery
description: >-
  Complete operational guide and capability reference for the Antigravity Telegram Agent v4.0.
  Use this skill whenever operating through Telegram, sending files/photos/videos/audio to the user,
  storing or retrieving long-term cross-chat memories (personal info, preferences, projects, infra),
  capturing web screenshots, creating dynamic Telegram slash commands, managing MCP servers/plugins,
  or orchestrating multi-agent subagents.
---

# Antigravity Telegram Agent v4.0 — Guide de Maîtrise Complet

Tu es propulsé par **Google Antigravity CLI (`agy`)** et connecté en temps réel à **Telegram** via la passerelle **Antigravity Telegram Agent v4.0**. Ce skill décrit l'ensemble de tes capacités natives et comment les utiliser à la perfection.

---

## 1. 📤 Envoi Multimédia Bidirectionnel sur Telegram (`tg_send.py`)

Tu peux envoyer **n'importe quel fichier** (image, graphique, capture d'écran, vidéo, audio, note vocale, PDF, archive ZIP, script) directement dans la conversation Telegram de l'utilisateur.

### Commandes d'envoi direct
Utilise l'exécutable Python de l'environnement virtuel (ou `python`) avec `tg_send.py` :

```bash
# Détection automatique du format (Photo, Vidéo, Audio, Voix, Animation ou Document)
python tg_send.py --file "/chemin/absolu/fichier.ext" --caption "Description claire"

# Forcer un type de média spécifique :
python tg_send.py --photo "/chemin/absolu/image.png" --caption "Voici l'image générée"
python tg_send.py --video "/chemin/absolu/video.mp4" --caption "Aperçu vidéo"
python tg_send.py --audio "/chemin/absolu/audio.mp3" --caption "Fichier audio"
python tg_send.py --voice "/chemin/absolu/vocal.ogg" --caption "Note vocale"
python tg_send.py --document "/chemin/absolu/archive.zip" --caption "Archive du projet"
```

### Règles importantes pour `tg_send.py`
- **N'utilise JAMAIS `tg_send.py` pour envoyer de simples messages texte de progression** ("Je cherche...", "Analyse en cours...") : l'interface Telegram affiche déjà tes pensées, tes outils et tes sous-agents en temps réel dans une bulle animée.
- En revanche, utilise **toujours** `tg_send.py --file ...` dès que tu produis un livrable visuel ou téléchargeable (image, PDF, capture d'écran, build, export).

---

## 2. 🧠 Mémoire Long-Terme Inter-Conversations (`mem.py` / `memory.db`)

Tu disposes d'un moteur de **Mémoire Long-Terme Hybride (Vectorielle FastEmbed + SQLite)** qui persiste entre toutes les sessions, même après `/clear` ou un redémarrage du serveur.

### Catégories officielles
- `profile` : Identité de l'utilisateur (prénom, métier, localisation, appareils, compétences).
- `preferences` : Préférences de langage, style de code, frameworks favoris, ton des réponses.
- `projet` : Détails de chaque projet (nom, chemin du dossier, stack technique, architecture, état d'avancement, prochaines étapes).
- `infra` : Serveurs, adresses IP, OS (Armbian, Windows, VPS), conteneurs Docker, ports, services.
- `rules` : Règles permanentes demandées par l'utilisateur.

### Commandes de mémorisation proactive (`mem.py`)
Enregistre **proactivement** toute information importante à l'aide d'une clé unique (`--key`) pour mettre à jour proprement le souvenir sans créer de doublon :

```bash
# Enregistrer ou mettre à jour une info personnelle / préférence / règle / infra
python mem.py add "L'utilisateur utilise un serveur Armbian Linux (192.168.110.200) et un PC Windows." --category infra --key "serveurs_utilisateur" --importance 5

# Enregistrer ou mettre à jour l'état d'un projet
python mem.py add "Projet MonApp : situé dans /root/mon-app, stack FastAPI + React, authentification terminée." --category projet --key "projet_monapp" --importance 5

# Rechercher dans la mémoire long-terme (hybride sémantique + mots-clés)
python mem.py search "MonApp architecture"

# Lister tous les souvenirs actifs (ou filtrer par catégorie)
python mem.py list
python mem.py list --category projet

# Supprimer un souvenir obsolète par son ID
python mem.py delete 12
```

---

## 3. 🌐 Navigation Web, Scraping & Captures d'Écran (`browser_tool.py` & MCP)

Tu disposes de plusieurs niveaux d'outils pour interagir avec le Web :

1. **Outils natifs Antigravity** : `search_web` et `read_url_content`.
2. **Serveurs MCP Web (si activés)** :
   - **Playwright MCP (`playwright`)** : Automatisation complète d'un navigateur headless (clics, formulaires, SPA JavaScript, captures DOM).
   - **Firecrawl MCP (`firecrawl`)** : Scraping profond et transformation de sites complexes en Markdown structuré.
3. **Utilitaire intégré `browser_tool.py`** :
   ```bash
   # Recherche web rapide (DuckDuckGo)
   python browser_tool.py search "documentation officielle FastAPI lifespan"

   # Extraction propre d'une page web en Markdown
   python browser_tool.py fetch "https://example.com"

   # Capture d'écran HD d'un site web et envoi direct sur Telegram
   python browser_tool.py screenshot "https://example.com" --send-tg --caption "Aperçu du site en direct"
   ```

---

## 4. 🕹️ Création de Commandes Telegram Dynamiques (`command_manager.py`)

Tu peux créer, lister ou supprimer des commandes `/slash` personnalisées sur Telegram à la demande de l'utilisateur. Elles sont immédiatement synchronisées avec le menu `/` de Telegram :

```bash
# Créer une nouvelle commande /audit
python command_manager.py add audit "Auditer la sécurité et la qualité d'un projet" "Réalise un audit complet de sécurité et de code sur : {prompt}" --mode auto-approve --effort high

# Lister les commandes personnalisées
python command_manager.py list

# Supprimer une commande personnalisée
python command_manager.py remove audit
```

---

## 5. 🤝 Orchestration Multi-Agents & Sous-Agents (`invoke_subagent`)

Lorsque le mode Multi-Agents est actif :
- Utilise `invoke_subagent` pour lancer des sous-agents en parallèle (`research` pour l'exploration rapide, `self` pour exécuter des sous-tâches complètes, ou crée un sous-agent dédié avec `define_subagent`).
- L'interface Telegram affiche automatiquement en direct l'activité de tes sous-agents à l'utilisateur.

---

## 6. 🔌 Écosystème Antigravity CLI (`agy`) & Auto-Heal

Tu peux inspecter ou gérer l'environnement Antigravity CLI à tout moment :
- **Serveurs MCP** : `agy mcp list`, `agy mcp add <nom> -- <commande>`, `agy mcp enable <nom>`, `agy mcp disable <nom>`
- **Plugins CLI** : `agy plugin list`, `agy plugin install <nom>`
- **Modèles IA** : `agy models`
- **Santé du serveur** : `python server_watchdog.py` (vérifie CPU, RAM, Disque et services actifs).
