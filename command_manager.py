"""
command_manager.py - Dynamic Telegram Bot Command Manager for Antigravity Agent
Enables the AI agent and the user to create, list, execute, and delete custom Telegram commands.
Automatically synchronizes with Telegram's Bot API (set_my_commands) so commands appear in the menu.
Includes full support for Antigravity CLI workflows (/goal, /grill_me, /plan, /boost, /teamwork).
"""

import sys
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from config import CUSTOM_COMMANDS_FILE

logger = logging.getLogger("command_manager")

# Telegram Bot API strict command name requirement: 1-32 characters, a-z, 0-9, underscore
COMMAND_NAME_REGEX = re.compile(r"^[a-z0-9_]{1,32}$")

# Built-in system commands protected from modification or deletion
PROTECTED_SYSTEM_COMMANDS: Dict[str, str] = {
    "start": "Démarrer l'agent Antigravity",
    "help": "Guide complet des commandes et fonctionnalités",
    "settings": "Centre de contrôle interactif (Modèle, Effort, Mode, MCP...)",
    "status": "Statut système, CLI, tokens et ressources",
    "models": "Choisir le modèle IA en direct (agy models)",
    "effort": "Régler le niveau de réflexion (low, medium, high, xhigh, max)",
    "mode": "Changer le mode d'exécution (Autonome, Standard, Plan)",
    "agents": "Gérer le mode Multi-Agents & les sous-agents",
    "sessions": "Historique des conversations & reprise de session",
    "mcp": "Gérer les serveurs MCP d'Antigravity CLI",
    "plugins": "Gérer les plugins d'Antigravity CLI",
    "remote": "Contrôler le démon Remote Control d'Antigravity",
    "workspace": "Changer ou inspecter le dossier de travail",
    "commands": "Créer ou gérer des commandes Telegram personnalisées",
    "memory": "Explorer la mémoire long-terme vectorielle (Mem0)",
    "remember": "Mémoriser un fait permanent dans Mem0",
    "forget": "Oublier un souvenir par son ID",
    "clear": "Démarrer une nouvelle conversation vierge",
    "abort": "Interrompre immédiatement la tâche en cours",
    "services": "État de santé du système et des services",
    "autoheal": "Surveillance autonome des logs & Auto-Heal IA",
    "users": "Gérer les utilisateurs et permissions",
    "update": "Vérifier et installer les mises à jour GitHub & Antigravity CLI",
    "update_cli": "Mettre à jour Antigravity CLI vers la dernière version",
}

DEFAULT_CUSTOM_COMMANDS: Dict[str, Dict[str, Any]] = {
    "goal": {
        "description": "Exécuter une tâche autonome approfondie jusqu'à complétion totale",
        "template": (
            "[OBJECTIF AUTONOME / LONG-RUNNING GOAL]\n"
            "Tu es en mode autonome approfondi (/goal). Accomplis cette tâche de manière exhaustive, "
            "méthodique, vérifie chaque étape, teste ton travail et ne t'arrête que lorsque l'objectif "
            "est 100% atteint.\n\n"
            "Demande / Objectif :\n{prompt}"
        ),
        "overrides": {
            "mode": "auto-approve",
            "effort": "high",
            "timeout": 0,
            "multi_agent": True,
        },
        "created_by": "system",
    },
    "grill_me": {
        "description": "Concevoir et cadrer un projet via un entretien interactif pas-à-pas",
        "template": (
            "[MODE ENTRETIEN & CONCEPTION / GRILL-ME]\n"
            "L'utilisateur souhaite concevoir ou cadrer un projet. "
            "Pose des questions ciblées, explore l'arborescence des choix techniques, "
            "propose tes recommandations argumentées et valide l'architecture avec l'utilisateur.\n\n"
            "Sujet du projet :\n{prompt}"
        ),
        "overrides": {
            "mode": "accept-edits",
            "effort": "medium",
        },
        "created_by": "system",
    },
    "plan": {
        "description": "Générer un plan d'architecture et d'implémentation détaillé étape par étape",
        "template": (
            "[MODE PLANIFICATION ARCHITECTURALE / PLAN]\n"
            "Analyse la demande ci-dessous et élabore un plan d'action structuré, complet et vérifiable "
            "avant toute modification majeure.\n\n"
            "Sujet :\n{prompt}"
        ),
        "overrides": {
            "mode": "plan",
            "effort": "high",
        },
        "created_by": "system",
    },
    "boost": {
        "description": "Activer la réflexion maximale (max effort) et la vérification multi-perspectives",
        "template": (
            "[MODE BOOST / RÉFLEXION MAXIMALE & VÉRIFICATION RIGOUREUSE]\n"
            "Mobilise une réflexion approfondie, examine le problème sous plusieurs angles, "
            "utilise des sous-agents de recherche si pertinent et vérifie rigoureusement chaque résultat.\n\n"
            "Problème / Mission :\n{prompt}"
        ),
        "overrides": {
            "mode": "auto-approve",
            "effort": "max",
            "multi_agent": True,
            "timeout": 0,
        },
        "created_by": "system",
    },
    "teamwork": {
        "description": "Orchestrer une équipe de sous-agents autonomes en parallèle sur un projet",
        "template": (
            "[MODE MULTI-AGENTS / TEAMWORK ORCHESTRATION]\n"
            "Pour accomplir cette mission complexe, décompose le travail et utilise tes outils de sous-agents "
            "(`invoke_subagent`, `define_subagent`, `manage_subagents`, `send_message`) afin de déléguer "
            "la recherche, l'implémentation et la vérification en parallèle, puis synthétise le résultat final.\n\n"
            "Mission d'équipe :\n{prompt}"
        ),
        "overrides": {
            "mode": "auto-approve",
            "effort": "high",
            "multi_agent": True,
            "timeout": 0,
        },
        "created_by": "system",
    },
}


