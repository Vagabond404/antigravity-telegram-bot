"""
memory_manager.py - Antigravity Second Brain & Long-Term Memory (Mem0 / Vector Engine)
Powered by FastEmbed (BAAI/bge-small-en-v1.5) & Cross-Platform SQLite Vector Store.
- Persistent across chats, sessions, and reboots
- Dedicated categories: profile, preferences, projet, infra, rules, tools, general
- Smart key-based upsert + hybrid vector/keyword search + automatic fact capture
"""

import os
import re
import json
import sqlite3
import html
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import BASE_DIR, VAULT_DIR

try:
    from fastembed import TextEmbedding
    FASTEMBED_AVAILABLE = True
except ImportError:
    FASTEMBED_AVAILABLE = False

DB_PATH = str(BASE_DIR / "memory.db")
MODEL_NAME = "BAAI/bge-small-en-v1.5"

_embedder_cache = None


def get_embedder():
    global _embedder_cache
    if not FASTEMBED_AVAILABLE:
        return None
    if _embedder_cache is None:
        try:
            _embedder_cache = TextEmbedding(model_name=MODEL_NAME)
        except Exception as e:
            print(f"[MemoryManager] Warning: Failed to load embedder {MODEL_NAME}: {e}")
            _embedder_cache = None
    return _embedder_cache


def _compute_embedding_json(text: str) -> Optional[str]:
    embedder = get_embedder()
    if embedder is None:
        return None
    try:
        embeddings = list(embedder.embed([text]))
        if embeddings:
            return json.dumps(embeddings[0].tolist())
    except Exception as e:
        print(f"[MemoryManager] Embedding error: {e}")
    return None


def get_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")

    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memories';")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(memories);")
        cols = [r[1] for r in cur.fetchall()]
        migrations = [
            ("user_id", "ALTER TABLE memories ADD COLUMN user_id TEXT DEFAULT 'default';"),
            ("embedding", "ALTER TABLE memories ADD COLUMN embedding TEXT;"),
            ("category", "ALTER TABLE memories ADD COLUMN category TEXT DEFAULT 'general';"),
            ("key", "ALTER TABLE memories ADD COLUMN key TEXT DEFAULT '';"),
            ("tags", "ALTER TABLE memories ADD COLUMN tags TEXT DEFAULT '';"),
            ("related_to", "ALTER TABLE memories ADD COLUMN related_to TEXT DEFAULT '';"),
            ("importance", "ALTER TABLE memories ADD COLUMN importance INTEGER DEFAULT 3;"),
            ("updated_at", "ALTER TABLE memories ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"),
        ]
        for col_name, sql in migrations:
            if col_name not in cols:
                try:
                    conn.execute(sql)
                except Exception:
                    pass
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                key TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                related_to TEXT DEFAULT '',
                importance INTEGER DEFAULT 3,
                embedding TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_cat ON memories(category);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);")
    conn.commit()
    return conn


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def add_memory(
    content: str,
    category: str = "general",
    user_id: str = "default",
    key: Optional[str] = None,
    tags: str = "",
    related_to: str = "",
    importance: int = 3,
    db_path: str = DB_PATH,
) -> int:
    content = content.strip()
    if not content:
        return 0

    clean_key = (key or "").strip()
    clean_cat = (category or "general").strip().lower()
    if clean_cat in ("user_profile", "personal", "perso"):
        clean_cat = "profile"
    elif clean_cat in ("pref", "prefs", "preference"):
        clean_cat = "preferences"
    elif clean_cat in ("project", "projects", "projets"):
        clean_cat = "projet"

    conn = get_db(db_path)
    cur = conn.cursor()

    # 1. If a non-empty key is provided, upsert by key so project/profile updates replace old values
    if clean_key:
        cur.execute("SELECT id FROM memories WHERE key = ? AND key != ''", (clean_key,))
        row = cur.fetchone()
        if row:
            emb_json = _compute_embedding_json(f"[{clean_cat}] {clean_key}: {content}")
            cur.execute(
                """
                UPDATE memories
                SET content = ?, category = ?, tags = COALESCE(NULLIF(?, ''), tags),
                    related_to = COALESCE(NULLIF(?, ''), related_to),
                    importance = ?, embedding = COALESCE(?, embedding),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (content, clean_cat, tags, related_to, int(importance), emb_json, row[0]),
            )
            conn.commit()
            conn.close()
            return int(row[0])

    # 2. Otherwise check exact content match
    cur.execute("SELECT id FROM memories WHERE content = ?", (content,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE memories
            SET category = ?, key = COALESCE(NULLIF(?, ''), key),
                tags = COALESCE(NULLIF(?, ''), tags),
                importance = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (clean_cat, clean_key, tags, int(importance), row[0]),
        )
        conn.commit()
        conn.close()
        return int(row[0])

    embedding_json = _compute_embedding_json(f"[{clean_cat}] {clean_key}: {content}" if clean_key else content)

    cur.execute(
        """
        INSERT INTO memories (user_id, content, category, key, tags, related_to, importance, embedding)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, content, clean_cat, clean_key, tags or "", related_to or "", int(importance), embedding_json),
    )
    mem_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(mem_id or 0)


