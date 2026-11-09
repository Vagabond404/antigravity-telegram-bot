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
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='persons';")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(persons);")
        p_cols = [r[1] for r in cur.fetchall()]
        if "user_id" not in p_cols:
            try:
                conn.execute("ALTER TABLE persons ADD COLUMN user_id TEXT DEFAULT 'default';")
            except Exception:
                pass
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS persons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
                name TEXT NOT NULL,
                aliases TEXT DEFAULT '',
                role TEXT DEFAULT '',
                relationship_to_user TEXT DEFAULT '',
                tone_preference TEXT DEFAULT '',
                facts TEXT DEFAULT '[]',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
            );
        """)

    # Interpersonal Relationships Table (Social graph)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='relationships';")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(relationships);")
        r_cols = [r[1] for r in cur.fetchall()]
        if "user_id" not in r_cols:
            try:
                conn.execute("ALTER TABLE relationships ADD COLUMN user_id TEXT DEFAULT 'default';")
            except Exception:
                pass
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_persons_user ON persons(user_id, name);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_user ON relationships(user_id);")
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
    uid_str = str(user_id or "default")

    # 1. If a non-empty key is provided, upsert by key within this user partition
    if clean_key:
        cur.execute("SELECT id FROM memories WHERE key = ? AND key != '' AND user_id = ?", (clean_key, uid_str))
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

    # 2. Otherwise check exact content match within this user partition
    cur.execute("SELECT id FROM memories WHERE content = ? AND user_id = ?", (content, uid_str))
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
    include_shared: bool = True,
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
        if include_shared:
            conditions.append("(user_id = ? OR user_id IN ('global', 'shared', 'default'))")
            params.append(str(user_id))
        else:
            conditions.append("user_id = ?")
            params.append(str(user_id))

    sql = "SELECT id, content, category, key, tags, importance, embedding, created_at, user_id FROM memories"
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
        mem_id, content, cat, key, tags, importance, emb_str, created_at = row[:8]
        row_uid = row[8] if len(row) > 8 else "default"

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

        # Boost personal memories slightly over global ones
        if user_id and str(row_uid) == str(user_id):
            score += 0.05

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
            "user_id": row_uid,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def list_memories(
    limit: int = 50,
    category: Optional[str] = None,
    user_id: Optional[str] = None,
    include_shared: bool = False,
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
        if include_shared:
            conditions.append("(user_id = ? OR user_id IN ('global', 'shared', 'default'))")
            params.append(str(user_id))
        else:
            conditions.append("user_id = ?")
            params.append(str(user_id))

    sql = "SELECT id, content, category, key, tags, importance, created_at, updated_at, user_id FROM memories"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    if user_id and include_shared:
        sql += " ORDER BY CASE WHEN user_id = ? THEN 1 ELSE 0 END DESC, importance DESC, updated_at DESC LIMIT ?"
        params.extend([str(user_id), limit])
    else:
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
            "user_id": r[8] if len(r) > 8 else "default",
        }
        for r in rows
    ]


def list_memories_by_categories(
    categories: List[str],
    limit: int = 25,
    user_id: Optional[str] = None,
    include_shared: bool = False,
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    if not categories:
        return []
    conn = get_db(db_path)
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in categories)
    if user_id:
        if include_shared:
            cur.execute(
                f"""SELECT id, content, category, key, tags, importance, created_at, updated_at, user_id 
                    FROM memories 
                    WHERE category IN ({placeholders}) AND (user_id = ? OR user_id IN ('global', 'shared', 'default')) 
                    ORDER BY CASE WHEN user_id = ? THEN 1 ELSE 0 END DESC, importance DESC, updated_at DESC LIMIT ?""",
                (*categories, str(user_id), str(user_id), limit),
            )
        else:
            cur.execute(
                f"""SELECT id, content, category, key, tags, importance, created_at, updated_at, user_id 
                    FROM memories 
                    WHERE category IN ({placeholders}) AND user_id = ? 
                    ORDER BY importance DESC, updated_at DESC LIMIT ?""",
                (*categories, str(user_id), limit),
            )
    else:
        cur.execute(
            f"""SELECT id, content, category, key, tags, importance, created_at, updated_at, user_id 
                FROM memories 
                WHERE category IN ({placeholders}) 
                ORDER BY importance DESC, updated_at DESC LIMIT ?""",
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
            "user_id": r[8] if len(r) > 8 else "default",
        }
        for r in rows
    ]


def delete_memory(memory_id: int, user_id: Optional[str] = None, db_path: str = DB_PATH) -> bool:
    conn = get_db(db_path)
    cur = conn.cursor()
    if user_id:
        cur.execute("DELETE FROM memories WHERE id = ? AND (user_id = ? OR user_id IN ('global', 'shared', 'default'))", (memory_id, str(user_id)))
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
    user_id: str = "default",
    db_path: str = DB_PATH,
) -> int:
    """Create or update a person profile strictly isolated per user."""
    clean_name = (name or "").strip()
    if not clean_name:
        return 0

    uid_str = str(user_id or "default")
    conn = get_db(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, role, relationship_to_user, tone_preference, notes, aliases, facts FROM persons WHERE LOWER(name) = LOWER(?) AND user_id = ?",
        (clean_name, uid_str),
    )
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
            INSERT INTO persons (user_id, name, role, relationship_to_user, tone_preference, notes, aliases, facts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (uid_str, clean_name, role.strip(), relationship_to_user.strip(), tone_preference.strip(), notes.strip(), aliases.strip(), json.dumps(facts_list, ensure_ascii=False))
        )
        pid = cur.lastrowid
        conn.commit()
        conn.close()
        return pid or 0


def add_person_fact(name: str, fact: str, user_id: str = "default", db_path: str = DB_PATH) -> bool:
    """Add a permanent fact to a person's profile for a specific user."""
    clean_name = (name or "").strip()
    clean_fact = (fact or "").strip()
    if not clean_name or not clean_fact:
        return False

    uid_str = str(user_id or "default")
    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, facts FROM persons WHERE LOWER(name) = LOWER(?) AND user_id = ?",
        (clean_name, uid_str),
    )
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
        save_person(name=clean_name, facts=[clean_fact], user_id=uid_str, db_path=db_path)
        return True