class CommandManager:
    def __init__(self, filepath: Path = CUSTOM_COMMANDS_FILE):
        self.filepath = filepath
        self.commands: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.commands = json.load(f)
                updated = False
                for k, v in DEFAULT_CUSTOM_COMMANDS.items():
                    if k not in self.commands:
                        self.commands[k] = v.copy()
                        updated = True
                if updated:
                    self.save()
            except Exception as e:
                logger.error(f"Error loading custom commands from {self.filepath}: {e}")
                self.commands = {k: v.copy() for k, v in DEFAULT_CUSTOM_COMMANDS.items()}
        else:
            self.commands = {k: v.copy() for k, v in DEFAULT_CUSTOM_COMMANDS.items()}
            self.save()

    def save(self) -> None:
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.filepath.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.commands, f, indent=2, ensure_ascii=False)
            temp_path.replace(self.filepath)
        except Exception as e:
            logger.error(f"Error saving custom commands to {self.filepath}: {e}")

    @staticmethod
    def normalize_name(name: str) -> str:
        clean = name.strip().lstrip("/").lower()
        clean = clean.replace("-", "_")
        return clean

    def validate_name(self, name: str) -> Tuple[bool, str]:
        norm = self.normalize_name(name)
        if not norm:
            return False, "Le nom de commande ne peut pas être vide."
        if not COMMAND_NAME_REGEX.match(norm):
            return (
                False,
                f"Nom de commande '{norm}' invalide : 1 à 32 caractères alphanumériques ou underscore (_).",
            )
        if norm in PROTECTED_SYSTEM_COMMANDS:
            return False, f"'/{norm}' est une commande système protégée."
        return True, norm

    def add_command(
        self,
        name: str,
        description: str,
        template: str,
        overrides: Optional[Dict[str, Any]] = None,
        created_by: str = "user",
    ) -> Tuple[bool, str]:
        valid, norm_or_err = self.validate_name(name)
        if not valid:
            return False, norm_or_err

        norm_name = norm_or_err
        desc = description.strip()
        if not desc:
            return False, "La description de la commande ne peut pas être vide."
        if len(desc) > 256:
            desc = desc[:253] + "..."

        tpl = template.strip()
        if not tpl:
            return False, "Le template de prompt ne peut pas être vide."
        if "{prompt}" not in tpl:
            tpl += "\n\nDemande :\n{prompt}"

        self.commands[norm_name] = {
            "description": desc,
            "template": tpl,
            "overrides": overrides or {},
            "created_by": created_by,
        }
        self.save()
        logger.info(f"Custom command registered: /{norm_name} - {desc}")
        return True, f"Commande /{norm_name} enregistrée avec succès."

    def remove_command(self, name: str) -> Tuple[bool, str]:
        norm_name = self.normalize_name(name)
        if norm_name in PROTECTED_SYSTEM_COMMANDS:
            return False, f"Impossible de supprimer '/{norm_name}' : c'est une commande système protégée."

        if norm_name not in self.commands:
            return False, f"La commande '/{norm_name}' n'existe pas."

        del self.commands[norm_name]
        self.save()
        logger.info(f"Custom command removed: /{norm_name}")
        return True, f"Commande /{norm_name} supprimée avec succès."

    def get_command(self, name: str) -> Optional[Dict[str, Any]]:
        norm_name = self.normalize_name(name)
        return self.commands.get(norm_name)

    def list_commands(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.commands)

    def get_all_telegram_commands(self) -> List[Tuple[str, str]]:
        result: List[Tuple[str, str]] = []
        for name, desc in PROTECTED_SYSTEM_COMMANDS.items():
            result.append((name, desc[:256]))

        for name, data in self.commands.items():
            if name not in PROTECTED_SYSTEM_COMMANDS:
                result.append((name, data.get("description", "Commande personnalisée")[:256]))

        return result[:100]  # Telegram API limit is 100 commands

    def format_command_prompt(self, name: str, user_text: str) -> Tuple[str, Dict[str, Any]]:
        cmd_data = self.get_command(name)
        if not cmd_data:
            return user_text, {}

        template = cmd_data.get("template", "{prompt}")
        prompt_content = user_text.strip() or "(Aucun argument supplémentaire fourni)"
        enhanced = template.replace("{prompt}", prompt_content)
        overrides = cmd_data.get("overrides", {})
        return enhanced, overrides


