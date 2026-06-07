"""Knowledge graph — cross-session entity and relation extraction.

Builds a simple graph of entities and their relationships from conversations,
stored in SQLite for persistence. Used to augment memory recall with
structured knowledge about users, projects, and topics.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _db_execute(db_path: str, sql: str, params: tuple = ()) -> list:
    """Run a SQL statement synchronously (intended for asyncio.to_thread)."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.fetchall()


def _db_query(db_path: str, sql: str, params: tuple = ()) -> list:
    """Run a read-only SQL query synchronously (intended for asyncio.to_thread)."""
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, params).fetchall()


@dataclass
class Entity:
    name: str
    entity_type: str  # "person", "project", "topic", "document"
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relation:
    source: str
    target: str
    relation_type: str  # "works_on", "owns", "mentions", "depends_on"
    weight: float = 1.0


class KnowledgeGraph:
    """Simple knowledge graph backed by SQLite.

    Stores entities and their relationships extracted from conversations.
    Used to provide structured context for memory recall.
    All public methods are async using asyncio.to_thread().
    """

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = str(self._data_dir / "knowledge_graph.db")
        _db_execute(self._db_path, """
            CREATE TABLE IF NOT EXISTS entities (
                name TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                properties_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        _db_execute(self._db_path, """
            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                created_at REAL NOT NULL
            )
        """)
        _db_execute(self._db_path,
                    "CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source)")
        _db_execute(self._db_path,
                    "CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target)")

    async def add_entity(self, entity: Entity) -> None:
        now = time.time()
        await asyncio.to_thread(
            _db_execute, self._db_path,
            "INSERT INTO entities (name, entity_type, properties_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "entity_type=excluded.entity_type, "
            "properties_json=excluded.properties_json, "
            "updated_at=excluded.updated_at",
            (entity.name, entity.entity_type,
             json.dumps(entity.properties), now, now),
        )

    async def get_entity(self, name: str) -> Entity | None:
        rows = await asyncio.to_thread(
            _db_query, self._db_path,
            "SELECT name, entity_type, properties_json FROM entities WHERE name=?",
            (name,),
        )
        if not rows:
            return None
        return Entity(name=rows[0][0], entity_type=rows[0][1],
                     properties=json.loads(rows[0][2]))

    async def add_relation(self, relation: Relation) -> None:
        await asyncio.to_thread(
            _db_execute, self._db_path,
            "INSERT INTO relations (source, target, relation_type, weight, created_at) VALUES (?,?,?,?,?)",
            (relation.source, relation.target, relation.relation_type,
             relation.weight, time.time()),
        )

    async def get_neighbors(self, entity_name: str, max_depth: int = 1) -> list[dict[str, Any]]:
        """Get all entities directly connected to the given entity."""
        rows = await asyncio.to_thread(
            _db_query, self._db_path,
            "SELECT source, target, relation_type, weight FROM relations WHERE source=? OR target=?",
            (entity_name, entity_name),
        )
        results = []
        for row in rows:
            neighbor = row[1] if row[0] == entity_name else row[0]
            results.append({
                "entity": entity_name,
                "neighbor": neighbor,
                "relation": row[2],
                "weight": row[3],
            })
        return results

    async def search_entities(self, query: str, limit: int = 10) -> list[Entity]:
        """Simple keyword search for entities.

        Escapes SQL LIKE wildcards in the query for literal matching.
        """
        # Escape LIKE wildcards so user input isn't interpreted as patterns
        safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = await asyncio.to_thread(
            _db_query, self._db_path,
            f"SELECT name, entity_type, properties_json FROM entities "
            f"WHERE name LIKE ? ESCAPE '\\' LIMIT ?",
            (f"%{safe_query}%", limit),
        )
        return [Entity(name=r[0], entity_type=r[1],
                      properties=json.loads(r[2])) for r in rows]

    async def get_all_entities(self, entity_type: str | None = None) -> list[Entity]:
        if entity_type:
            rows = await asyncio.to_thread(
                _db_query, self._db_path,
                "SELECT name, entity_type, properties_json FROM entities WHERE entity_type=?",
                (entity_type,),
            )
        else:
            rows = await asyncio.to_thread(
                _db_query, self._db_path,
                "SELECT name, entity_type, properties_json FROM entities"
            )
        return [Entity(name=r[0], entity_type=r[1],
                      properties=json.loads(r[2])) for r in rows]
