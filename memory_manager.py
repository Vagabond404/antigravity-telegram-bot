"""
memory_manager.py - Antigravity Second Brain & Long-Term Memory (Mem0 / Vector Engine)
Powered by FastEmbed (BAAI/bge-small-en-v1.5) & Cross-Platform SQLite Vector Store.
Zero cloud token cost, local on-device embeddings, sub-millisecond similarity search.
"""

import os
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

    conn = get_db(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM memories WHERE content = ?",
        (content,),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE memories SET category = ?, key = COALESCE(?, key), tags = COALESCE(?, tags), importance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (category, key or "", tags or "", importance, row[0]),
        )
        conn.commit()
        conn.close()
        return row[0]

    embedder = get_embedder()
    embedding_json = None
    if embedder is not None:
        try:
            embeddings = list(embedder.embed([content]))
            if len(embeddings) > 0:
                embedding_json = json.dumps(embeddings[0].tolist())
        except Exception as e:
            print(f"[MemoryManager] Embedding error: {e}")

    cur.execute(
        """
        INSERT INTO memories (user_id, content, category, key, tags, related_to, importance, embedding)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, content, category, key or "", tags or "", related_to or "", int(importance), embedding_json),
    )
    mem_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(mem_id or 0)


def search_memory(
    query: str,
    limit: int = 5,
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
    for row in rows:
        mem_id, content, cat, key, tags, importance, emb_str, created_at = row

        words = query.lower().split()
        content_lower = f"{content} {key or ''} {tags or ''}".lower()
        matched_words = [w for w in words if len(w) > 2 and w in content_lower]
        keyword_score = len(matched_words) / max(len(words), 1)

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
            "SELECT id, content, category, key, tags, importance, created_at, updated_at FROM memories WHERE category = ? ORDER BY updated_at DESC LIMIT ?",
            (category, limit),
        )
    else:
        cur.execute(
            "SELECT id, content, category, key, tags, importance, created_at, updated_at FROM memories ORDER BY updated_at DESC LIMIT ?",
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
    limit: int = 5,
    category: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return search_memory(query=query, limit=limit, category=category, user_id=user_id)


def get_summary_html(user_id: Optional[str] = None) -> str:
    mems = list_memories(limit=25, user_id=user_id)
    if not mems:
        return (
            "🧠 <b>Deuxième Cerveau & Mémoire Long-Terme (Mem0)</b>\n\n"
            "<i>Aucun souvenir stocké pour le moment.</i>\n\n"
            "💡 Utilisez <code>/remember &lt;information&gt;</code> pour mémoriser un fait permanent."
        )

    categories: Dict[str, List[Dict[str, Any]]] = {}
    for m in mems:
        cat = m["category"]
        categories.setdefault(cat, []).append(m)

    lines = ["🧠 <b>Deuxième Cerveau & Souvenirs Actifs (Mem0)</b>\n"]
    cat_icons = {
        "profile": "👤",
        "system": "🤖",
        "infra": "🖥️",
        "vault": "📚",
        "rules": "📌",
        "tools": "🔧",
        "user_note": "📝",
        "projet": "🚀",
        "general": "💡",
    }

    for cat, items in categories.items():
        icon = cat_icons.get(cat, "🔹")
        lines.append(f"{icon} <b>{html.escape(cat.upper())} :</b>")
        for it in items:
            lines.append(f"  • <code>#{it['id']}</code> {html.escape(it['content'])}")
        lines.append("")

    lines.append(
        "<i>💡 Commandes : <code>/memory &lt;recherche&gt;</code>, "
        "<code>/remember &lt;texte&gt;</code>, <code>/forget &lt;id&gt;</code>, <code>/vault</code></i>"
    )
    return "\n".join(lines)


def get_relevant_context(query: str, user_id: Optional[str] = None) -> str:
    ctx_parts = []

    all_mems = list_memories(limit=15, user_id=user_id)
    profile_mems = [m for m in all_mems if m["category"] in ("profile", "rules", "infra", "system", "user_note")]

    semantic_mems = search_memory(query, limit=5, user_id=user_id)

    combined = []
    seen_contents = set()
    for m in profile_mems:
        if m["content"] not in seen_contents:
            combined.append(f"• [{m['category']}] {m['content']}")
            seen_contents.add(m["content"])

    for m in semantic_mems:
        if m["score"] > 0.2 and m["content"] not in seen_contents:
            combined.append(f"• [{m['category']}] {m['content']}")
            seen_contents.add(m["content"])

    if combined:
        ctx_parts.append("[🧠 DEUXIÈME CERVEAU & MÉMOIRE LONG-TERME (Mem0)]\n" + "\n".join(combined))

    try:
        from vault_manager import search_notes
        v_results = search_notes(query)
        if v_results:
            vault_snippets = []
            for item in v_results[:2]:
                snippet_str = " | ".join(item["snippets"][:2])
                vault_snippets.append(f"• Note `{item['path']}` : {snippet_str}")
            if vault_snippets:
                ctx_parts.append(f"[📚 COFFRE OBSIDIAN MARKDOWN ({VAULT_DIR})]\n" + "\n".join(vault_snippets))
    except Exception:
        pass

    return "\n\n".join(ctx_parts)


def seed_default_memories():
    existing = list_memories(limit=5)
    if existing:
        return
    defaults = [
        ("Agent autonome propulsé par Google Antigravity CLI et piloté via Telegram.", "system"),
        ("Règle d'affichage Telegram : Pendant l'exécution, le suivi s'affiche en direct. La réponse finale doit être propre, claire et bien structurée.", "rules"),
        ("Outils CLI intégrés : tg_send (envoi de fichiers/photos/vidéos/audios sur Telegram), mem (mémoire vectorielle long-terme), vault (coffre Markdown Obsidian), browser (recherche et navigation web).", "tools"),
    ]
    for text, cat in defaults:
        add_memory(text, category=cat)


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
                print(f"  [{r['score']}] (id={r['id']}) {r['content']}")
        elif cmd == "list":
            for m in list_memories():
                print(f"  #{m['id']} [{m['category']}] {m['content']}")
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