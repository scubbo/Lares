"""Graph memory extension for SQLite provider.

Adds memory nodes and edges for associative memory.
"""

import json
import uuid
from collections import deque
from datetime import UTC, datetime

import aiosqlite
import structlog

log = structlog.get_logger()


class GraphMemoryMixin:
    """Mixin that adds graph memory capabilities to SqliteMemoryProvider."""

    _db: aiosqlite.Connection | None

    async def _create_graph_tables(self) -> None:
        """Create graph memory tables if they don't exist."""
        if not self._db:
            raise RuntimeError("Provider not initialized")

        await self._db.executescript("""
            -- Memory graph nodes
            CREATE TABLE IF NOT EXISTS memory_nodes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                summary TEXT,
                source TEXT NOT NULL,
                tags TEXT,
                embedding BLOB,
                access_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP
            );

            -- Memory graph edges
            CREATE TABLE IF NOT EXISTS memory_edges (
                id TEXT PRIMARY KEY,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                weight REAL DEFAULT 0.5,
                edge_type TEXT DEFAULT 'related',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_strengthened TIMESTAMP,
                FOREIGN KEY (source_node_id) REFERENCES memory_nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (target_node_id) REFERENCES memory_nodes(id) ON DELETE CASCADE,
                UNIQUE(source_node_id, target_node_id)
            );

            -- Indexes for efficient traversal
            CREATE INDEX IF NOT EXISTS idx_edges_source ON memory_edges(source_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON memory_edges(target_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_weight ON memory_edges(weight DESC);
            CREATE INDEX IF NOT EXISTS idx_nodes_source ON memory_nodes(source);
            CREATE INDEX IF NOT EXISTS idx_nodes_accessed ON memory_nodes(last_accessed DESC);
        """)
        await self._db.commit()
        log.info("graph_memory_tables_created")

    # === Node Operations ===

    async def create_memory_node(
        self,
        content: str,
        source: str = "conversation",
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Create a new memory node.

        Args:
            content: The memory content
            source: Origin type (conversation, perch_tick, research, reflection)
            summary: Optional short summary
            tags: Optional list of tags

        Returns:
            The node ID
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        node_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC).isoformat()

        await self._db.execute(
            """
            INSERT INTO memory_nodes
            (id, content, summary, source, tags, access_count, created_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                node_id,
                content,
                summary,
                source,
                json.dumps(tags) if tags else None,
                now,
                now,
            ),
        )
        await self._db.commit()

        log.info("memory_node_created", node_id=node_id, source=source)
        return node_id

    async def get_memory_node(self, node_id: str) -> dict | None:
        """Get a single memory node by ID."""
        if not self._db:
            return None

        cursor = await self._db.execute(
            """
            SELECT id, content, summary, source, tags, access_count,
                   created_at, last_accessed
            FROM memory_nodes WHERE id = ?
            """,
            (node_id,),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        # Update access tracking
        await self.update_node_access(node_id)

        return {
            "id": row["id"],
            "content": row["content"],
            "summary": row["summary"],
            "source": row["source"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "access_count": row["access_count"],
            "created_at": row["created_at"],
            "last_accessed": row["last_accessed"],
        }

    async def search_memory_nodes(
        self,
        query: str,
        limit: int = 10,
        source_filter: str | None = None,
    ) -> list[dict]:
        """Search nodes by content (text search for Phase 1)."""
        if not self._db:
            return []

        pattern = f"%{query}%"

        if source_filter:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                WHERE (content LIKE ? OR summary LIKE ?) AND source = ?
                ORDER BY last_accessed DESC
                LIMIT ?
                """,
                (pattern, pattern, source_filter, limit),
            )
        else:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                WHERE content LIKE ? OR summary LIKE ?
                ORDER BY last_accessed DESC
                LIMIT ?
                """,
                (pattern, pattern, limit),
            )

        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "summary": row["summary"],
                "source": row["source"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "access_count": row["access_count"],
                "created_at": row["created_at"],
                "last_accessed": row["last_accessed"],
            }
            for row in rows
        ]

    async def list_recent_nodes(
        self,
        limit: int = 20,
        source_filter: str | None = None,
    ) -> list[dict]:
        """List recently created/accessed nodes."""
        if not self._db:
            return []

        if source_filter:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                WHERE source = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (source_filter, limit),
            )
        else:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "summary": row["summary"],
                "source": row["source"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "access_count": row["access_count"],
                "created_at": row["created_at"],
                "last_accessed": row["last_accessed"],
            }
            for row in rows
        ]

    async def update_node_access(self, node_id: str) -> None:
        """Update access count and last_accessed timestamp."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE memory_nodes
            SET access_count = access_count + 1,
                last_accessed = ?
            WHERE id = ?
            """,
            (datetime.now(tz=UTC).isoformat(), node_id),
        )
        await self._db.commit()

    # === Edge Operations ===

    async def create_memory_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str = "related",
        initial_weight: float = 0.5,
    ) -> str:
        """Create an edge between two nodes.

        Returns edge ID. Updates weight if edge exists (upsert).
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        edge_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC).isoformat()

        # Upsert - if edge exists, strengthen it instead
        await self._db.execute(
            """
            INSERT INTO memory_edges
            (id, source_node_id, target_node_id, edge_type, weight, created_at, last_strengthened)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_node_id, target_node_id) DO UPDATE SET
                weight = MIN(1.0, weight + 0.1),
                last_strengthened = excluded.last_strengthened
            """,
            (edge_id, source_id, target_id, edge_type, initial_weight, now, now),
        )
        await self._db.commit()

        log.info(
            "memory_edge_created",
            source=source_id,
            target=target_id,
            edge_type=edge_type,
        )
        return edge_id

    async def strengthen_edge(
        self,
        source_id: str,
        target_id: str,
        amount: float = 0.1,
    ) -> float:
        """Strengthen an edge (Hebbian learning).

        Returns new weight (capped at 1.0).
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        now = datetime.now(tz=UTC).isoformat()

        await self._db.execute(
            """
            UPDATE memory_edges
            SET weight = MIN(1.0, weight + ?),
                last_strengthened = ?
            WHERE source_node_id = ? AND target_node_id = ?
            """,
            (amount, now, source_id, target_id),
        )
        await self._db.commit()

        # Get the new weight
        cursor = await self._db.execute(
            "SELECT weight FROM memory_edges WHERE source_node_id = ? AND target_node_id = ?",
            (source_id, target_id),
        )
        row = await cursor.fetchone()
        return row["weight"] if row else 0.0

    async def get_connected_nodes(
        self,
        node_id: str,
        direction: str = "both",
        min_weight: float = 0.1,
        limit: int = 10,
    ) -> list[dict]:
        """Get nodes connected to this one, sorted by edge weight."""
        if not self._db:
            return []

        results = []

        if direction in ("outgoing", "both"):
            cursor = await self._db.execute(
                """
                SELECT n.id, n.content, n.summary, n.source, e.weight, e.edge_type
                FROM memory_nodes n
                JOIN memory_edges e ON n.id = e.target_node_id
                WHERE e.source_node_id = ? AND e.weight >= ?
                ORDER BY e.weight DESC
                LIMIT ?
                """,
                (node_id, min_weight, limit),
            )
            rows = await cursor.fetchall()
            for row in rows:
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "source": row["source"],
                    "weight": row["weight"],
                    "edge_type": row["edge_type"],
                    "direction": "outgoing",
                })

        if direction in ("incoming", "both"):
            cursor = await self._db.execute(
                """
                SELECT n.id, n.content, n.summary, n.source, e.weight, e.edge_type
                FROM memory_nodes n
                JOIN memory_edges e ON n.id = e.source_node_id
                WHERE e.target_node_id = ? AND e.weight >= ?
                ORDER BY e.weight DESC
                LIMIT ?
                """,
                (node_id, min_weight, limit),
            )
            rows = await cursor.fetchall()
            for row in rows:
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "source": row["source"],
                    "weight": row["weight"],
                    "edge_type": row["edge_type"],
                    "direction": "incoming",
                })

        # Sort by weight and limit
        results.sort(key=lambda x: x["weight"], reverse=True)
        return results[:limit]

    async def traverse_graph(
        self,
        start_node_id: str,
        max_depth: int = 2,
        max_nodes: int = 20,
        min_weight: float = 0.2,
    ) -> list[dict]:
        """BFS traversal from a starting node.

        Returns nodes with their distance from start.
        """
        if not self._db:
            return []

        visited = set()
        results = []
        queue = deque([(start_node_id, 0)])

        while queue and len(results) < max_nodes:
            current_id, depth = queue.popleft()

            if current_id in visited:
                continue
            visited.add(current_id)

            # Get node info
            node = await self.get_memory_node(current_id)
            if node:
                node["depth"] = depth
                results.append(node)

            # Don't explore beyond max depth
            if depth >= max_depth:
                continue

            # Get connected nodes
            connected = await self.get_connected_nodes(
                current_id,
                direction="outgoing",
                min_weight=min_weight,
                limit=10,
            )

            for conn in connected:
                if conn["id"] not in visited:
                    queue.append((conn["id"], depth + 1))

        return results

    async def get_graph_stats(self) -> dict:
        """Get statistics about the memory graph."""
        if not self._db:
            return {}

        # Node count
        cursor = await self._db.execute("SELECT COUNT(*) as count FROM memory_nodes")
        node_row = await cursor.fetchone()
        node_count = node_row["count"] if node_row else 0

        # Edge count
        cursor = await self._db.execute("SELECT COUNT(*) as count FROM memory_edges")
        edge_row = await cursor.fetchone()
        edge_count = edge_row["count"] if edge_row else 0

        # Average connections per node
        avg_connections = edge_count / node_count if node_count > 0 else 0

        # Nodes by source
        cursor = await self._db.execute(
            "SELECT source, COUNT(*) as count FROM memory_nodes GROUP BY source"
        )
        source_rows = await cursor.fetchall()
        by_source = {row["source"]: row["count"] for row in source_rows}

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "avg_connections": round(avg_connections, 2),
            "nodes_by_source": by_source,
        }
