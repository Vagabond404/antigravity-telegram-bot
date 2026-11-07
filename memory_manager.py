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
from config import BASE_DIR

try:
    from fastembed import TextEmbedding
    FASTEMBED_AVAILABLE = True
except ImportError:
    FASTEMBED_AVAILABLE = False

try:
    from resource_governor import governor
    IS_LOW_SPEC = bool(governor.low_resource_mode)
except Exception:
    IS_LOW_SPEC = False

DB_PATH = str(BASE_DIR / "memory.db")
MODEL_NAME = "BAAI/bge-small-en-v1.5"

_embedder_cache = None


def get_embedder():
    global _embedder_cache
    # On low-spec devices (TV box, ARM SBCs, <=2GB RAM), skip heavy ONNX neural networks
    # and use instant, lightweight SQLite keyword matching to keep response times under 1 second.
    if IS_LOW_SPEC or not FASTEMBED_AVAILABLE or os.getenv("DISABLE_EMBEDDINGS", "").strip().lower() in ("1", "true"):
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

    # People Profiles Table (Persons, Tone preference, Facts, Notes)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            aliases TEXT DEFAULT '',
            role TEXT DEFAULT '',
            relationship_to_user TEXT DEFAULT '',
            tone_preference TEXT DEFAULT '',
            facts TEXT DEFAULT '[]',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Interpersonal Relationships Table (Social graph)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_a TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            person_b TEXT NOT NULL,
            details TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_cat ON memories(category);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_a ON relationships(person_a);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_b ON relationships(person_b);")
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
    conditions = []
    params = []
    if category:
        conditions.append("category = ?")
        params.append(category)
    if user_id:
        conditions.append("user_id = ?")
        params.append(str(user_id))

    sql = "SELECT id, content, category, key, tags, importance, embedding, created_at FROM memories"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, tuple(params))
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
    conditions = []
    params = []
    if category:
        conditions.append("category = ?")
        params.append(category)
    if user_id:
        conditions.append("user_id = ?")
        params.append(str(user_id))

    sql = "SELECT id, content, category, key, tags, importance, created_at, updated_at FROM memories"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
    params.append(limit)

    cur.execute(sql, tuple(params))
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


def list_memories_by_categories(categories: List[str], limit: int = 25, user_id: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    if not categories:
        return []
    conn = get_db(db_path)
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in categories)
    if user_id:
        cur.execute(
            f"SELECT id, content, category, key, tags, importance, created_at, updated_at FROM memories WHERE category IN ({placeholders}) AND user_id = ? ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (*categories, str(user_id), limit),
        )
    else:
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
    if user_id:
        cur.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, str(user_id)))
    else:
        cur.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    affected = cur.rowcount > 0
    conn.commit()
    conn.close()
    return affected


# =============================================================================
# Advanced Person Profiles, Social Graph & Tone Engine
# =============================================================================

