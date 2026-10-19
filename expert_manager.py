"""
expert_manager.py - Antigravity Custom Expert Subagents Manager
Allows creating, configuring, and persisting specialized AI subagents (Math, Code, English, Sciences, etc.)
that the main agent can autonomously invoke or consult.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from config import BASE_DIR

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger("expert_manager")

EXPERTS_FILE = BASE_DIR / "custom_experts.json"

DEFAULT_EXPERTS: Dict[str, Dict[str, Any]] = {}


class ExpertManager:
    """Manages custom expert subagents persisted in custom_experts.json."""

    def __init__(self, filepath: Path = EXPERTS_FILE):
        self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        if not self.filepath.exists():
            try:
                self.filepath.write_text(
                    json.dumps(DEFAULT_EXPERTS, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.error(f"Failed to create default experts file: {e}")

    def load_experts(self) -> Dict[str, Dict[str, Any]]:
        self._ensure_file()
        try:
            content = self.filepath.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.error(f"Error loading custom experts: {e}")
        return dict(DEFAULT_EXPERTS)

    def save_experts(self, data: Dict[str, Dict[str, Any]]) -> bool:
        try:
            self.filepath.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except Exception as e:
            logger.error(f"Error saving custom experts: {e}")
            return False

    def get_expert(self, name: str) -> Optional[Dict[str, Any]]:
        experts = self.load_experts()
        return experts.get(name)

    def add_or_update_expert(
        self,
        name: str,
        display_name: str,
        domain: str,
        role: str,
        system_prompt: str,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Create or update a specialized expert subagent."""
        name_clean = "".join(c if c.isalnum() or c in "_-" else "_" for c in name.strip().lower())
        if not name_clean:
            name_clean = "expert"

        experts = self.load_experts()
        entry = {
            "display_name": display_name.strip() or f"Expert {name_clean}",
            "domain": domain.strip() or "Domaine spécialisé",
            "role": role.strip() or f"Expert spécialisé en {domain}",
            "system_prompt": system_prompt.strip(),
            "enabled": enabled,
        }
        experts[name_clean] = entry
        self.save_experts(experts)
        return entry

    def toggle_expert(self, name: str) -> Optional[bool]:
        experts = self.load_experts()
        if name not in experts:
            return None
        current = experts[name].get("enabled", True)
        experts[name]["enabled"] = not current
        self.save_experts(experts)
        return not current

    def delete_expert(self, name: str) -> bool:
        experts = self.load_experts()
        if name in experts:
            del experts[name]
            self.save_experts(experts)
            return True
        return False

    def get_active_experts_prompt(self) -> str:
        """Generate prompt context describing available expert subagents."""
        experts = self.load_experts()
        active = {k: v for k, v in experts.items() if v.get("enabled", True)}
        if not active:
            return ""

        lines = [
            "\n[ÉQUIPE DE SOUS-AGENTS EXPERTS PERSONNALISÉS]",
            "Tu as sous ta direction une équipe de sous-agents experts hautement spécialisés configurés par l'utilisateur :",
        ]
        for name, exp in active.items():
            lines.append(
                f"- `{name}` ({exp.get('display_name', name)}) : {exp.get('role', '')} | Domaine : {exp.get('domain', '')}"
            )
            prompt_preview = exp.get("system_prompt", "").replace("\n", " ")
            if len(prompt_preview) > 200:
                prompt_preview = prompt_preview[:197] + "..."
            lines.append(f"  Instructions : \"{prompt_preview}\"")

        lines.extend([
            "",
            "DIRECTIVES D'UTILISATION DES SOUS-AGENTS EXPERTS :",
            "1. Lorsque l'utilisateur pose une question pointue relevant de l'un de ces domaines,",
            "   ou s'il demande expressément l'aide d'un expert ('demande au prof de maths', 'fais vérifier par l'expert code') :",
            "   - Tu peux soit invoquer ce sous-agent avec `define_subagent` et `invoke_subagent` pour une analyse approfondie,",
            "   - Soit adopter immédiatement la persona et la rigueur de cet expert pour répondre au plus haut niveau d'exigence.",
            "2. Pour créer ou modifier un agent expert (ex: 'Crée un agent expert en SVT'),",
            "   tu peux directement mettre à jour `custom_experts.json` ou utiliser le module `expert_manager.py`.",
        ])
        return "\n".join(lines)


expert_mgr = ExpertManager()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Antigravity Custom Expert Subagents CLI")
    sub = parser.add_subparsers(dest="command")

    # List
    sub.add_parser("list", help="List all configured expert subagents")

    # Add
    p_add = sub.add_parser("add", help="Add or update an expert subagent")
    p_add.add_argument("name", help="Identifier (e.g. physics_pro, history_scholar)")
    p_add.add_argument("--display", default="", help="Display name with icon")
    p_add.add_argument("--domain", default="", help="Domain of expertise")
    p_add.add_argument("--role", default="", help="Role description")
    p_add.add_argument("--prompt", required=True, help="Detailed system prompt / persona")

    # Toggle
    p_tog = sub.add_parser("toggle", help="Toggle expert enabled/disabled")
    p_tog.add_argument("name", help="Expert identifier")

    # Delete
    p_del = sub.add_parser("delete", help="Delete an expert")
    p_del.add_argument("name", help="Expert identifier")

    args = parser.parse_args()

    if args.command == "list" or not args.command:
        experts = expert_mgr.load_experts()
        print(f"\n🎓 Total Experts: {len(experts)}")
        for k, v in experts.items():
            st = "✅ Active" if v.get("enabled", True) else "❌ Inactive"
            print(f"- [{st}] {v.get('display_name', k)} (`{k}`)")
            print(f"    Domaine: {v.get('domain', '')}")
            print(f"    Rôle: {v.get('role', '')}")
        print()

    elif args.command == "add":
        entry = expert_mgr.add_or_update_expert(
            name=args.name,
            display_name=args.display or args.name,
            domain=args.domain or "Général",
            role=args.role or "Expert",
            system_prompt=args.prompt,
        )
        print(f"✅ Expert '{args.name}' registered successfully:\n{json.dumps(entry, indent=2)}")

    elif args.command == "toggle":
        res = expert_mgr.toggle_expert(args.name)
        if res is None:
            print(f"❌ Expert '{args.name}' not found.")
        else:
            print(f"✅ Expert '{args.name}' status is now: {'Active ✅' if res else 'Inactive ❌'}")

    elif args.command == "delete":
        ok = expert_mgr.delete_expert(args.name)
        if ok:
            print(f"✅ Expert '{args.name}' deleted.")
        else:
            print(f"❌ Expert '{args.name}' not found.")


if __name__ == "__main__":
    main()
