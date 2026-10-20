"""
Unit tests for agent_registry.py
Verifies subagent team management, frontmatter serialization, import/export,
tool safety whitelisting, and legacy migration.
"""

import os
import shutil
import tempfile
from pathlib import Path
import pytest

from agent_registry import AgentRegistry, SAFE_TOOLS_WHITELIST


@pytest.fixture
def temp_registry():
    temp_dir = Path(tempfile.mkdtemp(prefix="agent_test_"))
    registry = AgentRegistry(agents_dir=temp_dir)
    yield registry
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_seed_default_agents(temp_registry):
    agents = temp_registry.list_agents(include_disabled=True)
    names = {a["name"] for a in agents}
    assert "recherche" in names
    assert "code" in names
    assert "maker_3d" in names
    assert len(agents) >= 3


def test_save_and_get_agent(temp_registry):
    meta = {
        "name": "physics_pro",
        "display_name": "⚛️ Expert Physique",
        "description": "Calculs de mécanique quantique et relativité",
        "model": "gemini-4-argon-medium",
        "tools": ["run_command", "view_file", "malicious_hack_tool"],
        "enabled": True,
    }
    instructions = "Tu es un physicien de renommée internationale."

    ok, msg = temp_registry.save_agent("physics_pro", meta, instructions)
    assert ok is True

    agent = temp_registry.get_agent("physics_pro")
    assert agent is not None
    assert agent["name"] == "physics_pro"
    assert agent["display_name"] == "⚛️ Expert Physique"
    assert agent["model"] == "gemini-4-argon-medium"
    assert "run_command" in agent["tools"]
    assert "view_file" in agent["tools"]
    # Unsafe tool must be filtered out by whitelist
    assert "malicious_hack_tool" not in agent["tools"]
    assert "Tu es un physicien" in agent["instructions"]


def test_toggle_agent(temp_registry):
    assert temp_registry.get_agent("recherche")["enabled"] is True
    new_state = temp_registry.toggle_agent("recherche")
    assert new_state is False
    assert temp_registry.get_agent("recherche")["enabled"] is False

    new_state = temp_registry.toggle_agent("recherche")
    assert new_state is True
    assert temp_registry.get_agent("recherche")["enabled"] is True


def test_delete_agent(temp_registry):
    assert temp_registry.get_agent("code") is not None
    ok = temp_registry.delete_agent("code")
    assert ok is True
    assert temp_registry.get_agent("code") is None


def test_export_and_import_agent_file(temp_registry):
    export_file = temp_registry.export_agent_file("maker_3d")
    assert export_file is not None
    assert export_file.is_file()

    # Create another registry in a fresh folder
    temp_dir2 = Path(tempfile.mkdtemp(prefix="agent_test_import_"))
    registry2 = AgentRegistry(agents_dir=temp_dir2)
    # Clear seeded agents to test clean import
    for f in temp_dir2.glob("*.md"):
        f.unlink()

    ok, msg, imported = registry2.import_agent_file(export_file)
    assert ok is True
    assert imported is not None
    assert imported["name"] == "maker_3d"
    assert imported["display_name"] == "📐 3D, Électronique & Maker"

    shutil.rmtree(temp_dir2, ignore_errors=True)


def test_export_all_zip(temp_registry):
    zip_path = temp_registry.export_all_agents_zip()
    assert zip_path is not None
    assert zip_path.is_file()
    assert zip_path.suffix.lower() == ".zip"
    zip_path.unlink(missing_ok=True)


def test_orchestrator_subagents_prompt(temp_registry):
    prompt = temp_registry.get_orchestrator_subagents_prompt()
    assert "[ÉQUIPE DE SOUS-AGENTS SPÉCIALISÉS (ORCHESTRATION)]" in prompt
    assert "recherche" in prompt
    assert "code" in prompt
    assert "maker_3d" in prompt
    assert "RÈGLES D'ORCHESTRATION STRICTES" in prompt


def test_migrate_from_custom_experts(temp_registry):
    temp_json = Path(tempfile.mktemp(suffix=".json"))
    temp_json.write_text("""
    {
        "biologist": {
            "display_name": "🧬 Biologiste Moléculaire",
            "domain": "Génomique",
            "role": "Analyse d'ADN et protéines",
            "system_prompt": "Tu es un expert en génomique.",
            "enabled": true
        }
    }
    """, encoding="utf-8")

    migrated = temp_registry.migrate_from_custom_experts(temp_json)
    assert migrated == 1

    bio = temp_registry.get_agent("biologist")
    assert bio is not None
    assert bio["display_name"] == "🧬 Biologiste Moléculaire"
    assert "génomique" in bio["instructions"].lower()

    temp_json.unlink(missing_ok=True)