def save_person(
    name: str,
    role: str = "",
    relationship_to_user: str = "",
    tone_preference: str = "",
    notes: str = "",
    aliases: str = "",
    facts: Optional[List[str]] = None,
    db_path: str = DB_PATH,
) -> int:
    """Create or update a person profile (identity, social role, speech tone preference)."""
    clean_name = (name or "").strip()
    if not clean_name:
        return 0

    conn = get_db(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, role, relationship_to_user, tone_preference, notes, aliases, facts FROM persons WHERE LOWER(name) = LOWER(?)", (clean_name,))
    row = cur.fetchone()

    facts_list = list(facts or [])
    if row:
        pid, cur_role, cur_rel, cur_tone, cur_notes, cur_aliases, cur_facts_raw = row
        new_role = role.strip() or cur_role
        new_rel = relationship_to_user.strip() or cur_rel
        new_tone = tone_preference.strip() or cur_tone
        new_notes = notes.strip() or cur_notes
        new_aliases = aliases.strip() or cur_aliases

        try:
            merged_facts = json.loads(cur_facts_raw or "[]")
        except Exception:
            merged_facts = []
        for f in facts_list:
            if f and f not in merged_facts:
                merged_facts.append(f)

        cur.execute(
            """
            UPDATE persons
            SET role = ?, relationship_to_user = ?, tone_preference = ?, notes = ?, aliases = ?, facts = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_role, new_rel, new_tone, new_notes, new_aliases, json.dumps(merged_facts, ensure_ascii=False), pid)
        )
        conn.commit()
        conn.close()
        return pid
    else:
        cur.execute(
            """
            INSERT INTO persons (name, role, relationship_to_user, tone_preference, notes, aliases, facts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (clean_name, role.strip(), relationship_to_user.strip(), tone_preference.strip(), notes.strip(), aliases.strip(), json.dumps(facts_list, ensure_ascii=False))
        )
        pid = cur.lastrowid
        conn.commit()
        conn.close()
        return pid or 0


def add_person_fact(name: str, fact: str, db_path: str = DB_PATH) -> bool:
    """Add a permanent fact to a person's profile."""
    clean_name = (name or "").strip()
    clean_fact = (fact or "").strip()
    if not clean_name or not clean_fact:
        return False

    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, facts FROM persons WHERE LOWER(name) = LOWER(?)", (clean_name,))
    row = cur.fetchone()
    if row:
        pid, facts_raw = row
        try:
            facts = json.loads(facts_raw or "[]")
        except Exception:
            facts = []
        if clean_fact not in facts:
            facts.append(clean_fact)
            cur.execute("UPDATE persons SET facts = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (json.dumps(facts, ensure_ascii=False), pid))
            conn.commit()
        conn.close()
        return True
    else:
        conn.close()
        save_person(name=clean_name, facts=[clean_fact], db_path=db_path)
        return True


def get_person(name: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieve full profile of a person by name or alias."""
    clean_name = (name or "").strip().lower()
    if not clean_name:
        return None

    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, aliases, role, relationship_to_user, tone_preference, facts, notes, created_at, updated_at FROM persons")
    rows = cur.fetchall()
    conn.close()

    for r in rows:
        p_name = r[1]
        p_aliases = [a.strip().lower() for a in (r[2] or "").split(",") if a.strip()]
        if p_name.lower() == clean_name or clean_name in p_aliases:
            try:
                facts = json.loads(r[6] or "[]")
            except Exception:
                facts = []
            return {
                "id": r[0],
                "name": p_name,
                "aliases": r[2] or "",
                "role": r[3] or "",
                "relationship_to_user": r[4] or "",
                "tone_preference": r[5] or "",
                "facts": facts,
                "notes": r[7] or "",
                "created_at": r[8],
                "updated_at": r[9],
            }
    return None


def list_persons(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """List all registered person profiles."""
    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, aliases, role, relationship_to_user, tone_preference, facts, notes, created_at, updated_at FROM persons ORDER BY updated_at DESC")
    rows = cur.fetchall()
    conn.close()

    res = []
    for r in rows:
        try:
            facts = json.loads(r[6] or "[]")
        except Exception:
            facts = []
        res.append({
            "id": r[0],
            "name": r[1],
            "aliases": r[2] or "",
            "role": r[3] or "",
            "relationship_to_user": r[4] or "",
            "tone_preference": r[5] or "",
            "facts": facts,
            "notes": r[7] or "",
            "created_at": r[8],
            "updated_at": r[9],
        })
    return res


def delete_person(name: str, db_path: str = DB_PATH) -> bool:
    """Delete a person profile and any relationships they are involved in."""
    clean_name = (name or "").strip()
    if not clean_name:
        return False
    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM persons WHERE LOWER(name) = LOWER(?)", (clean_name,))
    affected = cur.rowcount > 0
    cur.execute("DELETE FROM relationships WHERE LOWER(person_a) = LOWER(?) OR LOWER(person_b) = LOWER(?)", (clean_name, clean_name))
    conn.commit()
    conn.close()
    return affected


def add_relationship(
    person_a: str,
    relation_type: str,
    person_b: str,
    details: str = "",
    db_path: str = DB_PATH,
) -> int:
    """Add or update an interpersonal connection between two people."""
    pa = (person_a or "").strip()
    rel = (relation_type or "").strip().lower()
    pb = (person_b or "").strip()
    if not pa or not rel or not pb:
        return 0

    # Ensure both persons exist in database
    if not get_person(pa, db_path=db_path):
        save_person(name=pa, db_path=db_path)
    if not get_person(pb, db_path=db_path):
        save_person(name=pb, db_path=db_path)

    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id FROM relationships
        WHERE LOWER(person_a) = LOWER(?) AND LOWER(person_b) = LOWER(?)
        """,
        (pa, pb),
    )
    row = cur.fetchone()
    if row:
        rid = row[0]
        cur.execute(
            """
            UPDATE relationships
            SET relation_type = ?, details = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (rel, details.strip(), rid),
        )
        conn.commit()
        conn.close()
        return rid
    else:
        cur.execute(
            """
            INSERT INTO relationships (person_a, relation_type, person_b, details)
            VALUES (?, ?, ?, ?)
            """,
            (pa, rel, pb, details.strip()),
        )
        rid = cur.lastrowid
        conn.commit()
        conn.close()
        return rid or 0


def list_relationships(person: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """List social connections between people, optionally filtering for one person."""
    conn = get_db(db_path)
    cur = conn.cursor()
    if person:
        p_clean = person.strip().lower()
        cur.execute(
            """
            SELECT id, person_a, relation_type, person_b, details, created_at, updated_at
            FROM relationships
            WHERE LOWER(person_a) = ? OR LOWER(person_b) = ?
            ORDER BY updated_at DESC
            """,
            (p_clean, p_clean),
        )
    else:
        cur.execute(
            """
            SELECT id, person_a, relation_type, person_b, details, created_at, updated_at
            FROM relationships
            ORDER BY updated_at DESC
            """
        )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "person_a": r[1],
            "relation_type": r[2],
            "person_b": r[3],
            "details": r[4] or "",
            "created_at": r[5],
            "updated_at": r[6],
        }
        for r in rows
    ]


def delete_relationship(rel_id: int, db_path: str = DB_PATH) -> bool:
    """Delete a social connection by ID."""
    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM relationships WHERE id = ?", (rel_id,))
    affected = cur.rowcount > 0
    conn.commit()
    conn.close()
    return affected


def get_memory_graph(db_path: str = DB_PATH) -> Dict[str, Any]:
    mems = list_memories(limit=200, db_path=db_path)
    persons = list_persons(db_path=db_path)
    rels = list_relationships(db_path=db_path)
    nodes = [{"id": f"mem_{m['id']}", "type": "memory", "category": m["category"], "key": m["key"], "content": m["content"]} for m in mems]
    for p in persons:
        nodes.append({"id": f"person_{p['id']}", "type": "person", "name": p["name"], "role": p["role"], "tone": p["tone_preference"]})
    links = []
    for r in rels:
        links.append({"source": r["person_a"], "target": r["person_b"], "type": r["relation_type"], "details": r["details"]})
    return {"total_nodes": len(nodes), "total_links": len(links), "nodes": nodes, "links": links}


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


def auto_extract_and_store_facts(user_text: str, user_id: str = "default") -> List[str]:
    """
    Automatically detect explicit user statements (personal info, preferences,
    explicit 'remember this' requests, social relations, speech tone instructions,
    or project notes) and persist them to SQLite immediately.
    """
    if not user_text or len(user_text.strip()) < 6:
        return []
    text = user_text.strip()
    if text.startswith("/"):
        return []

    captured: List[str] = []

    # 1. Social Relations & Interpersonal Connections
    # "Marc est mon collègue" / "Sophie est mon amie"
    m_rel_user = re.search(r"([A-Za-zÀ-ÿ0-9_-]+)\s+est\s+(?:mon|ma)\s+([A-Za-zÀ-ÿ0-9_-]+)", text, flags=re.IGNORECASE)
    if m_rel_user:
        p_name = m_rel_user.group(1).capitalize()
        rel_type = m_rel_user.group(2).lower()
        if p_name.lower() not in ("ceci", "cela", "c'", "il", "elle", "le", "la"):
            save_person(name=p_name, relationship_to_user=rel_type)
            add_relationship("Utilisateur", f"proche ({rel_type})", p_name, details=f"{p_name} est {rel_type} de l'utilisateur")
            captured.append(f"Relation: {p_name} est {rel_type} de l'utilisateur")

    # "Marc est le frère de Sophie"
    m_inter_rel = re.search(r"([A-Za-zÀ-ÿ0-9_-]+)\s+est\s+(?:le|la|l')?\s*([A-Za-zÀ-ÿ0-9_-]+)\s+de\s+([A-Za-zÀ-ÿ0-9_-]+)", text, flags=re.IGNORECASE)
    if m_inter_rel:
        p_a = m_inter_rel.group(1).capitalize()
        rel_t = m_inter_rel.group(2).lower()
        p_b = m_inter_rel.group(3).capitalize()
        if p_a.lower() not in ("ceci", "cela", "c'", "il", "elle") and p_b.lower() not in ("ceci", "cela"):
            add_relationship(p_a, rel_t, p_b)
            captured.append(f"Lien social: {p_a} est {rel_t} de {p_b}")

    # 2. Tone & Speech rules for a person ("Quand tu parles à Marc, vouvoie-le", "Parle à Sophie de manière formelle")
    m_tone = re.search(r"(?:quand tu parles à|adresse-toi à|parle à)\s+([A-Za-zÀ-ÿ0-9_-]+)\s+(?:en\s+|sur un ton\s+|avec\s+)?(.+)", text, flags=re.IGNORECASE)
    if m_tone:
        p_name = m_tone.group(1).capitalize()
        tone_instr = m_tone.group(2).strip().rstrip(".,;!")
        save_person(name=p_name, tone_preference=tone_instr)
        captured.append(f"Consigne de ton pour {p_name}: {tone_instr}")

    # 3. Explicit memory commands in natural language
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
                add_memory(content=fact, category=cat, importance=imp, user_id=user_id)
                captured.append(fact)
                break

    return captured


def get_summary_html(user_id: Optional[str] = None) -> str:
    mems = list_memories(limit=40, user_id=user_id)
    persons = list_persons()
    rels = list_relationships()

    if not mems and not persons:
        return (
            "🧠 <b>Deuxième Cerveau & Mémoire Long-Terme (Mem0)</b>\n\n"
            "<i>Aucun souvenir ni profil stocké pour le moment.</i>\n\n"
            "💡 Utilisez <code>/remember &lt;information&gt;</code> ou dites simplement à l'agent "
            "<i>« Retiens que... »</i> pour mémoriser un fait permanent."
        )

    categories: Dict[str, List[Dict[str, Any]]] = {}
    for m in mems:
        cat = m["category"]
        categories.setdefault(cat, []).append(m)

    lines = ["🧠 <b>Mémoire Long-Terme, Profils & Souvenirs Actifs</b>\n"]

    if persons:
        lines.append("👥 <b>PROFILS DES PERSONNES & TONS :</b>")
        for p in persons:
            p_desc = f"• 👤 <b>{html.escape(p['name'])}</b>"
            details = []
            if p.get("role"):
                details.append(f"Rôle: {html.escape(p['role'])}")
            if p.get("relationship_to_user"):
                details.append(f"Lien: {html.escape(p['relationship_to_user'])}")
            if p.get("tone_preference"):
                details.append(f"🗣️ Ton: <i>{html.escape(p['tone_preference'])}</i>")
            if details:
                p_desc += f" ({', '.join(details)})"
            lines.append(p_desc)
            if p.get("facts"):
                for pf in p["facts"][:3]:
                    lines.append(f"    └ <i>{html.escape(pf)}</i>")
        lines.append("")

    if rels:
        lines.append("🤝 <b>GRAPH RELATIONNEL & LIENS :</b>")
        for r in rels[:8]:
            det = f" [<i>{html.escape(r['details'])}</i>]" if r.get("details") else ""
            lines.append(f"  • 🔗 <b>{html.escape(r['person_a'])}</b> ➔ {html.escape(r['relation_type'])} ➔ <b>{html.escape(r['person_b'])}</b>{det}")
        lines.append("")

    cat_icons = {
        "profile": "👤",
        "preferences": "⭐",
        "projet": "🚀",
        "infra": "🖥️",
        "rules": "📌",
        "user_note": "📝",
        "system": "🤖",
        "tools": "🔧",
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
        "<code>/remember &lt;texte&gt;</code>, <code>/forget &lt;id&gt;</code></i>"
    )
    return "\n".join(lines)


def get_relevant_context(query: str, user_id: Optional[str] = None) -> str:
    """
    Build the complete Long-Term Memory context block injected into the Agent:
      0. Person Profiles, Interpersonal Relationships & Speech Tone Instructions
      1. Core User Profile, Preferences & Rules (always available across all chats)
      2. Active Projects & Infrastructure memories
      3. Semantic & Keyword matches for the current user prompt
    """
    ctx_parts = []
    seen_contents = set()

    # 0. People Profiles, Tone Rules & Social Graph
    persons = list_persons()
    rels = list_relationships()
    person_lines = []
    q_lower = query.lower()

    for p in persons:
        p_name_lower = p["name"].lower()
        aliases = [a.strip().lower() for a in (p.get("aliases") or "").split(",") if a.strip()]
        is_relevant = (
            p_name_lower in q_lower
            or any(a in q_lower for a in aliases)
            or "admin" in p.get("role", "").lower()
            or "principal" in p.get("relationship_to_user", "").lower()
            or len(persons) <= 6
        )
        if is_relevant:
            desc_parts = [f"• 👤 Nom: {p['name']}"]
            if p.get("role"):
                desc_parts.append(f"Rôle: {p['role']}")
            if p.get("relationship_to_user"):
                desc_parts.append(f"Lien avec l'utilisateur: {p['relationship_to_user']}")
            if p.get("tone_preference"):
                desc_parts.append(f"🗣️ DIRECTIVE DE TON / COMMENT LUI PARLER: {p['tone_preference']}")
            if p.get("notes"):
                desc_parts.append(f"Notes: {p['notes']}")
            facts = p.get("facts", [])
            if facts:
                desc_parts.append(f"Faits connus: {'; '.join(facts[:4])}")
            person_lines.append(" | ".join(desc_parts))

    rel_lines = []
    if rels:
        for r in rels[:10]:
            det = f" ({r['details']})" if r.get("details") else ""
            rel_lines.append(f"• 🔗 {r['person_a']} est {r['relation_type']} de {r['person_b']}{det}")

    # 1. Core Profile, Preferences & Rules (Filtered by user_id if provided)
    core_mems = list_memories_by_categories(
        ["profile", "user_profile", "preferences", "rules", "user_note"],
        limit=20,
        user_id=user_id,
    )
    core_lines = []
    for m in core_mems:
        if m["content"] not in seen_contents:
            k_str = f" ({m['key']})" if m.get("key") else ""
            core_lines.append(f"• [{m['category']}{k_str}] {m['content']}")
            seen_contents.add(m["content"])

    # 2. Projects & Infrastructure memories (Filtered by user_id if provided)
    proj_mems = list_memories_by_categories(
        ["projet", "projects", "project", "infra"],
        limit=15,
        user_id=user_id,
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
    if person_lines:
        mem_sections.append("👥 PROFILS DES PERSONNES & CONSIGNES D'ÉLOCUTION :\n" + "\n".join(person_lines))
    if rel_lines:
        mem_sections.append("🤝 GRAPH SOCIAL & LIENS ENTRE PERSONNES :\n" + "\n".join(rel_lines))
    if core_lines:
        mem_sections.append("👤 PROFIL, PRÉFÉRENCES & RÈGLES DE L'UTILISATEUR :\n" + "\n".join(core_lines))
    if proj_lines:
        mem_sections.append("🚀 PROJETS & INFRASTRUCTURE CONNUS :\n" + "\n".join(proj_lines))
    if sem_lines:
        mem_sections.append("🔍 SOUVENIRS PERTINENTS POUR CETTE DEMANDE :\n" + "\n".join(sem_lines))

    if mem_sections:
        ctx_parts.append("[🧠 MÉMOIRE LONG-TERME INTER-CONVERSATIONS (Mem0)]\n" + "\n\n".join(mem_sections))

    return "\n\n".join(ctx_parts)


def seed_default_memories():
    existing = list_memories(limit=5)
    if existing:
        return
    defaults = [
        ("Agent autonome propulsé par Google Antigravity CLI et piloté via Telegram.", "system", "agent_identity"),
        ("Règle d'affichage Telegram : Pendant l'exécution, le suivi s'affiche en direct. La réponse finale doit être propre, claire et bien structurée.", "rules", "display_rule"),
        ("Mémoire proactive : Toujours enregistrer les informations personnelles, préférences et détails des projets de l'utilisateur avec mem.py pour s'en souvenir entre toutes les conversations.", "rules", "proactive_memory"),
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