def search_memory(
    query: str,
    limit: int = 6,
    category: Optional[str] = None,
    user_id: Optional[str] = None,
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    query = query.strip()
    if not query:
        return []

    conn = get_db(db_path)
    cur = conn.cursor()
    if category:
        cur.execute(
            "SELECT id, content, category, key, tags, importance, embedding, created_at FROM memories WHERE category = ?",
            (category,),
        )
    else:
        cur.execute(
            "SELECT id, content, category, key, tags, importance, embedding, created_at FROM memories"
        )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return []

    embedder = get_embedder()
    query_emb = None
    if embedder is not None:
        try:
            q_list = list(embedder.embed([query]))
            if len(q_list) > 0:
                query_emb = np.array(q_list[0])
        except Exception as e:
            print(f"[MemoryManager] Query embedding error: {e}")

    results = []
    words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2]

    for row in rows:
        mem_id, content, cat, key, tags, importance, emb_str, created_at = row

        content_lower = f"{content} {key or ''} {tags or ''} {cat or ''}".lower()
        matched_words = [w for w in words if w in content_lower]
        keyword_score = len(matched_words) / max(len(words), 1) if words else 0.0

        vector_score = 0.0
        if query_emb is not None and emb_str:
            try:
                emb = np.array(json.loads(emb_str))
                vector_score = cosine_similarity(query_emb, emb)
            except Exception:
                pass

        if query_emb is not None and emb_str:
            score = (vector_score * 0.7) + (keyword_score * 0.3)
        else:
            score = keyword_score

        # Slight boost for high-importance memories
        imp_boost = max(0, (int(importance or 3) - 3)) * 0.03
        score += imp_boost

        results.append({
            "id": mem_id,
            "content": content,
            "category": cat,
            "key": key or "",
            "tags": tags or "",
            "importance": importance or 3,
            "score": round(float(score), 4),
            "created_at": created_at,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def list_memories(
    limit: int = 50,
    category: Optional[str] = None,
    user_id: Optional[str] = None,
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    conn = get_db(db_path)
    cur = conn.cursor()
    if category:
        cur.execute(
            "SELECT id, content, category, key, tags, importance, created_at, updated_at FROM memories WHERE category = ? ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (category, limit),
        )
    else:
        cur.execute(
            "SELECT id, content, category, key, tags, importance, created_at, updated_at FROM memories ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (limit,),
        )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "content": r[1],
            "category": r[2],
            "key": r[3] or "",
            "tags": r[4] or "",
            "importance": r[5] or 3,
            "created_at": r[6],
            "updated_at": r[7],
        }
        for r in rows
    ]


def list_memories_by_categories(categories: List[str], limit: int = 25, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    if not categories:
        return []
    conn = get_db(db_path)
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in categories)
    cur.execute(
        f"SELECT id, content, category, key, tags, importance, created_at, updated_at FROM memories WHERE category IN ({placeholders}) ORDER BY importance DESC, updated_at DESC LIMIT ?",
        (*categories, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "content": r[1],
            "category": r[2],
            "key": r[3] or "",
            "tags": r[4] or "",
            "importance": r[5] or 3,
            "created_at": r[6],
            "updated_at": r[7],
        }
        for r in rows
    ]


def delete_memory(memory_id: int, user_id: Optional[str] = None, db_path: str = DB_PATH) -> bool:
    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    affected = cur.rowcount > 0
    conn.commit()
    conn.close()
    return affected


def get_memory_graph(db_path: str = DB_PATH) -> Dict[str, Any]:
    mems = list_memories(limit=200, db_path=db_path)
    nodes = [{"id": m["id"], "category": m["category"], "key": m["key"], "content": m["content"]} for m in mems]
    return {"total_nodes": len(nodes), "nodes": nodes}


def add_or_update_memory(
    content: str,
    category: str = "general",
    key: Optional[str] = None,
    tags: str = "",
    related_to: str = "",
    importance: int = 3,
    user_id: str = "default",
) -> int:
    return add_memory(
        content=content,
        category=category,
        user_id=user_id,
        key=key,
        tags=tags,
        related_to=related_to,
        importance=importance,
    )


def search_memories(
    query: str,
    limit: int = 6,
    category: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return search_memory(query=query, limit=limit, category=category, user_id=user_id)


def auto_extract_and_store_facts(user_text: str) -> List[str]:
    """
    Automatically detect explicit user statements (personal info, preferences,
    explicit 'remember this' requests, or project notes) and persist them to SQLite
    immediately so nothing is ever lost between chats even if the LLM doesn't call mem.py.
    """
    if not user_text or len(user_text.strip()) < 6:
        return []
    text = user_text.strip()
    if text.startswith("/"):
        return []

    captured: List[str] = []

    # 1. Explicit memory commands in natural language ("retiens que...", "souviens-toi que...", "note que...")
    explicit_patterns = [
        (r"(?:retiens|souviens[- ]toi|n'oublie pas|garde en mémoire|mémorise)\s+(?:bien\s+)?(?:que\s+)?(.+)", "user_note", 5),
        (r"(?:je préfère|ma préférence est|j'aime quand tu)\s+(.+)", "preferences", 4),
        (r"(?:je m'appelle|mon prénom est|mon nom est)\s+([^\n.,!?;]{2,40})", "profile", 5),
        (r"(?:toujours répondre|réponds toujours|ne fais jamais)\s+(.+)", "rules", 5),
    ]

    for pat, cat, imp in explicit_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            fact = m.group(0).strip()
            if len(fact) <= 400:
                add_memory(content=fact, category=cat, importance=imp)
                captured.append(fact)
                break

    return captured


def get_summary_html(user_id: Optional[str] = None) -> str:
    mems = list_memories(limit=40, user_id=user_id)
    if not mems:
        return (
            "🧠 <b>Deuxième Cerveau & Mémoire Long-Terme (Mem0)</b>\n\n"
            "<i>Aucun souvenir stocké pour le moment.</i>\n\n"
            "💡 Utilisez <code>/remember &lt;information&gt;</code> ou dites simplement à l'agent "
            "<i>« Retiens que... »</i> pour mémoriser un fait permanent."
        )

    categories: Dict[str, List[Dict[str, Any]]] = {}
    for m in mems:
        cat = m["category"]
        categories.setdefault(cat, []).append(m)

    lines = ["🧠 <b>Deuxième Cerveau & Souvenirs Actifs (Mem0)</b>\n"]
    cat_icons = {
        "profile": "👤",
        "preferences": "⭐",
        "projet": "🚀",
        "infra": "🖥️",
        "rules": "📌",
        "user_note": "📝",
        "system": "🤖",
        "tools": "🔧",
        "vault": "📚",
        "general": "💡",
    }

    for cat, items in categories.items():
        icon = cat_icons.get(cat, "🔹")
        lines.append(f"{icon} <b>{html.escape(cat.upper())} :</b>")
        for it in items:
            key_badge = f" [<code>{html.escape(it['key'])}</code>]" if it.get("key") else ""
            lines.append(f"  • <code>#{it['id']}</code>{key_badge} {html.escape(it['content'])}")
        lines.append("")

    lines.append(
        "<i>💡 Commandes : <code>/memory &lt;recherche&gt;</code>, "
        "<code>/remember &lt;texte&gt;</code>, <code>/forget &lt;id&gt;</code>, <code>/vault</code></i>"
    )
    return "\n".join(lines)


def get_relevant_context(query: str, user_id: Optional[str] = None) -> str:
    """
    Build the complete Long-Term Memory & Second Brain context block injected into the Agent:
      1. Core User Profile, Preferences & Rules (always available across all chats)
      2. Active Projects & Infrastructure memories
      3. Semantic & Keyword matches for the current user prompt
      4. Structured Obsidian Markdown Vault notes (Projects index + matching snippets)
    """
    ctx_parts = []
    seen_contents = set()

    # 1. Core Profile, Preferences & Rules (Always injected)
    core_mems = list_memories_by_categories(
        ["profile", "user_profile", "preferences", "rules", "user_note"],
        limit=20,
    )
    core_lines = []
    for m in core_mems:
        if m["content"] not in seen_contents:
            k_str = f" ({m['key']})" if m.get("key") else ""
            core_lines.append(f"• [{m['category']}{k_str}] {m['content']}")
            seen_contents.add(m["content"])

    # 2. Projects & Infrastructure memories
    proj_mems = list_memories_by_categories(
        ["projet", "projects", "project", "infra"],
        limit=15,
    )
    proj_lines = []
    for m in proj_mems:
        if m["content"] not in seen_contents:
            k_str = f" ({m['key']})" if m.get("key") else ""
            proj_lines.append(f"• [{m['category']}{k_str}] {m['content']}")
            seen_contents.add(m["content"])

    # 3. Semantic / Keyword search across all other memories
    semantic_mems = search_memory(query, limit=6, user_id=user_id)
    sem_lines = []
    for m in semantic_mems:
        if m["score"] > 0.18 and m["content"] not in seen_contents:
            k_str = f" ({m['key']})" if m.get("key") else ""
            sem_lines.append(f"• [{m['category']}{k_str}] {m['content']}")
            seen_contents.add(m["content"])

    mem_sections = []
    if core_lines:
        mem_sections.append("👤 PROFIL, PRÉFÉRENCES & RÈGLES DE L'UTILISATEUR :\n" + "\n".join(core_lines))
    if proj_lines:
        mem_sections.append("🚀 PROJETS & INFRASTRUCTURE CONNUS :\n" + "\n".join(proj_lines))
    if sem_lines:
        mem_sections.append("🔍 SOUVENIRS PERTINENTS POUR CETTE DEMANDE :\n" + "\n".join(sem_lines))

    if mem_sections:
        ctx_parts.append("[🧠 MÉMOIRE LONG-TERME INTER-CONVERSATIONS (Mem0)]\n" + "\n\n".join(mem_sections))

    # 4. Obsidian Markdown Vault (Project notes index + search snippets)
    try:
        from vault_manager import list_notes, search_notes
        all_notes = list_notes()
        note_paths = [n["path"] for n in all_notes if not n["path"].startswith("00_System/")]
        v_results = search_notes(query)

        vault_lines = []
        if note_paths:
            vault_lines.append("Fiches Markdown disponibles dans le coffre : " + ", ".join(f"`{p}`" for p in note_paths[:15]))
        if v_results:
            for item in v_results[:3]:
                snippet_str = " | ".join(item["snippets"][:2])
                vault_lines.append(f"• Extrait de `{item['path']}` : {snippet_str}")
        if vault_lines:
            ctx_parts.append(f"[📚 COFFRE DE CONNAISSANCES OBSIDIAN ({VAULT_DIR})]\n" + "\n".join(vault_lines))
    except Exception:
        pass

    return "\n\n".join(ctx_parts)


def seed_default_memories():
    existing = list_memories(limit=5)
    if existing:
        return
    defaults = [
        ("Agent autonome propulsé par Google Antigravity CLI et piloté via Telegram.", "system", "agent_identity"),
        ("Règle d'affichage Telegram : Pendant l'exécution, le suivi s'affiche en direct. La réponse finale doit être propre, claire et bien structurée.", "rules", "display_rule"),
        ("Mémoire proactive : Toujours enregistrer les informations personnelles, préférences et détails des projets de l'utilisateur avec mem.py et vault_manager.py pour s'en souvenir entre les conversations.", "rules", "proactive_memory"),
    ]
    for text, cat, key in defaults:
        add_memory(text, category=cat, key=key, importance=4)


if __name__ == "__main__":
    import sys
    seed_default_memories()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "search" and len(sys.argv) > 2:
            q = " ".join(sys.argv[2:])
            res = search_memory(q)
            print(f"Results for '{q}':")
            for r in res:
                print(f"  [{r['score']}] (id={r['id']}, cat={r['category']}, key={r['key']}) {r['content']}")
        elif cmd == "list":
            for m in list_memories():
                print(f"  #{m['id']} [{m['category']}] ({m['key']}) {m['content']}")
        elif cmd == "add" and len(sys.argv) > 2:
            txt = " ".join(sys.argv[2:])
            mid = add_memory(txt)
            print(f"Added memory #{mid}: {txt}")
        elif cmd == "delete" and len(sys.argv) > 2:
            try:
                mid = int(sys.argv[2])
                ok = delete_memory(mid)
                print(f"Deleted memory #{mid}: {ok}")
            except ValueError:
                print("Invalid ID")
        elif cmd == "context" and len(sys.argv) > 2:
            q = " ".join(sys.argv[2:])
            print(get_relevant_context(q))
    else:
        print("Memory store ready. Count:", len(list_memories()))