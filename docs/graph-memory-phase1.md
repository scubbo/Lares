# Graph Memory - Phase 1 Implementation

*Created: 2026-01-03*
*Status: Draft - ready for implementation*

## Overview

This document specifies Phase 1 of the graph memory architecture: schema definition and basic CRUD operations. The goal is to extend the existing SQLite provider to support memory nodes and edges without breaking current functionality.

## Schema Extension

Add to `SqliteMemoryProvider._create_tables()`:

```sql
-- Memory graph nodes
CREATE TABLE IF NOT EXISTS memory_nodes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    summary TEXT,                    -- Short summary for quick display
    source TEXT NOT NULL,            -- 'conversation', 'perch_tick', 'research', 'reflection'
    tags TEXT,                       -- JSON array of tags
    embedding BLOB,                  -- Vector embedding for semantic search (Phase 2)
    access_count INTEGER DEFAULT 0,  -- How many times retrieved
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP
);

-- Memory graph edges (associations)
CREATE TABLE IF NOT EXISTS memory_edges (
    id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    weight REAL DEFAULT 0.5,         -- 0.0 to 1.0
    edge_type TEXT DEFAULT 'related', -- 'related', 'causal', 'temporal', 'contradicts'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_strengthened TIMESTAMP,
    FOREIGN KEY (source_node_id) REFERENCES memory_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES memory_nodes(id) ON DELETE CASCADE,
    UNIQUE(source_node_id, target_node_id)  -- One edge per direction
);

-- Indexes for efficient traversal
CREATE INDEX IF NOT EXISTS idx_edges_source ON memory_edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON memory_edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_weight ON memory_edges(weight DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_source ON memory_nodes(source);
CREATE INDEX IF NOT EXISTS idx_nodes_accessed ON memory_nodes(last_accessed DESC);
```

## New Methods for SqliteMemoryProvider

### Node Operations

```python
async def create_memory_node(
    self,
    content: str,
    source: str = "conversation",
    summary: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Create a new memory node.
    
    Returns the node ID.
    """

async def get_memory_node(self, node_id: str) -> dict | None:
    """Get a single memory node by ID."""

async def search_memory_nodes(
    self,
    query: str,
    limit: int = 10,
    source_filter: str | None = None,
) -> list[dict]:
    """Search nodes by content (text search for Phase 1)."""

async def list_recent_nodes(
    self,
    limit: int = 20,
    source_filter: str | None = None,
) -> list[dict]:
    """List recently created/accessed nodes."""

async def update_node_access(self, node_id: str) -> None:
    """Update access count and last_accessed timestamp."""
```

### Edge Operations

```python
async def create_memory_edge(
    self,
    source_id: str,
    target_id: str,
    edge_type: str = "related",
    initial_weight: float = 0.5,
) -> str:
    """Create an edge between two nodes.
    
    Returns edge ID. Upserts if edge exists.
    """

async def strengthen_edge(
    self,
    source_id: str,
    target_id: str,
    amount: float = 0.1,
) -> float:
    """Strengthen an edge (Hebbian learning).
    
    Returns new weight (capped at 1.0).
    """

async def get_connected_nodes(
    self,
    node_id: str,
    direction: str = "both",  # "outgoing", "incoming", "both"
    min_weight: float = 0.1,
    limit: int = 10,
) -> list[dict]:
    """Get nodes connected to this one, sorted by edge weight."""

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
```

## MCP Tools (for me to use)

### memory_node_create
Create a new memory node with content and optional metadata.

### memory_node_link
Create or strengthen a link between two nodes.

### memory_node_search
Search for nodes matching a query.

### memory_graph_explore
Traverse the graph from a starting node.

### memory_graph_stats
Show statistics: node count, edge count, avg connections, etc.

## Usage Patterns

### Creating memories from conversations
When Daniele shares something important:
1. I call `memory_node_create` with the key information
2. I search for related existing nodes
3. I call `memory_node_link` to connect them

### Retrieving context (Phase 2+)
Before responding:
1. System embeds the incoming message
2. System finds top-K similar nodes
3. System traverses edges to find related context
4. Context is injected into my prompt

### Hebbian reinforcement (Phase 4+)
When multiple nodes are accessed together:
1. Track which nodes appear in same context
2. Strengthen edges between co-accessed nodes
3. Decay edges during perch ticks if not accessed

## Migration Path

1. Add new tables (non-breaking)
2. Add new methods to SqliteMemoryProvider
3. Create MCP tools that wrap the methods
4. Test manually via MCP
5. Later: automatic retrieval, decay, etc.

## Open Decisions

- [ ] **Summary generation**: Auto-generate from content or require manual?
- [ ] **Bidirectional edges**: Store one edge or two? (Currently: two, via UNIQUE constraint)
- [ ] **Decay rate**: What's the half-life? (Propose: 7 days, 0.1 floor)
- [ ] **Token budget**: How much graph context to inject? (Propose: 2000 tokens max)

## Next Steps

1. ✅ Write this spec
2. [ ] Implement schema extension
3. [ ] Implement node CRUD methods
4. [ ] Implement edge methods
5. [ ] Create MCP tools
6. [ ] Manual testing
7. [ ] Document usage patterns
