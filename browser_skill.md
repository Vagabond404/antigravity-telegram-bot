---
name: autonomous-browser
description: Navigateur autonome et outils de recherche web propulsés par Chromium Headless sur Armbian. Utilisez ce skill pour chercher sur le web, extraire le contenu d'un site web, ou faire des captures d'écran (screenshots) et les envoyer sur Telegram.
---

# Autonomous Web Browser & Search Skill

Ce skill fournit un ensemble d'outils rapides et autonomes pour naviguer sur le web, exécuter des recherches d'informations en temps réel et capturer des aperçus visuels de pages web directement depuis le serveur Armbian Linux.

## 🛠️ Commandes Disponibles

### 1. 🔍 Recherche Web Instantanée
Effectue une recherche web propre et structurée sans nécessiter de clé API :
```bash
browser search "<termes de recherche>" [--limit 5]
```

### 2. 📄 Extraction & Lecture de Page Web (DOM & Markdown)
Extrait le contenu propre d'une page web au format Markdown :
```bash
browser fetch <url>
```

### 3. 📸 Capture d'Écran Web (Screenshot) & Envoi Telegram
Capture un rendu haute fidélité d'une page web au format PNG :
```bash
# Capture simple
browser screenshot <url> --out /tmp/capture.png

# Capture ET envoi automatique direct dans le chat Telegram de l'utilisateur
browser screenshot <url> --send-tg --caption "Aperçu de <titre/site>"
```

## 💡 Bonnes Pratiques
- Dès que l'utilisateur vous demande de visiter un site ou de vérifier une information en ligne, utilisez `browser search "..."` ou `browser fetch <url>`.
- Si l'utilisateur vous demande à quoi ressemble un site ou une capture visuelle, exécutez `browser screenshot <url> --send-tg --caption "..."`.