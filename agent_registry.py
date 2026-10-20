"""
agent_registry.py - Native Antigravity Subagent Team Registry
Manages specialized subagents stored as markdown files in `.agents/agents/*.md`.
Supports listing, creating, editing, deleting, toggling, exporting, and importing
subagent definitions with strict security validation and tool safety controls.
"""

import os
import re
import sys
import yaml
import json
import shutil
import zipfile
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import config
from config import BASE_DIR

logger = logging.getLogger("agent_registry")

AGENTS_DIR = BASE_DIR / ".agents" / "agents"
AGENTS_DIR.mkdir(parents=True, exist_ok=True)

# Curated safe tools list allowed for subagents
SAFE_TOOLS_WHITELIST = {
    "run_command",
    "view_file",
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
    "sed_file",
    "list_dir",
    "find_by_name",
    "grep_search",
    "search_web",
    "read_url_content",
    "generate_image",
    "call_mcp_tool",
    "list_resources",
    "read_resource",
    "open_browser_url",
    "read_browser_page",
    "capture_browser_screenshot",
    "send_message",
    "manage_task",
    "schedule",
    "wait",
}

DEFAULT_SEED_AGENTS: List[Dict[str, Any]] = [
    {
        "name": "recherche",
        "display_name": "🔍 Recherche & Documentation",
        "description": "Spécialiste de la recherche web, de l'analyse documentaire et de la synthèse d'informations fiables.",
        "model": "gemini-3.8-flash-low",
        "tools": ["search_web", "read_url_content", "view_file"],
        "enabled": True,
        "instructions": (
            "Tu es un agent d'exploration et de recherche documentaire de haut niveau.\n"
            "Ta mission : chercher, recouper les sources fiables, extraire les faits essentiels "
            "et fournir une synthèse claire, dense et vérifiée à l'orchestrateur.\n"
            "Ne divague pas, concentre-toi exclusivement sur la mission transmise."
        ),
    },
    {
        "name": "code",
        "display_name": "💻 Code & Architecture",
        "description": "Expert en développement logiciel (Python, JS, Bash, C/C++), refactoring, débogage et tests unitaires.",
        "model": "gemini-4-argon-medium",
        "tools": [
            "run_command",
            "view_file",
            "write_to_file",
            "replace_file_content",
            "list_dir",
            "grep_search",
        ],
        "enabled": True,
        "instructions": (
            "Tu es un ingénieur logiciel et architecte expert.\n"
            "Ta mission : concevoir, écrire du code propre, modulaire et robuste, corriger les bugs, "
            "et exécuter les tests pour valider le bon fonctionnement avant de rendre ton rapport.\n"
            "Sois concis, précis et concentre-toi sur la solution technique optimale."
        ),
    },
    {
        "name": "maker_3d",
        "display_name": "📐 3D, Électronique & Maker",
        "description": "Spécialiste en modélisation 3D (OpenSCAD, STL), projets makers, Arduino, Raspberry Pi et ESP32.",
        "model": "gemini-3.8-flash-medium",
        "tools": [
            "run_command",
            "view_file",
            "write_to_file",
            "search_web",
            "read_url_content",
        ],
        "enabled": True,
        "instructions": (
            "Tu es un expert en modélisation 3D, impression 3D et électronique embarquée (ESP32, Arduino, Raspberry Pi).\n"
            "Ta mission : concevoir des pièces en OpenSCAD, calculer les cotes et tolérances avec exactitude, "
            "et définir les schémas de câblage et scripts nécessaires pour fabriquer des prototypes fonctionnels."
        ),
    },
]