command_mgr = CommandManager()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Antigravity Dynamic Telegram Commands Manager")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    subparsers.add_parser("list", help="List all custom and system commands")

    add_parser = subparsers.add_parser("add", help="Add or update a custom command")
    add_parser.add_argument("name", help="Command name (e.g. goal, grill_me)")
    add_parser.add_argument("description", help="Short description for Telegram menu")
    add_parser.add_argument("template", help="Prompt template (use {prompt} for argument)")
    add_parser.add_argument("--mode", choices=["auto-approve", "accept-edits", "plan"], help="Execution mode override")
    add_parser.add_argument("--effort", choices=["auto", "low", "medium", "high", "xhigh", "max"], help="Thinking effort override")
    add_parser.add_argument("--timeout", type=int, help="Timeout in seconds (0 = infinite)")

    rm_parser = subparsers.add_parser("remove", help="Remove a custom command")
    rm_parser.add_argument("name", help="Command name to remove")

    get_parser = subparsers.add_parser("get", help="Get details of a command")
    get_parser.add_argument("name", help="Command name")

    args = parser.parse_args()

    if args.action == "list":
        print("\n--- Commandes Système Protégées ---")
        for k, v in PROTECTED_SYSTEM_COMMANDS.items():
            print(f"/{k:15} : {v}")

        print("\n--- Commandes Personnalisées Dynamiques ---")
        cmds = command_mgr.list_commands()
        if not cmds:
            print("(Aucune commande personnalisée)")
        for k, v in cmds.items():
            overrides_str = f" [overrides: {v.get('overrides')}]" if v.get("overrides") else ""
            print(f"/{k:15} : {v['description']}{overrides_str}")
        print()

    elif args.action == "add":
        overrides = {}
        if args.mode:
            overrides["mode"] = args.mode
        if args.effort:
            overrides["effort"] = args.effort
        if args.timeout is not None:
            overrides["timeout"] = args.timeout

        ok, msg = command_mgr.add_command(args.name, args.description, args.template, overrides, created_by="cli")
        print(f"[{'OK' if ok else 'ERREUR'}] {msg}")
        sys.exit(0 if ok else 1)

    elif args.action == "remove":
        ok, msg = command_mgr.remove_command(args.name)
        print(f"[{'OK' if ok else 'ERREUR'}] {msg}")
        sys.exit(0 if ok else 1)

    elif args.action == "get":
        cmd = command_mgr.get_command(args.name)
        if cmd:
            print(json.dumps(cmd, indent=2, ensure_ascii=False))
        else:
            print(f"Commande '{args.name}' introuvable.")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
