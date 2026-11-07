# 🤖 Antigravity Telegram Agent v5.1 — Guide Complet du Projet

> **Documentation intégrale de référence** : Architecture, Fonctionnement, Capacités, Personnalisation et Guide d'Utilisation.

---

## 📑 Sommaire

1. [À quoi sert ce projet ? (Vision & Raison d'être)](#1-à-quoi-sert-ce-projet--vision--raison-dêtre)
2. [Architecture Technique & Fonctionnement Interne](#2-architecture-technique--fonctionnement-interne)
   - Le moteur *Zero Cold-Start* (Processus chaud `stream-json`)
   - Le pont asynchrone Telegram ↔ Google Antigravity CLI (`agy`)
   - Gestionnaire de quotas temps réel & Ladder de secours multi-familles
3. [Panorama des Fonctionnalités Clés](#3-panorama-des-fonctionnalités-clés)
   - Streaming interactif des pensées et exécutions d'outils
   - Mémoire hybride à long terme, profils de personnes et graphe relationnel
   - Planificateur de tâches et automatisations autonomes en arrière-plan
   - Essaim multi-agents (Subagents) au format Markdown standard
   - Intégration dynamique des serveurs MCP (Model Context Protocol)
   - Commandes personnalisées et modes opérationnels avancés
   - Sécurité, isolation en bac à sable (Sandboxing) et anti-injection en groupe
   - Internationalisation dynamique (i18n) et auto-traduction
   - Auto-Heal, scanner de logs et mise à jour atomique sans perte de données
4. [Guide d'Utilisation au Quotidien](#4-guide-dutilisation-au-quotidien)
   - Première prise en main & Démarrage
   - Matrice complète des commandes Telegram
   - Gestion multimédia : photos, vidéos, mémos vocaux, documents et code
5. [Comment Parler à l'IA pour un Résultat Optimal ?](#5-comment-parler-à-lia-pour-un-résultat-optimal-)
   - Ingénierie de prompt adaptée à Antigravity
   - Exploiter les commandes de workflow (`/plan`, `/goal`, `/grill_me`, `/boost`, `/teamwork`)
   - Résolution itérative, vérification rigoureuse et autonomie guidée
6. [Comment Personnaliser Intégralement le Système ?](#6-comment-personnaliser-intégralement-le-système-)
   - Créer et configurer des Subagents spécialisés
   - Créer des commandes slash personnalisées (`custom_commands.json`)
   - Enseigner des règles de mémoire, profils et relations (`mem.py`)
   - Ajuster les règles de vouvoiement, tutoiement et tonalité
   - Connecter de nouveaux outils et serveurs MCP
7. [Cas d'Usage Réels et Possibilités](#7-cas-dusage-réels-et-possibilités)
8. [Dépannage & Bonnes Pratiques](#8-dépannage--bonnes-pratiques)

---

## 1. À quoi sert ce projet ? (Vision & Raison d'être)

### Le Problème Initial
L'environnement **Google Antigravity CLI (`agy`)** est l'un des outils de développement autonome les plus puissants au monde, combinant les meilleurs modèles d'IA (Gemini 2.5/3.8, Claude 3.7 Sonnet, Argon 4) avec l'exécution native de commandes système, d'édition de code, d'orchestration de sous-agents et de connecteurs MCP.

Cependant, dans son fonctionnement d'origine :
- Il est **confiné à un terminal de bureau** : impossible de le piloter depuis un smartphone dans les transports, depuis une tablette ou lors d'un déplacement.
- Chaque nouvelle commande CLI classique réinitialise un processus neuf, créant une **latence de démarrage de 12 à 18 secondes** (*cold-start*) et détruisant le cache mémoire de prompt.
- Les dépassements de quota sur les modèles à fort raisonnement (Claude Sonnet / Opus) bloquent net l'utilisateur avec un message de réessai à 4 heures sans solution de repli immédiate.
- Il n'y a pas de mémoire persistante native entre différentes sessions de travail.

### La Solution : Antigravity Telegram Agent v5.1
Ce projet transforme Antigravity en un **assistant autonome universel disponible 24h/24 dans votre poche via Telegram** :
- **Accessible partout** : Pilotez votre machine, vos serveurs de dev, vos dépôts git et vos scripts depuis l'application Telegram (iOS, Android, Web, PC/Mac).
- **Zéro latence (*Zero Cold-Start*)** : Un processus CLI tourne en permanence en arrière-plan en mode flux JSON interactif. Les réponses démarrent en une fraction de seconde.
- **Transparence totale** : Vous voyez en direct l'IA réfléchir (*Thinking*), appeler ses outils (`run_command`, `read_file`, `write_file`) et déléguer des tâches à des subagents dans une bulle interactive animée.
- **Résilience absolue aux quotas** : Bascule automatique transparente entre Claude, Gemini Pro et Gemini Flash sans jamais bloquer votre flux de travail.
- **Mémoire encyclopédique permanente** : L'IA se souvient de votre infrastructure, de vos projets, de vos préférences de code, de vos collègues et sait exactement s'il faut les tutoyer ou les vouvoyer.
- **Automatisation proactive** : Capable de programmer ses propres rappels, veilles et tâches de maintenance planifiées.

---

## 2. Architecture Technique & Fonctionnement Interne

Le schéma ci-dessous résume le flux d'exécution complet, de Telegram jusqu'au système hôte :

```
┌─────────────────────────────────────────────────────────────┐
│                 Telegram Mobile & Desktop App               │
└──────────────────────────────┬──────────────────────────────┘
                               │ Long-Polling / Webhook (python-telegram-bot)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 bot.py (Passerelle & Cœur)                  │
│  - Contrôle d'accès Admin strict (ALLOWED_USER_ID)          │
│  - Claviers interactifs, bulles de statut & spinner         │
│  - Réception photos, documents, vocaux (transcription)      │
│  - Routage des commandes standard et personnalisées         │
└──────┬───────────────────────┬───────────────────────┬──────┘
       │                       │                       │
       ▼                       ▼                       ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│  agent_runner│       │  memory_mgr  │       │  scheduler   │
│  - Fallbacks │       │  (SQLite +   │       │  (tasks.py   │
│  - Tier Gate │       │   FastEmbed) │       │   DB Worker) │
└──────┬───────┘       └──────────────┘       └──────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│               agy_session.py (Processus Chaud)              │
│  - Processus persistant `agy --stream-json`                 │
│  - File d'attente FIFO thread-safe (évite tout conflit)    │
│  - Parsing des flux JSON en direct :                         │
│      * step_index, thinking, tool_calls, subagents          │
│  - Détection dynamique des erreurs de quota et retries      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│            Google Antigravity CLI Execution Core            │
│  - Modèles : Claude 3.7 Sonnet / Argon 4 / Gemini Pro/Flash │
│  - Serveurs MCP dynamiques (Supabase, Playwright, GitHub)   │
│  - Subagents modulaires (.agents/agents/*.md)               │
│  - Bac à sable projet (workspace/)                          │
└─────────────────────────────────────────────────────────────┘
```

### Le Moteur Zero Cold-Start (`agy_session.py`)
Au lieu de lancer une commande `agy prompt "..."` à chaque message, le bot instancie une session persistante `agy --stream-json`. 
- Les entrées de l'utilisateur sont injectées sur l'entrée standard `stdin`.
- Les événements retournés par le moteur Antigravity sont lus en continu sur `stdout`.
- Ce mode conserve les jetons en cache (*Prompt Caching* de Google AI), divisant drastiquement les coûts en tokens et supprimant les 15 secondes d'initialisation.

### Gestionnaire de Quotas & Échelle de Secours (*Fallback Ladder*)
Dans `quota_manager.py`, le bot surveille en temps réel les limites des 3 familles de modèles :
1. **Gemini Flash** (Volume massif, quasi illimité).
2. **Gemini Pro / Argon 4** (Raisonnement avancé, quota intermédiaire).
3. **Claude 3.7 Sonnet / Opus** (Raisonnement maximal, quota strict avec fenêtre de réinitialisation de plusieurs heures).

Si Claude signale un épuisement de quota (ex: *"rate limit reached, retry in 3h 14m"*), le bot extrait mathématiquement le temps de cooldown, enclenche un compte à rebours précis et réoriente automatiquement la requête vers le barreau inférieur :
$$\text{Claude 3.7 Sonnet} \longrightarrow \text{Claude 3.5 Sonnet} \longrightarrow \text{Gemini 2.5 Pro / Argon 4} \longrightarrow \text{Gemini 3.8 Flash}$$
L'utilisateur n'est jamais interrompu au milieu d'un débogage ou d'un développement critique.

---

## 3. Panorama des Fonctionnalités Clés

### 1. Streaming Interactif & Bulle de Progression
Pendant que l'IA résout une tâche complexe :
- Une bulle Telegram s'actualise en temps réel avec un indicateur animé (spinner).
- Les étapes de réflexion intérieure (*Thinking*) sont synthétisées.
- Les appels d'outils (`Lecture de config.py`, `Exécution de pytest`, etc.) s'affichent sous forme de tags clairs.
- Un bouton interactif `[🛑 Interrompre]` permet d'annuler instantanément la tâche en cours à n'importe quel moment.

### 2. Mémoire Permanente Hybride (`mem.py`)
Contrairement aux bots classiques qui oublient tout dès qu'on ferme la conversation ou tape `/clear`, cet agent intègre une mémoire multi-niveaux :
- **Profils de Personnes (`mem.py person`)** : Enregistrement de l'identité, du rôle, et surtout de la **consigne d'adresse** (tutoiement, vouvoiement, ton amical, sec ou protocolaire). L'IA adapte instantanément son style de réponse en fonction de la personne évoquée ou avec qui elle échange.
- **Graphe Social (`mem.py relate`)** : Cartographie des relations interpersonnelles ("Ange est l'associé de Marc", "Sophie est cliente de l'agence").
- **Catégories de Faits** :
  - `profile` : Nom, rôles, fuseau horaire, matériel.
  - `preferences` : Frameworks favoris, indentation, conventions de nommage.
  - `projet` : Dépôts git, architectures en cours, statut des jalons.
  - `infra` : Adresses IP des serveurs, conteneurs Docker, ports, clés SSH.
  - `rules` : Consignes strictes et permanentes que l'IA doit toujours respecter.

### 3. Tâches Planifiées & Automatisations Autonomes (`tasks.py`)
Le bot embarque son propre planificateur asynchrone fonctionnant en tâche de fond :
- **Minuteurs ponctuels** : *"Dans 20 minutes, rappelle-moi de tester le build"*.
- **Tâches récurrentes** : *"Toutes les 2 heures, vérifie l'état de l'API et préviens-moi en cas d'erreur 500"*.
- **Briefing matinal** : *"Tous les jours à 08h30, résume mes tâches et la météo"*.
- **Commandes shell planifiées** : Possibilité d'exécuter un script bash/powershell en arrière-plan à heure fixe.
- Les tâches sont gérées via Telegram avec `/tasks` ou directement en ligne de commande via `python tasks.py`.

### 4. Essaim Multi-Agents (Subagents)
L'agent peut créer et orchestrer des agents spécialisés définis dans des fichiers Markdown structurés dans `.agents/agents/<nom>.md` :
- Chaque subagent possède son propre modèle, ses outils autorisés, ses compétences et son prompt système.
- Vous pouvez demander en langage naturel : *"Crée un subagent expert en cybersécurité OWASP"* ; le bot génère le manifeste, demande votre confirmation via un bouton Telegram, et l'enregistre immédiatement.
- Sauvegarde et partage simplifiés : exportez votre équipe d'agents en archive `.zip` via Telegram, ou glissez-déposez un fichier `.md` dans la discussion pour l'ajouter instantanément.

### 5. Intégration Dynamique des Serveurs MCP
Le bot inspecte automatiquement la configuration globale `~/.gemini/config/mcp_config.json` :
- Tous les serveurs MCP déclarés (ex: Playwright pour le scraping web complexe, Supabase pour les bases de données, GitHub, Filesystem) sont injectés dans le contexte du modèle avec leurs schémas d'outils.
- L'IA sait exactement comment invoquer `call_mcp_tool` avec les paramètres requis.
- Tapez `/mcp` sur Telegram pour inspecter l'état de vos serveurs et tester leur connectivité.

### 6. Commandes Personnalisées Avancées
Grâce à `command_manager.py` et `custom_commands.json`, le bot propose des modes opératoires surpuissants :
- `/goal <tâche>` : Mode d'accomplissement autonome profond. L'IA pousse son raisonnement au maximum, vérifie et teste chaque action, et ne s'arrête que lorsque l'objectif est achevé à 100%.
- `/grill_me <sujet>` : Mode interview technique. L'IA vous pose des questions ciblées une par une pour cadrer un projet avant de coder.
- `/plan <sujet>` : Génère une feuille de route détaillée sans modifier le code immédiatement.
- `/boost <problème>` : Pousse le raisonnement à l'effort maximal avec vérification croisée.
- `/teamwork <mission>` : Orchestre plusieurs sous-agents en parallèle.

### 7. Sécurité, Isolation & Sandboxing
- **Accès Administrateur Unique** : Seul l'identifiant Telegram configuré dans `ALLOWED_USER_ID` peut interagir avec le bot. Les inconnus sont ignorés silencieusement sans consommer de tokens ni exécuter de code.
- **Protection Anti-Injection en Groupe** : En groupe Telegram, le bot passe en mode discret (*stealth*). Les membres du groupe ne peuvent pas modifier les subagents, ni accéder aux fichiers du serveur hôte.
- **Confinement dans `workspace/`** : Par défaut, les créations et modifications de fichiers sont cantonnées au dossier du projet pour protéger vos fichiers système et votre bureau.

### 8. Auto-Heal & Mise à Jour Sans Perte de Données
- Le scanner de logs analyse automatiquement les erreurs récurrentes.
- La commande `/update` vérifie les nouveaux commits sur le dépôt GitHub officiel, réalise une sauvegarde atomique de vos bases de données, de votre configuration `.env` et de vos agents, applique les changements et redémarre le démon en douceur sans coupure perceptible.

---

## 4. Guide d'Utilisation au Quotidien

### Prise en Main Rapide
1. Ouvrez votre bot sur Telegram et cliquez sur `/start`.
2. Le bot vous reconnaît comme administrateur et affiche le panneau d'accueil.
3. Écrivez simplement ce que vous souhaitez accomplir, exactement comme vous le feriez avec un développeur senior à vos côtés.

### Matrice Complète des Commandes Telegram

| Commande | Rôle & Action |
|---|---|
| `/start` | Initialise la session, affiche le menu principal et valide vos droits admin. |
| `/help` | Affiche l'aide complète et des exemples concrets. |
| `/settings` | Centre de contrôle interactif (Modèle actif, niveau d'effort, mode d'approbation, langue). |
| `/usage` ou `/quota` | Jauge graphique des quotas (Flash, Pro, Claude), compte à rebours de reset, test de connexion. |
| `/models` | Sélecteur visuel de modèles IA autorisés sur votre compte Google. |
| `/effort` | Règle l'intensité de réflexion (*auto, low, medium, high, max*). |
| `/mode` | Règle le mode d'exécution (*auto-approve, accept-edits, plan*). |
| `/agents` | Gestion de l'essaim multi-agents (création, activation, export zip, import). |
| `/tasks` ou `/schedule` | Gestionnaire de tâches planifiées, rappels et automatisations récurrentes. |
| `/memory` | Recherche sémantique dans la mémoire à long terme. |
| `/remember <fait>` | Enregistre manuellement et immédiatement un fait en mémoire permanente. |
| `/forget <id>` | Supprime une information devenue obsolète de la base mémoire. |
| `/mcp` | Inspecteur des serveurs MCP connectés et de leurs outils. |
| `/plugins` | Gestionnaire des plugins Antigravity CLI officiels et communautaires. |
| `/workspace` | Affiche ou modifie le dossier de travail courant sur la machine hôte. |
| `/status` | Métriques de santé : RAM, CPU, version du bot, uptime du démon. |
| `/clear` | Réinitialise le contexte de la discussion tout en conservant la mémoire permanente. |
| `/abort` | Annule immédiatement l'exécution en cours sur le serveur. |
| `/language` | Bascule la langue de l'interface (Français, Anglais, Espagnol, etc.). |
| `/update` | Recherche et applique les mises à jour logicielles avec backup automatique. |

### Gestion Multimédia Bidirectionnelle
- **Envoi de documents / code** : Déposez n'importe quel fichier source, script, PDF ou archive ZIP dans Telegram. L'IA l'ingère, le lit et peut travailler dessus immédiatement.
- **Photos et captures d'écran** : Envoyez une capture d'écran d'un bug ou d'une maquette UI ; l'IA analyse visuellement l'image et propose le code correctif.
- **Messages vocaux** : Envoyez un mémo vocal Telegram quand vous marchez dans la rue ; le bot transcrit votre voix et traite votre demande sans que vous ayez à taper un seul mot.
- **Réception de fichiers** : Dès que l'IA génère un livrable (export PDF, image générée, archive ZIP, script compilé), elle utilise l'utilitaire `tg_send.py` pour vous envoyer le fichier directement dans la discussion.

---

## 5. Comment Parler à l'IA pour un Résultat Optimal ?

### Principes d'Ingénierie de Prompt
Pour tirer 100% de la puissance d'Antigravity Telegram Agent :

1. **Soyez précis sur l'objectif et les contraintes** :
   *Moins efficace :* "Fais-moi un script python pour scraper un site."  
   *Très efficace :* "Écris un script Python avec `playwright` pour extraire les titres et prix de cette page en gérant la pagination. Sauvegarde le résultat en JSON dans `workspace/output.json` et teste le script."

2. **Déléguez la vérification à l'IA** :
   L'agent a accès au terminal ! Demandez-lui toujours de vérifier ce qu'il vient de faire :
   > *"Implémente la fonction de calcul de taxe dans `tax.py` et lance la suite de tests avec `pytest tests/test_tax.py` pour confirmer que tout est vert."*

3. **Utilisez les bons modes de commande** :
   - Vous démarrez un gros projet de zéro ? Commencez par `/plan Développe une API FastAPI avec auth JWT`.
   - Vous hésitez sur l'architecture ? Tapez `/grill_me Système de réservation en ligne` pour qu'il vous interviewe.
   - Vous voulez qu'il travaille en totale autonomie jusqu'au bout ? Tapez `/goal Migre la base SQLite vers PostgreSQL et valide tous les tests`.
   - Vous faites face à un bug très complexe et obscur ? Tapez `/boost Pourquoi ce deadlock se produit dans le worker Celery ?`.

---

## 6. Comment Personnaliser Intégralement le Système ?

### 1. Personnaliser les Subagents Spécialisés
Créez un fichier Markdown dans `.agents/agents/<nom_expert>.md` avec ce format :

```markdown
---
name: devops_master
description: Expert en Docker, Kubernetes, Nginx, CI/CD et sécurité Linux.
model: gemini-2.5-pro
tools: [run_command, read_file, write_file, edit_file]
skills: [bash-pro, docker-mastery]
---
Tu es un ingénieur DevOps senior d'élite.
Tu privilégies toujours des scripts idempotent, la sécurité par défaut et une gestion rigoureuse des logs.
```
Dès la sauvegarde, l'agent est immédiatement disponible et invocable via `/agents` ou par délégation automatique.

### 2. Personnaliser les Commandes Slash (`custom_commands.json`)
Vous pouvez définir vos propres raccourcis personnalisés directement dans `custom_commands.json` :

```json
{
  "audit": {
    "description": "Lance un audit de sécurité complet du workspace",
    "template": "[AUDIT DE SÉCURITÉ]\nAnalyse le code du projet, cherche les vulnérabilités OWASP, les fuites de tokens et les failles de logique :\n{prompt}",
    "overrides": {
      "mode": "auto-approve",
      "effort": "high"
    }
  }
}
```
Vous pouvez désormais taper `/audit mon_projet` sur Telegram !

### 3. Personnaliser la Mémoire, Profils et Règles de Politesse (`mem.py`)

#### Enseigner des Règles de Savoir-Vivre et de Tonalité
Vous pouvez dicter précisément à l'IA la manière de s'adresser à chaque personne :
```bash
# Définir l'administrateur principal (tutoiement direct et technique)
python mem.py person add "Ange" --role "Fondateur & Dev Lead" --relation "Propriétaire" --tone "Tutoiement direct, concis, amical et technique" --aliases "ange,admin"

# Définir un client ou partenaire (vouvoiement formel et très courtois)
python mem.py person add "M. Martin" --role "Directeur Financier" --relation "Client" --tone "Vouvoiement très courtois, soigné et formel"
```

#### Enregistrer des Relations Humaines
```bash
python mem.py relate "Ange" "travaille avec" "Marc" --details "Marc gère le design frontend"
```

#### Fixer des Règles Permanentes
```bash
python mem.py add "Ne jamais déployer en production le vendredi après 16h." --category rules --key "deploy_rule"
python mem.py add "L'adresse IP du serveur de staging est 192.168.1.50." --category infra --key "ip_staging"
```

---

## 7. Cas d'Usage Réels et Possibilités

1. **Développement Mobile en Déplacement** : Vous êtes dans le train, vous recevez une notification de bug sur votre application. Vous demandez au bot d'inspecter le dépôt git, de reproduire l'erreur avec un test unitaire, de corriger le code et de pousser une branche de fix, tout cela depuis votre téléphone.
2. **Surveillance & Maintenance Serveur Autonome** : Le bot exécute une tâche planifiée toutes les 4 heures pour vérifier l'espace disque, la charge CPU et la validité des certificats SSL Let's Encrypt de votre parc de serveurs. En cas d'anomalie, il vous prévient instantanément avec les logs correspondants.
3. **Veille Technologique & Synthèse Quotidienne** : Tous les matins à 08h00, l'agent recherche les actualités majeures sur l'IA et le développement, fait un résumé exécutif et vous l'envoie en mémo texte structuré sur Telegram.
4. **Génération & Livraison de Rapports PDF** : Vous demandez au bot d'extraire les statistiques de votre base de données, de compiler un document d'analyse au format PDF et de vous le renvoyer directement sous forme de document téléchargeable dans la discussion.

---

## 8. Dépannage & Bonnes Pratiques

- **Le bot ne répond plus à mes messages ?**  
  Vérifiez que votre identifiant Telegram correspond bien à la variable `ALLOWED_USER_ID` du fichier `.env`. Si vous n'avez pas renseigné cette variable, le premier utilisateur qui tape `/start` s'approprie automatiquement le rôle d'administrateur.
- **Erreur de Quota Claude ("ResourceExhausted") ?**  
  Le bot bascule automatiquement vers Gemini. Tapez `/usage` pour voir le temps restant avant la réinitialisation de vos crédits Claude, puis cliquez sur `[🔄 Réinitialiser les verrous de cooldown]` une fois le délai écoulé.
- **Une tâche tourne en boucle ?**  
  Tapez simplement `/abort` pour forcer l'arrêt immédiat du processus de travail actif.
- **Envie de nettoyer l'écran sans perdre les réglages ?**  
  Tapez `/clear` : l'historique de la conversation immédiate est réinitialisé pour libérer la mémoire vive et repartir sur des bases saines, mais toutes vos données stockées dans la base de mémoire permanente (`memory.db`) restent intactes.

---
*Document généré pour Antigravity Telegram Agent v5.1.*