class AgentRegistry:
    """
    Manages Antigravity subagent definition files (.agents/agents/*.md).
    """

    def __init__(self, agents_dir: Path = AGENTS_DIR):
        self.agents_dir = agents_dir
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_seed_agents()

    def _ensure_seed_agents(self) -> None:
        """Seed default agents if the agents directory is empty."""
        try:
            existing = list(self.agents_dir.glob("*.md"))
            if not existing:
                for agent in DEFAULT_SEED_AGENTS:
                    self.save_agent(
                        name=agent["name"],
                        meta={
                            "name": agent["name"],
                            "display_name": agent["display_name"],
                            "description": agent["description"],
                            "model": agent.get("model", "auto"),
                            "tools": agent.get("tools", []),
                            "enabled": agent.get("enabled", True),
                        },
                        instructions=agent["instructions"],
                    )
                logger.info("Initialized default subagent team in .agents/agents/")
        except Exception as e:
            logger.warning(f"Could not seed default agents: {e}")

    def list_agents(self, include_disabled: bool = True) -> List[Dict[str, Any]]:
        """List all registered subagents with parsed metadata."""
        agents: List[Dict[str, Any]] = []
        for file in sorted(self.agents_dir.glob("*.md")):
            try:
                agent_data = self._read_agent_file(file)
                if agent_data:
                    if include_disabled or agent_data.get("enabled", True):
                        agents.append(agent_data)
            except Exception as e:
                logger.debug(f"Error reading agent file {file}: {e}")
        return agents

    def get_agent(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific agent by name."""
        clean_name = self._sanitize_name(name)
        file = self.agents_dir / f"{clean_name}.md"
        if file.is_file():
            return self._read_agent_file(file)
        return None

    def save_agent(self, name: str, meta: Dict[str, Any], instructions: str) -> Tuple[bool, str]:
        """
        Save or update an agent file with YAML frontmatter + Markdown body.
        """
        clean_name = self._sanitize_name(name or meta.get("name", ""))
        if not clean_name:
            return False, "Nom d'agent invalide (doit contenir au moins un caractère alphanumérique)."

        meta_clean = {
            "name": clean_name,
            "display_name": meta.get("display_name", clean_name).strip() or clean_name,
            "description": meta.get("description", "").strip() or f"Sous-agent spécialisé {clean_name}",
            "model": meta.get("model", "auto").strip() or "auto",
            "tools": [t.strip() for t in meta.get("tools", []) if t.strip() in SAFE_TOOLS_WHITELIST],
            "enabled": bool(meta.get("enabled", True)),
        }

        content = self._render_agent_markdown(meta_clean, instructions.strip())
        target_file = self.agents_dir / f"{clean_name}.md"
        try:
            target_file.write_text(content, encoding="utf-8")
            logger.info(f"Subagent '{clean_name}' saved to {target_file}")
            return True, f"Agent '{clean_name}' enregistré avec succès."
        except Exception as e:
            logger.error(f"Failed to write agent file {target_file}: {e}")
            return False, f"Erreur lors de l'enregistrement de l'agent : {e}"

    def toggle_agent(self, name: str) -> Optional[bool]:
        """Toggle an agent between enabled and disabled."""
        agent = self.get_agent(name)
        if not agent:
            return None
        current_state = agent.get("enabled", True)
        new_state = not current_state
        agent["enabled"] = new_state
        ok, _ = self.save_agent(name, agent, agent.get("instructions", ""))
        return new_state if ok else None

    def delete_agent(self, name: str) -> bool:
        """Delete an agent definition file."""
        clean_name = self._sanitize_name(name)
        file = self.agents_dir / f"{clean_name}.md"
        if file.is_file():
            try:
                file.unlink()
                logger.info(f"Subagent '{clean_name}' deleted.")
                return True
            except Exception as e:
                logger.error(f"Failed to delete agent {clean_name}: {e}")
        return False

    def export_agent_file(self, name: str) -> Optional[Path]:
        """Return the path to the agent's markdown file for sending via Telegram."""
        clean_name = self._sanitize_name(name)
        file = self.agents_dir / f"{clean_name}.md"
        if file.is_file():
            return file
        return None

    def export_all_agents_zip(self) -> Optional[Path]:
        """Pack all agents into a zip archive for backup or export."""
        agents = list(self.agents_dir.glob("*.md"))
        if not agents:
            return None
        zip_path = config.TEMP_DIR / f"antigravity_agent_team_{int(asyncio_time())}.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for agent_file in agents:
                    zf.write(agent_file, arcname=agent_file.name)
            return zip_path
        except Exception as e:
            logger.error(f"Error creating agents zip: {e}")
            return None

    def import_agent_file(self, file_path: Path) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Import an agent from a .md file or a .zip archive.
        Validates frontmatter and sanitizes tool lists against dangerous tools.
        """
        if not file_path.exists():
            return False, "Fichier d'agent introuvable.", None

        ext = file_path.suffix.lower()
        if ext == ".zip":
            # Extract and import each .md
            imported_count = 0
            extract_dir = config.TEMP_DIR / f"import_{int(asyncio_time())}"
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    zf.extractall(extract_dir)
                for md_file in extract_dir.glob("*.md"):
                    ok, _, _ = self.import_agent_file(md_file)
                    if ok:
                        imported_count += 1
                shutil.rmtree(extract_dir, ignore_errors=True)
                if imported_count > 0:
                    return True, f"✅ {imported_count} agent(s) importé(s) avec succès depuis l'archive.", None
                return False, "Aucun fichier d'agent .md valide trouvé dans l'archive.", None
            except Exception as e:
                return False, f"Erreur lors de l'ouverture de l'archive ZIP : {e}", None

        if ext != ".md":
            return False, "Format de fichier non pris en charge (seuls .md et .zip sont acceptés).", None

        try:
            content = file_path.read_text(encoding="utf-8")
            parsed = self._parse_agent_markdown(content)
            if not parsed:
                return False, "Format de frontmatter YAML invalide ou manquant dans le fichier .md.", None

            meta, instructions = parsed
            name = meta.get("name") or file_path.stem
            clean_name = self._sanitize_name(name)
            if not clean_name:
                return False, "Nom d'agent invalide dans le fichier.", None

            # Filter unsafe tools
            requested_tools = meta.get("tools", [])
            safe_tools = [t for t in requested_tools if t in SAFE_TOOLS_WHITELIST]
            meta["tools"] = safe_tools

            ok, msg = self.save_agent(clean_name, meta, instructions)
            if ok:
                agent_info = self.get_agent(clean_name)
                return True, f"Agent '{clean_name}' importé avec succès !", agent_info
            return False, msg, None

        except Exception as e:
            logger.error(f"Error importing agent file {file_path}: {e}")
            return False, f"Erreur lors de l'import : {e}", None

    def get_orchestrator_subagents_prompt(self) -> str:
        """
        Generate the concise dynamic subagent team prompt injected into the orchestrator.
        Enforces:
        - Delegation with reformulated clear missions.
        - Direct response for simple conversational messages.
        - Gathering outputs and composing the final response.
        """
        agents = self.list_agents(include_disabled=False)
        if not agents:
            return ""

        lines = [
            "[ÉQUIPE DE SOUS-AGENTS SPÉCIALISÉS (ORCHESTRATION)]",
            "Tu es l'ORCHESTRATEUR principal. Tu as sous tes ordres une équipe de sous-agents spécialisés :",
        ]

        for ag in agents:
            name = ag.get("name", "")
            dname = ag.get("display_name", name)
            desc = ag.get("description", "")
            model = ag.get("model", "auto")
            tools = ", ".join(ag.get("tools", [])) or "aucun outil spécifique"
            lines.append(f"• `{name}` ({dname}) : {desc} [Modèle: {model} | Outils: {tools}]")

        lines.extend([
            "",
            "RÈGLES D'ORCHESTRATION STRICTES :",
            "1. RÉPONSE DIRECTE : Pour les questions simples, salutations ou demandes ne nécessitant pas d'expertise poussée,",
            "   réponds DIRECTEMENT sans invoquer de sous-agent ni utiliser d'outil superflu (gain de vitesse maximal).",
            "2. DÉLÉGATION STRUCTURÉE : Pour les tâches complexes, de recherche, de code ou multi-étapes :",
            "   - Reformule une MISSION CLAIRE et DÉTAILLÉE pour le sous-agent adéquat via `invoke_subagent` ou `define_subagent`.",
            "   - Enchaîne les sous-agents si besoin (ex: Recherche d'abord, puis Code ou Modélisation 3D).",
            "3. SYNTHÈSE FINALE : Ne laisse jamais un sous-agent s'adresser directement à l'utilisateur.",
            "   Tu dois TOUJOURS recueillir leurs résultats, les vérifier, et rédiger TOI-MÊME la réponse finale élégante et complète.",
        ])

        return "\n".join(lines)

    def migrate_from_custom_experts(self, experts_file: Path = BASE_DIR / "custom_experts.json") -> int:
        """Migrate legacy custom_experts.json to native .agents/agents/*.md."""
        if not experts_file.is_file():
            return 0
        migrated = 0
        try:
            data = json.loads(experts_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for name, exp in data.items():
                    clean_name = self._sanitize_name(name)
                    target = self.agents_dir / f"{clean_name}.md"
                    if not target.exists():
                        meta = {
                            "name": clean_name,
                            "display_name": exp.get("display_name", clean_name),
                            "description": exp.get("role", "") or exp.get("domain", ""),
                            "model": "auto",
                            "tools": ["search_web", "view_file"],
                            "enabled": exp.get("enabled", True),
                        }
                        instr = exp.get("system_prompt", f"Tu es un expert spécialisé en {clean_name}.")
                        self.save_agent(clean_name, meta, instr)
                        migrated += 1
            if migrated > 0:
                logger.info(f"Successfully migrated {migrated} legacy experts to .agents/agents/*.md")
        except Exception as e:
            logger.warning(f"Failed migrating custom_experts.json: {e}")
        return migrated

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize an agent identifier to be safe for filenames and CLI flags."""
        s = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(name).strip().lower())
        s = re.sub(r"_+", "_", s).strip("_")
        return s[:32]

    @staticmethod
    def _parse_agent_markdown(text: str) -> Optional[Tuple[Dict[str, Any], str]]:
        """Parse YAML frontmatter and markdown body from an agent definition file."""
        text = text.strip()
        if not text.startswith("---"):
            return None
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None
        frontmatter_str = parts[1].strip()
        body = parts[2].strip()
        try:
            meta = yaml.safe_load(frontmatter_str)
            if isinstance(meta, dict):
                return meta, body
        except Exception:
            pass
        return None

    @staticmethod
    def _render_agent_markdown(meta: Dict[str, Any], instructions: str) -> str:
        """Render metadata and instructions into a clean markdown file with YAML frontmatter."""
        frontmatter = yaml.dump(meta, sort_keys=False, allow_unicode=True).strip()
        return f"---\n{frontmatter}\n---\n\n{instructions}\n"

    def _read_agent_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Read and parse an agent markdown file into a structured dictionary."""
        try:
            content = file_path.read_text(encoding="utf-8")
            parsed = self._parse_agent_markdown(content)
            if not parsed:
                return None
            meta, instructions = parsed
            clean_name = self._sanitize_name(meta.get("name") or file_path.stem)
            meta.setdefault("name", clean_name)
            meta.setdefault("display_name", meta.get("name", clean_name))
            meta.setdefault("description", f"Sous-agent spécialisé {clean_name}")
            meta.setdefault("model", "auto")
            meta.setdefault("tools", [])
            meta.setdefault("enabled", True)
            meta["file_path"] = str(file_path.resolve())
            meta["instructions"] = instructions
            return meta
        except Exception as e:
            logger.debug(f"Error reading agent file {file_path}: {e}")
            return None


def asyncio_time() -> float:
    try:
        import asyncio
        return asyncio.get_event_loop().time()
    except Exception:
        import time
        return time.time()


agent_registry = AgentRegistry()
