"""
vault_manager.py - Antigravity Obsidian & Markdown Second Brain Manager
Manages notes, structured knowledge, and daily logs in the configured Vault directory.
Cross-platform compatible (Windows, Linux, macOS).
"""

import os
import re
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import VAULT_DIR


def get_vault_path() -> Path:
    env_p = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    p = Path(env_p) if env_p else VAULT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_notes(subfolder: str = "") -> List[Dict[str, Any]]:
    vault = get_vault_path()
    target_dir = vault / subfolder if subfolder else vault
    if not target_dir.exists():
        return []

    results = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in sorted(files):
            if f.endswith(".md") and not f.startswith("."):
                full_p = Path(root) / f
                rel_p = full_p.relative_to(vault)
                stat = full_p.stat()
                results.append({
                    "path": str(rel_p).replace("\\", "/"),
                    "name": f,
                    "size_bytes": stat.st_size,
                    "updated_at": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    return results


def read_note(note_path: str) -> Dict[str, Any]:
    vault = get_vault_path()
    p = vault / note_path
    if not p.suffix:
        p = p.with_suffix(".md")

    if not p.exists():
        matches = list(vault.glob(f"**/{note_path}*"))
        matches = [m for m in matches if m.is_file() and m.suffix == ".md" and not m.name.startswith(".")]
        if matches:
            p = matches[0]
        else:
            return {"error": f"Note '{note_path}' introuvable dans le coffre."}

    content = p.read_text(encoding="utf-8", errors="replace")
    tags = list(set(re.findall(r"(?<!\S)#([a-zA-Z0-9_\-]+)", content)))
    links = list(set(re.findall(r"\[\[(.*?)\]\]", content)))

    return {
        "path": str(p.relative_to(vault)).replace("\\", "/"),
        "name": p.name,
        "content": content,
        "tags": tags,
        "links": links,
        "updated_at": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def write_note(note_path: str, content: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    vault = get_vault_path()
    p = vault / note_path
    if not p.suffix:
        p = p.with_suffix(".md")

    p.parent.mkdir(parents=True, exist_ok=True)

    if tags:
        tag_str = " ".join([f"#{t.lstrip('#')}" for t in tags])
        if not any(f"#{t.lstrip('#')}" in content for t in tags):
            content = f"{content.rstrip()}\n\n---\n**Tags :** {tag_str}\n"

    p.write_text(content, encoding="utf-8")
    return {
        "path": str(p.relative_to(vault)).replace("\\", "/"),
        "size_bytes": len(content.encode("utf-8")),
        "status": "written",
    }


def append_to_daily_note(text: str) -> Dict[str, Any]:
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    vault = get_vault_path()
    daily_dir = vault / "02_Journal" / "Daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    daily_file = daily_dir / f"{date_str}.md"
    entry = f"\n### 🕒 {time_str}\n{text.strip()}\n"

    if not daily_file.exists():
        header = f"# 📅 Journal du {now.strftime('%d/%m/%Y')}\n\n"
        daily_file.write_text(header + entry, encoding="utf-8")
    else:
        with open(daily_file, "a", encoding="utf-8") as f:
            f.write(entry)

    return {
        "path": str(daily_file.relative_to(vault)).replace("\\", "/"),
        "time": time_str,
        "status": "appended",
    }


def search_notes(query: str) -> List[Dict[str, Any]]:
    query_lower = query.lower().strip()
    if not query_lower:
        return []
    notes = list_notes()
    results = []

    for item in notes:
        read_res = read_note(item["path"])
        if "error" in read_res:
            continue

        content = read_res["content"]
        name = item["name"]

        score = 0
        snippets = []

        if query_lower in name.lower():
            score += 10

        for i, line in enumerate(content.splitlines(), 1):
            if query_lower in line.lower():
                score += 1
                if len(snippets) < 3:
                    snippets.append(f"L{i}: {line.strip()}")

        if score > 0:
            results.append({
                "path": item["path"],
                "name": name,
                "score": score,
                "snippets": snippets,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def seed_vault_structure():
    vault = get_vault_path()
    p_welcome = vault / "00_System" / "Architecture_Agent.md"
    if not p_welcome.exists():
        write_note(
            "00_System/Architecture_Agent.md",
            """# 🤖 Antigravity Telegram Agent - Second Brain Vault

Ce coffre Markdown (Obsidian) stocke les notes, les projets et le journal quotidien de votre agent Antigravity.

## 🛠️ Composants Clés
1. **Passerelle Telegram (`bot.py`)** : Suivi en temps réel, gestion multimédia (images, vidéos, audio, documents) et centre de contrôle complet (`/settings`).
2. **Moteur Antigravity CLI (`agent_runner.py`)** : Compatible avec toutes les fonctionnalités d'Antigravity CLI (modèles dynamiques, sous-agents multi-agents, MCP, plugins, remote-control).
3. **Mémoire Vectorielle (`memory_manager.py`)** : Recherche sémantique locale rapide via FastEmbed.
4. **Coffre Markdown (`vault_manager.py`)** : Fiches de connaissances structurées et journal quotidien.

#antigravity #agent #vault #knowledge
""",
        )


if __name__ == "__main__":
    import sys
    seed_vault_structure()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "list":
            sub = sys.argv[2] if len(sys.argv) > 2 else ""
            notes = list_notes(sub)
            print(f"Notes in vault ({len(notes)}):")
            for n in notes:
                print(f"  📄 {n['path']} ({n['size_bytes']} bytes)")
        elif cmd == "read" and len(sys.argv) > 2:
            res = read_note(sys.argv[2])
            if "error" in res:
                print("Error:", res["error"])
            else:
                print(f"=== {res['path']} ===")
                print(res["content"])
        elif cmd == "write" and len(sys.argv) > 3:
            p = sys.argv[2]
            c = " ".join(sys.argv[3:])
            res = write_note(p, c)
            print(f"Wrote note: {res['path']}")
        elif cmd == "daily" and len(sys.argv) > 2:
            txt = " ".join(sys.argv[2:])
            res = append_to_daily_note(txt)
            print(f"Appended to daily note: {res['path']}")
        elif cmd == "search" and len(sys.argv) > 2:
            q = " ".join(sys.argv[2:])
            res = search_notes(q)
            print(f"Found {len(res)} matches for '{q}':")
            for r in res:
                print(f"  📄 {r['path']} (score: {r['score']})")
                for s in r["snippets"]:
                    print(f"     {s}")
    else:
        print("Vault manager ready. Notes count:", len(list_notes()))