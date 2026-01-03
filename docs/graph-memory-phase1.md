# Graph Memory - Phase 1 Implementation

*Created: 2026-01-03*
*Status: ✅ COMPLETE - Ready for merge*

## Overview

This document specifies Phase 1 of the graph memory architecture: schema definition and basic CRUD operations. The goal is to extend the existing SQLite provider to support memory nodes and edges without breaking current functionality.

## Implementation Summary

**All Phase 1 features implemented and tested:**
- `src/lares/providers/sqlite_graph.py` - GraphMemoryMixin (479 lines)
- `src/lares/providers/sqlite_with_graph.py` - Combined provider
- `src/lares/mcp_graph_tools.py` - Tool implementation
- 6 MCP tools registered in `mcp_server.py`
- 19 tests in `tests/test_graph_memory.py`
- All 252 tests passing

## Schema

The following tables are created by `GraphMemoryMixin._create_graph_tables()`:

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

## MCP Tools Available

### graph_create_node
Create a new memory node with content and metadata.

**Parameters:**
- `content` (required): The memory content
- `source` (optional): 'conversation', 'perch_tick', 'research', 'reflection' (default: 'conversation')
- `summary` (optional): Short summary for quick reference
- `tags` (optional): Comma-separated tags

**Returns:** Node ID (UUID)

### graph_search_nodes
Search for nodes by text content.

**Parameters:**
- `query` (required): Search text
- `limit` (optional): Max results (default: 10)
- `source` (optional): Filter by source type

**Returns:** List of matching nodes

### graph_create_edge
Create or update an edge between two nodes.

**Parameters:**
- `source_id` (required): Source node ID
- `target_id` (required): Target node ID
- `edge_type` (optional): 'related', 'causal', 'temporal', 'contradicts' (default: 'related')
- `weight` (optional): Initial weight 0.0-1.0 (default: 0.5)

**Returns:** Edge ID (UUID)

### graph_get_connected
Get nodes connected to a given node.

**Parameters:**
- `node_id` (required): The node to find connections for
- `direction` (optional): 'outgoing', 'incoming', 'both' (default: 'both')
- `min_weight` (optional): Minimum edge weight (default: 0.1)
- `limit` (optional): Max results (default: 10)

**Returns:** List of connected nodes with edge info

### graph_traverse
BFS traversal from a starting node.

**Parameters:**
- `start_node_id` (required): Starting node
- `max_depth` (optional): How far to traverse (default: 2)
- `max_nodes` (optional): Max nodes to return (default: 20)
- `min_weight` (optional): Minimum edge weight to follow (default: 0.2)

**Returns:** List of nodes with distance from start

### graph_stats
Get statistics about the memory graph.

**Returns:** Node count, edge count, nodes by source, average connections

## Usage Examples

### Storing a memory from conversation
```
graph_create_node(
    content="Daniele is training for Aconcagua with coach Seth Keena using House/Johnston methodology",
    source="conversation",
    summary="Aconcagua training setup",
    tags="mountaineering,training,aconcagua"
)
```

### Finding related memories
```
graph_search_nodes(query="training", source="conversation")
```

### Connecting related concepts
```
# After finding node IDs for "Aconcagua training" and "House/Johnston methodology"
graph_create_edge(
    source_id="abc123...",
    target_id="def456...",
    edge_type="related",
    weight=0.7
)
```

### Exploring a topic
```
# Start from a node and see what's connected
graph_traverse(
    start_node_id="abc123...",
    max_depth=2,
    min_weight=0.3
)
```

## API Nuances (from testing)

1. **Node/edge IDs are UUIDs** - Generated automatically, not prefixed
2. **Access tracking is read-then-increment** - `get_memory_node` returns current count, THEN increments
3. **Search matches content and summary** - Not tags (would need JSON extraction)
4. **Edge weight capped at 1.0** - `strengthen_edge` won't exceed this
5. **Edges are directional** - A→B is different from B→A

## Future Phases

### Phase 2: Semantic Search
- Add embedding generation (sqlite-vec or external)
- Vector similarity for retrieval
- Hybrid search (text + semantic)

### Phase 3: Automatic Linking
- Extract entities/concepts from conversations
- Auto-create nodes for important information
- Suggest edges based on co-occurrence

### Phase 4: Hebbian Learning
- Strengthen edges when nodes accessed together
- Decay edges over time
- Prune weak connections

## Completion Checklist

- [x] Write implementation spec
- [x] Implement schema extension (sqlite_graph.py)
- [x] Implement node CRUD methods
- [x] Implement edge methods
- [x] Implement graph traversal
- [x] Create combined provider (sqlite_with_graph.py)
- [x] Create MCP tools (mcp_graph_tools.py)
- [x] Register tools in mcp_server.py
- [x] Write tests (19 tests)
- [x] All tests passing (252 total)
- [ ] Merge to master
- [ ] Start using in production