def get_person(name: str, user_id: Optional[str] = None, include_shared: bool = True, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieve full profile of a person by name or alias for a specific user, with shared fallback."""
    clean_name = (name or "").strip().lower()
    if not clean_name:
        return None

    conn = get_db(db_path)
    cur = conn.cursor()
    if user_id:
        if include_shared:
            cur.execute(
                """SELECT id, name, aliases, role, relationship_to_user, tone_preference, facts, notes, created_at, updated_at, user_id 
                   FROM persons 
                   WHERE user_id = ? OR user_id IN ('global', 'shared', 'default') 
                   ORDER BY CASE WHEN user_id = ? THEN 1 ELSE 0 END DESC, updated_at DESC""",
                (str(user_id), str(user_id)),
            )
        else:
            cur.execute(
                "SELECT id, name, aliases, role, relationship_to_user, tone_preference, facts, notes, created_at, updated_at, user_id FROM persons WHERE user_id = ? ORDER BY updated_at DESC",
                (str(user_id),),
            )
    else:
        cur.execute("SELECT id, name, aliases, role, relationship_to_user, tone_preference, facts, notes, created_at, updated_at, user_id FROM persons ORDER BY updated_at DESC")
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
                "user_id": r[10] if len(r) > 10 else "default",
            }
    return None


def list_persons(user_id: Optional[str] = None, include_shared: bool = True, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """List registered person profiles, isolated per user with optional shared entities."""
    conn = get_db(db_path)
    cur = conn.cursor()
    if user_id:
        if include_shared:
            cur.execute(
                """SELECT id, name, aliases, role, relationship_to_user, tone_preference, facts, notes, created_at, updated_at, user_id 
                   FROM persons 
                   WHERE user_id = ? OR user_id IN ('global', 'shared', 'default') 
                   ORDER BY CASE WHEN user_id = ? THEN 1 ELSE 0 END DESC, updated_at DESC""",
                (str(user_id), str(user_id)),
            )
        else:
            cur.execute(
                "SELECT id, name, aliases, role, relationship_to_user, tone_preference, facts, notes, created_at, updated_at, user_id FROM persons WHERE user_id = ? ORDER BY updated_at DESC",
                (str(user_id),),
            )
    else:
        cur.execute("SELECT id, name, aliases, role, relationship_to_user, tone_preference, facts, notes, created_at, updated_at, user_id FROM persons ORDER BY updated_at DESC")
    rows = cur.fetchall()
    conn.close()

    res = []
    seen_names = set()
    for r in rows:
        p_name = r[1]
        if p_name.lower() in seen_names:
            continue
        seen_names.add(p_name.lower())
        try:
            facts = json.loads(r[6] or "[]")
        except Exception:
            facts = []
        res.append({
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
            "user_id": r[10] if len(r) > 10 else "default",
        })
    return res


def delete_person(name: str, user_id: Optional[str] = None, db_path: str = DB_PATH) -> bool:
    """Delete a person profile and any relationships they are involved in."""
    clean_name = (name or "").strip()
    if not clean_name:
        return False
    conn = get_db(db_path)
    cur = conn.cursor()
    if user_id:
        uid_str = str(user_id)
        cur.execute("DELETE FROM persons WHERE LOWER(name) = LOWER(?) AND user_id = ?", (clean_name, uid_str))
        affected = cur.rowcount > 0
        cur.execute("DELETE FROM relationships WHERE (LOWER(person_a) = LOWER(?) OR LOWER(person_b) = LOWER(?)) AND user_id = ?", (clean_name, clean_name, uid_str))
    else:
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
    user_id: str = "default",
    db_path: str = DB_PATH,
) -> int:
    """Add or update an interpersonal connection between two people for a specific user."""
    pa = (person_a or "").strip()
    rel = (relation_type or "").strip().lower()
    pb = (person_b or "").strip()
    if not pa or not rel or not pb:
        return 0

    uid_str = str(user_id or "default")
    # Ensure both persons exist in database for this user
    if not get_person(pa, user_id=uid_str, db_path=db_path):
        save_person(name=pa, user_id=uid_str, db_path=db_path)
    if not get_person(pb, user_id=uid_str, db_path=db_path):
        save_person(name=pb, user_id=uid_str, db_path=db_path)

    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id FROM relationships
        WHERE LOWER(person_a) = LOWER(?) AND LOWER(person_b) = LOWER(?) AND user_id = ?
        """,
        (pa, pb, uid_str),
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
            INSERT INTO relationships (user_id, person_a, relation_type, person_b, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (uid_str, pa, rel, pb, details.strip()),
        )
        rid = cur.lastrowid
        conn.commit()
        conn.close()
        return rid or 0


def list_relationships(person: Optional[str] = None, user_id: Optional[str] = None, include_shared: bool = True, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """List social connections between people, optionally filtering for one person and user partition."""
    conn = get_db(db_path)
    cur = conn.cursor()
    clauses = []
    params = []
    if user_id:
        if include_shared:
            clauses.append("(user_id = ? OR user_id IN ('global', 'shared', 'default'))")
            params.append(str(user_id))
        else:
            clauses.append("user_id = ?")
            params.append(str(user_id))
    if person:
        p_clean = person.strip().lower()
        clauses.append("(LOWER(person_a) = ? OR LOWER(person_b) = ?)")
        params.extend([p_clean, p_clean])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order_sql = "ORDER BY CASE WHEN user_id = ? THEN 1 ELSE 0 END DESC, updated_at DESC" if (user_id and include_shared) else "ORDER BY updated_at DESC"
    if user_id and include_shared:
        params.append(str(user_id))

    cur.execute(
        f"""
        SELECT id, person_a, relation_type, person_b, details, created_at, updated_at, user_id
        FROM relationships
        {where_sql}
        {order_sql}
        """,
        tuple(params),
    )
    rows = cur.fetchall()
    conn.close()

    res = []
    seen_rel = set()
    for r in rows:
        key = (r[1].lower(), r[2].lower(), r[3].lower())
        if key in seen_rel:
            continue
        seen_rel.add(key)
        res.append({
            "id": r[0],
            "person_a": r[1],
            "relation_type": r[2],
            "person_b": r[3],
            "details": r[4] or "",
            "created_at": r[5],
            "updated_at": r[6],
            "user_id": r[7] if len(r) > 7 else "default",
        })
    return res


def delete_relationship(rel_id: int, user_id: Optional[str] = None, db_path: str = DB_PATH) -> bool:
    """Delete a social connection by ID."""
    conn = get_db(db_path)
    cur = conn.cursor()
    if user_id:
        cur.execute("DELETE FROM relationships WHERE id = ? AND (user_id = ? OR user_id IN ('global', 'shared', 'default'))", (rel_id, str(user_id)))
    else:
        cur.execute("DELETE FROM relationships WHERE id = ?", (rel_id,))
    affected = cur.rowcount > 0
    conn.commit()
    conn.close()
    return affected


def get_memory_graph(user_id: Optional[str] = None, include_shared: bool = True, db_path: str = DB_PATH) -> Dict[str, Any]:
    mems = list_memories(limit=200, user_id=user_id, include_shared=include_shared, db_path=db_path)
    persons = list_persons(user_id=user_id, include_shared=include_shared, db_path=db_path)
    rels = list_relationships(user_id=user_id, include_shared=include_shared, db_path=db_path)
    nodes = [{"id": f"mem_{m['id']}", "type": "memory", "category": m["category"], "key": m["key"], "content": m["content"], "user_id": m.get("user_id", "")} for m in mems]
    for p in persons:
        nodes.append({"id": f"person_{p['id']}", "type": "person", "name": p["name"], "role": p["role"], "tone": p["tone_preference"], "user_id": p.get("user_id", "")})
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
    db_path: str = DB_PATH,
) -> int:
    return add_memory(
        content=content,
        category=category,
        user_id=user_id,
        key=key,
        tags=tags,
        related_to=related_to,
        importance=importance,
        db_path=db_path,
    )


def search_memories(
    query: str,
    limit: int = 6,
    category: Optional[str] = None,
    user_id: Optional[str] = None,
    include_shared: bool = True,
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    return search_memory(query=query, limit=limit, category=category, user_id=user_id, include_shared=include_shared, db_path=db_path)


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

    uid_str = str(user_id or "default")
    captured: List[str] = []

    # 1. Social Relations & Interpersonal Connections (French & English)
    # French: "Marc est mon collègue" / "Sophie est mon amie"
    m_rel_user_fr = re.search(r"([A-Za-zÀ-ÿ0-9_-]+)\s+est\s+(?:mon|ma)\s+([A-Za-zÀ-ÿ0-9_-]+)", text, flags=re.IGNORECASE)
    if m_rel_user_fr:
        p_name = m_rel_user_fr.group(1).capitalize()
        rel_type = m_rel_user_fr.group(2).lower()
        if p_name.lower() not in ("ceci", "cela", "c'", "il", "elle", "le", "la"):
            save_person(name=p_name, relationship_to_user=rel_type, user_id=uid_str)
            add_relationship("Utilisateur", f"proche ({rel_type})", p_name, details=f"{p_name} est {rel_type} de l'utilisateur", user_id=uid_str)
            captured.append(f"Relation: {p_name} est {rel_type} de l'utilisateur")

    # English: "Marc is my colleague" / "Alice is my friend"
    m_rel_user_en = re.search(r"([A-Za-z0-9_-]+)\s+is\s+my\s+([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    if m_rel_user_en:
        p_name = m_rel_user_en.group(1).capitalize()
        rel_type = m_rel_user_en.group(2).lower()
        if p_name.lower() not in ("this", "that", "it", "he", "she"):
            save_person(name=p_name, relationship_to_user=rel_type, user_id=uid_str)
            add_relationship("User", f"close ({rel_type})", p_name, details=f"{p_name} is user's {rel_type}", user_id=uid_str)
            captured.append(f"Relation: {p_name} is {rel_type} of user")

    # French: "Marc est le frère de Sophie"
    m_inter_rel_fr = re.search(r"([A-Za-zÀ-ÿ0-9_-]+)\s+est\s+(?:le|la|l')?\s*([A-Za-zÀ-ÿ0-9_-]+)\s+de\s+([A-Za-zÀ-ÿ0-9_-]+)", text, flags=re.IGNORECASE)
    if m_inter_rel_fr:
        p_a = m_inter_rel_fr.group(1).capitalize()
        rel_t = m_inter_rel_fr.group(2).lower()
        p_b = m_inter_rel_fr.group(3).capitalize()
        if p_a.lower() not in ("ceci", "cela", "c'", "il", "elle") and p_b.lower() not in ("ceci", "cela"):
            add_relationship(p_a, rel_t, p_b, user_id=uid_str)
            captured.append(f"Lien social: {p_a} est {rel_t} de {p_b}")

    # English: "Marc is Sophie's brother"
    m_inter_rel_en = re.search(r"([A-Za-z0-9_-]+)\s+is\s+([A-Za-z0-9_-]+)'s\s+([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    if m_inter_rel_en:
        p_a = m_inter_rel_en.group(1).capitalize()
        p_b = m_inter_rel_en.group(2).capitalize()
        rel_t = m_inter_rel_en.group(3).lower()
        if p_a.lower() not in ("this", "that", "it", "he", "she"):
            add_relationship(p_a, rel_t, p_b, user_id=uid_str)
            captured.append(f"Social connection: {p_a} is {rel_t} of {p_b}")

    # 2. Tone & Speech rules for a person (French & English)
    m_tone_fr = re.search(r"(?:quand tu parles à|adresse-toi à|parle à)\s+([A-Za-zÀ-ÿ0-9_-]+)\s+(?:en\s+|sur un ton\s+|avec\s+)?(.+)", text, flags=re.IGNORECASE)
    if m_tone_fr:
        p_name = m_tone_fr.group(1).capitalize()
        tone_instr = m_tone_fr.group(2).strip().rstrip(".,;!")
        save_person(name=p_name, tone_preference=tone_instr, user_id=uid_str)
        captured.append(f"Consigne de ton pour {p_name}: {tone_instr}")

    m_tone_en = re.search(r"(?:when talking to|when speaking to|speak to|talk to)\s+([A-Za-z0-9_-]+)(?:,|:)?\s+(?:use\s+|with\s+|in\s+)?(.+)", text, flags=re.IGNORECASE)
    if m_tone_en:
        p_name = m_tone_en.group(1).capitalize()
        tone_instr = m_tone_en.group(2).strip().rstrip(".,;!")
        save_person(name=p_name, tone_preference=tone_instr, user_id=uid_str)
        captured.append(f"Tone directive for {p_name}: {tone_instr}")

    # 3. Explicit memory commands in natural language
    explicit_patterns = [
        # English
        (r"(?:remember|don't forget|keep in mind)\s+(?:that\s+)?(.+)", "user_note", 5),
        (r"(?:i prefer|my preference is|i like when you)\s+(.+)", "preferences", 4),
        (r"(?:my name is|i am called)\s+([^\n.,!?;]{2,40})", "profile", 5),
        (r"(?:always answer in|always reply in|never)\s+(.+)", "rules", 5),
        # French
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
                add_memory(content=fact, category=cat, importance=imp, user_id=uid_str)
                captured.append(fact)
                break

    return captured


def get_summary_html(user_id: Optional[str] = None, lang: str = "en", db_path: str = DB_PATH) -> str:
    is_fr = (lang == "fr")
    mems = list_memories(limit=40, user_id=user_id, include_shared=True, db_path=db_path)
    persons = list_persons(user_id=user_id, include_shared=True, db_path=db_path)
    rels = list_relationships(user_id=user_id, include_shared=True, db_path=db_path)

    if not mems and not persons:
        if is_fr:
            return (
                "🧠 <b>Deuxième Cerveau & Mémoire Long-Terme (Mem0)</b>\n\n"
                "<i>Aucun souvenir ni profil stocké pour le moment.</i>\n\n"
                "💡 Utilisez <code>/remember &lt;information&gt;</code> ou dites simplement à l'agent "
                "<i>« Retiens que... »</i> pour mémoriser un fait permanent."
            )
        else:
            return (
                "🧠 <b>Second Brain & Long-Term Memory (Mem0)</b>\n\n"
                "<i>No memory or profile stored yet.</i>\n\n"
                "💡 Use <code>/remember &lt;information&gt;</code> or tell the agent "
                "<i>\"Remember that...\"</i> to store a permanent fact."
            )

    categories: Dict[str, List[Dict[str, Any]]] = {}
    for m in mems:
        cat = m["category"]
        categories.setdefault(cat, []).append(m)

    header = "🧠 <b>Mémoire Long-Terme, Profils & Souvenirs Actifs</b>\n" if is_fr else "🧠 <b>Long-Term Memory, Profiles & Active Knowledge</b>\n"
    lines = [header]

    if persons:
        lines.append("👥 <b>PROFILS DES PERSONNES & TONS :</b>" if is_fr else "👥 <b>PEOPLE PROFILES & SPEECH TONES:</b>")
        for p in persons:
            p_desc = f"• 👤 <b>{html.escape(p['name'])}</b>"
            details = []
            if p.get("role"):
                details.append(f"Rôle: {html.escape(p['role'])}" if is_fr else f"Role: {html.escape(p['role'])}")
            if p.get("relationship_to_user"):
                details.append(f"Lien: {html.escape(p['relationship_to_user'])}" if is_fr else f"Relation: {html.escape(p['relationship_to_user'])}")
            if p.get("tone_preference"):
                details.append(f"🗣️ Ton: <i>{html.escape(p['tone_preference'])}</i>" if is_fr else f"🗣️ Tone: <i>{html.escape(p['tone_preference'])}</i>")
            p_uid = p.get("user_id", "")
            is_shared = p_uid in ("global", "shared", "default")
            badge = " 🌐 <i>[Shared]</i>" if is_shared else ""
            if details:
                p_desc += f" ({', '.join(details)}){badge}"
            elif badge:
                p_desc += badge
            lines.append(p_desc)
            if p.get("facts"):
                for pf in p["facts"][:3]:
                    lines.append(f"    └ <i>{html.escape(pf)}</i>")
        lines.append("")

    if rels:
        lines.append("🤝 <b>GRAPH RELATIONNEL & LIENS :</b>" if is_fr else "🤝 <b>SOCIAL GRAPH & CONNECTIONS:</b>")
        for r in rels[:8]:
            det = f" [<i>{html.escape(r['details'])}</i>]" if r.get("details") else ""
            lines.append(f"  • 🔗 <b>{html.escape(r['person_a'])}</b> ➔ {html.escape(r['relation_type'])} ➔ <b>{html.escape(r['person_b'])}</b>{det}")
        lines.append("")

    cat_icons = {
        "profile": "👤",
        "preferences": "⭐",
        "projet": "🚀",
        "projects": "🚀",
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
            it_uid = it.get("user_id", "")
            is_shared = it_uid in ("global", "shared", "default")
            scope_badge = " 🌐 [Shared]" if is_shared else ""
            lines.append(f"  • <code>#{it['id']}</code>{key_badge}{scope_badge} {html.escape(it['content'])}")
        lines.append("")

    footer = (
        "<i>💡 Commandes : <code>/memory &lt;recherche&gt;</code>, "
        "<code>/remember &lt;texte&gt;</code>, <code>/forget &lt;id&gt;</code></i>"
        if is_fr else
        "<i>💡 Commands: <code>/memory &lt;search&gt;</code>, "
        "<code>/remember &lt;text&gt;</code>, <code>/forget &lt;id&gt;</code></i>"
    )
    lines.append(footer)
    return "\n".join(lines)


def get_relevant_context(query: str, user_id: Optional[str] = None, db_path: str = DB_PATH) -> str:
    """
    Build the complete Long-Term Memory context block injected into the Agent:
      0. Person Profiles, Interpersonal Relationships & Speech Tone Instructions (Personal + Shared)
      1. Core User Profile, Preferences & Personal Notes (Strictly Personal to user_id)
      2. Active Projects, Infrastructure & Global Rules (Personal + Shared/Global)
      3. Semantic & Keyword matches for current user prompt (Personal + Shared/Global)
    """
    ctx_parts = []
    seen_contents = set()

    # 0. People Profiles, Tone Rules & Social Graph (Personal + Shared)
    persons = list_persons(user_id=user_id, include_shared=True, db_path=db_path)
    rels = list_relationships(user_id=user_id, include_shared=True, db_path=db_path)
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
            desc_parts = [f"• 👤 Name: {p['name']}"]
            if p.get("role"):
                desc_parts.append(f"Role: {p['role']}")
            if p.get("relationship_to_user"):
                desc_parts.append(f"Relation to user: {p['relationship_to_user']}")
            if p.get("tone_preference"):
                desc_parts.append(f"🗣️ SPEECH TONE / HOW TO SPEAK TO THEM: {p['tone_preference']}")
            if p.get("notes"):
                desc_parts.append(f"Notes: {p['notes']}")
            facts = p.get("facts", [])
            if facts:
                desc_parts.append(f"Known facts: {'; '.join(facts[:4])}")
            p_uid = p.get("user_id", "")
            if p_uid in ("global", "shared", "default"):
                desc_parts.append("(Scope: Shared 🌐)")
            person_lines.append(" | ".join(desc_parts))

    rel_lines = []
    if rels:
        for r in rels[:10]:
            det = f" ({r['details']})" if r.get("details") else ""
            rel_lines.append(f"• 🔗 {r['person_a']} is {r['relation_type']} of {r['person_b']}{det}")

    # 1. Core Profile, Preferences & Personal Notes (Strictly Personal to this user)
    core_mems = list_memories_by_categories(
        ["profile", "user_profile", "preferences", "user_note"],
        limit=20,
        user_id=user_id,
        include_shared=False,
        db_path=db_path,
    )
    core_lines = []
    for m in core_mems:
        if m["content"] not in seen_contents:
            k_str = f" ({m['key']})" if m.get("key") else ""
            core_lines.append(f"• [Personal 👤: {m['category']}{k_str}] {m['content']}")
            seen_contents.add(m["content"])

    # 2. Projects & Infrastructure & Rules (Personal + Shared)
    proj_mems = list_memories_by_categories(
        ["projet", "projects", "project", "infra", "rules", "system"],
        limit=20,
        user_id=user_id,
        include_shared=True,
        db_path=db_path,
    )
    proj_lines = []
    for m in proj_mems:
        if m["content"] not in seen_contents:
            k_str = f" ({m['key']})" if m.get("key") else ""
            m_uid = m.get("user_id", "")
            scope_tag = "Shared 🌐" if m_uid in ("global", "shared", "default") else "Personal 👤"
            proj_lines.append(f"• [{scope_tag}: {m['category']}{k_str}] {m['content']}")
            seen_contents.add(m["content"])

    # 3. Semantic / Keyword search across all other memories (Personal + Shared)
    semantic_mems = search_memory(query, limit=8, user_id=user_id, include_shared=True, db_path=db_path)
    sem_lines = []
    for m in semantic_mems:
        if m["score"] > 0.18 and m["content"] not in seen_contents:
            k_str = f" ({m['key']})" if m.get("key") else ""
            m_uid = m.get("user_id", "")
            scope_tag = "Shared 🌐" if m_uid in ("global", "shared", "default") else "Personal 👤"
            sem_lines.append(f"• [{scope_tag}: {m['category']}{k_str}] {m['content']}")
            seen_contents.add(m["content"])

    mem_sections = []
    if person_lines:
        mem_sections.append("👥 PERSON PROFILES & SPEECH TONE INSTRUCTIONS:\n" + "\n".join(person_lines))
    if rel_lines:
        mem_sections.append("🤝 SOCIAL GRAPH & INTERPERSONAL CONNECTIONS:\n" + "\n".join(rel_lines))
    if core_lines:
        mem_sections.append("👤 USER PERSONAL PROFILE & PREFERENCES (Private to current user):\n" + "\n".join(core_lines))
    if proj_lines:
        mem_sections.append("🚀 KNOWN PROJECTS, INFRASTRUCTURE & RULES (Personal + Shared):\n" + "\n".join(proj_lines))
    if sem_lines:
        mem_sections.append("🔍 RELEVANT MEMORIES FOR THIS REQUEST:\n" + "\n".join(sem_lines))

    if mem_sections:
        ctx_parts.append("[🧠 PROACTIVE LONG-TERM MEMORY (Mem0)]\n" + "\n\n".join(mem_sections))

    return "\n\n".join(ctx_parts)


def seed_default_memories():
    existing = list_memories(limit=5)
    if existing:
        return
    defaults = [
        ("Autonomous AI agent powered by Google Antigravity CLI and managed via Telegram.", "system", "agent_identity"),
        ("Telegram display rule: Real-time progress is streamed live during execution. Final response must be clean, clear and well-structured.", "rules", "display_rule"),
        ("Proactive memory: Always record personal information, preferences and project details with mem.py to remember across conversations.", "rules", "proactive_memory"),
    ]
    for text, cat, key in defaults:
        add_memory(text, category=cat, key=key, importance=4, user_id="default")


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