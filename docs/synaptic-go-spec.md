# Synaptic: Go Memory Graph Service

*Created: 2026-01-03*
*For: Claude Code to implement*
*Status: SPEC DRAFT*

## Overview

Synaptic is a standalone Go service providing associative memory for AI agents. It implements a biologically-inspired graph memory with Hebbian learning (connections strengthen with co-activation) and temporal decay (unused connections weaken over time).

**Design Goals:**
- Simple HTTP/gRPC API for any AI system to use
- SQLite storage with optional PostgreSQL for scale
- Background workers for decay, compaction, pruning
- MCP-compatible tools (optional)
- Zero runtime dependencies (single binary)

## Why Go?

- Single binary deployment
- Goroutines for background decay/maintenance
- Excellent concurrency for read-heavy workloads
- Cross-platform builds
- Memory efficient for always-on service

## Core Concepts

### Memory Nodes
- **id**: UUID
- **content**: The actual memory text
- **summary**: Short summary for quick retrieval
- **source**: Where it came from (conversation, research, reflection, etc.)
- **tags**: Array of tags for categorization
- **embedding**: Optional vector for semantic search
- **access_count**: How often retrieved
- **created_at**: When created
- **last_accessed**: Last retrieval time
- **decay_score**: Current strength (0.0-1.0, starts at 1.0)

### Memory Edges
- **id**: UUID
- **source_node_id**: From node
- **target_node_id**: To node  
- **weight**: Connection strength (0.0-1.0)
- **edge_type**: related, causal, temporal, contradicts
- **created_at**: When created
- **last_strengthened**: Last co-activation

### Hebbian Learning
"Neurons that fire together, wire together."

When two nodes are accessed close in time:
1. Find/create edge between them
2. Strengthen edge weight: `weight = min(1.0, weight + learning_rate)`
3. Update `last_strengthened` timestamp

**Parameters (configurable):**
- `learning_rate`: 0.1 (how much each co-activation adds)
- `co_activation_window`: 30 seconds (how close in time = together)

### Temporal Decay
Connections weaken without use, like synapses.

Background worker runs periodically:
1. For each edge: `weight = weight * decay_factor ^ hours_since_last_use`
2. For each node: `decay_score = decay_score * decay_factor ^ hours_since_access`
3. Prune edges below `min_edge_weight` threshold
4. Mark nodes below `min_node_score` for potential archival

**Parameters (configurable):**
- `decay_factor`: 0.99 (per hour, so ~75% after 24h without use)
- `min_edge_weight`: 0.05 (below this, edge is pruned)
- `min_node_score`: 0.1 (below this, node is archived)
- `decay_interval`: 1 hour (how often worker runs)

## API Design

### REST Endpoints

```
# Nodes
POST   /api/v1/nodes              # Create node
GET    /api/v1/nodes/:id          # Get node (increments access)
PUT    /api/v1/nodes/:id          # Update node
DELETE /api/v1/nodes/:id          # Delete node
GET    /api/v1/nodes/search       # Search nodes (text + optional vector)

# Edges  
POST   /api/v1/edges              # Create/update edge
GET    /api/v1/edges/:id          # Get edge
DELETE /api/v1/edges/:id          # Delete edge

# Graph Operations
GET    /api/v1/nodes/:id/connected    # Get connected nodes
POST   /api/v1/traverse               # BFS/DFS traversal
POST   /api/v1/coactivate             # Record co-activation (Hebbian)

# Admin
GET    /api/v1/stats                  # Graph statistics
POST   /api/v1/decay/run              # Manually trigger decay
GET    /api/v1/health                 # Health check
```

### Request/Response Examples

**Create Node:**
```json
POST /api/v1/nodes
{
  "content": "Daniele is training for Aconcagua...",
  "summary": "Aconcagua training info",
  "source": "conversation",
  "tags": ["mountaineering", "training"]
}

Response: 201 Created
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "content": "Daniele is training for Aconcagua...",
  "summary": "Aconcagua training info",
  "source": "conversation",
  "tags": ["mountaineering", "training"],
  "access_count": 0,
  "decay_score": 1.0,
  "created_at": "2026-01-03T16:30:00Z"
}
```

**Record Co-activation (Hebbian learning):**
```json
POST /api/v1/coactivate
{
  "node_ids": ["uuid1", "uuid2", "uuid3"],
  "context": "These nodes were all relevant to answering a question about training"
}

Response: 200 OK
{
  "edges_strengthened": 3,
  "edges_created": 1,
  "details": [
    {"source": "uuid1", "target": "uuid2", "new_weight": 0.6},
    {"source": "uuid1", "target": "uuid3", "new_weight": 0.5},
    {"source": "uuid2", "target": "uuid3", "new_weight": 0.5}
  ]
}
```

**Traverse:**
```json
POST /api/v1/traverse
{
  "start_node_id": "uuid1",
  "max_depth": 2,
  "max_nodes": 20,
  "min_weight": 0.2,
  "algorithm": "bfs"
}

Response: 200 OK
{
  "nodes": [
    {"id": "uuid1", "summary": "Start node", "depth": 0, "path_weight": 1.0},
    {"id": "uuid2", "summary": "Connected node", "depth": 1, "path_weight": 0.7},
    ...
  ]
}
```

## Configuration

```yaml
# config.yaml
server:
  port: 8080
  host: "0.0.0.0"

storage:
  driver: "sqlite"  # or "postgres"
  path: "./synaptic.db"  # for sqlite
  # connection_string: "..."  # for postgres

learning:
  hebbian_rate: 0.1
  co_activation_window_seconds: 30

decay:
  enabled: true
  factor: 0.99  # per hour
  interval_minutes: 60
  min_edge_weight: 0.05
  min_node_score: 0.1

search:
  embedding_provider: "none"  # or "openai", "local"
  # embedding_api_key: "..."
  # embedding_model: "text-embedding-3-small"

logging:
  level: "info"
  format: "json"
```

## Project Structure

```
synaptic/
├── cmd/
│   └── synaptic/
│       └── main.go           # Entry point
├── internal/
│   ├── api/
│   │   ├── handlers.go       # HTTP handlers
│   │   ├── middleware.go     # Logging, auth, etc.
│   │   └── routes.go         # Route setup
│   ├── config/
│   │   └── config.go         # Configuration loading
│   ├── graph/
│   │   ├── node.go           # Node type and methods
│   │   ├── edge.go           # Edge type and methods
│   │   ├── traversal.go      # BFS/DFS algorithms
│   │   └── hebbian.go        # Learning algorithms
│   ├── storage/
│   │   ├── interface.go      # Storage interface
│   │   ├── sqlite.go         # SQLite implementation
│   │   └── postgres.go       # PostgreSQL implementation
│   └── workers/
│       ├── decay.go          # Decay worker
│       └── compaction.go     # Optional compaction
├── pkg/
│   └── client/
│       └── client.go         # Go client library
├── config.example.yaml
├── go.mod
├── go.sum
├── Dockerfile
├── Makefile
└── README.md
```

## Implementation Priorities

### Phase 1: Core (MVP)
1. Basic HTTP server with health check
2. SQLite storage for nodes and edges
3. CRUD operations for nodes and edges
4. Text search
5. Graph traversal (BFS)
6. Basic stats endpoint

### Phase 2: Hebbian Learning
1. Co-activation endpoint
2. Automatic edge strengthening
3. Access tracking

### Phase 3: Decay
1. Background decay worker
2. Configurable decay parameters
3. Edge pruning
4. Node archival

### Phase 4: Polish
1. PostgreSQL support
2. Embedding/semantic search (optional)
3. gRPC API (optional)
4. Prometheus metrics
5. Docker image
6. Documentation

## Integration with Lares

Lares will call Synaptic via HTTP:

1. **On conversation**: Create nodes for important information
2. **On retrieval**: Search nodes, record access
3. **On multi-node query**: Call `/coactivate` with all returned node IDs
4. **Background**: Synaptic handles decay automatically

Eventually, Synaptic becomes an MCP server itself, and any MCP-compatible agent can use it.

## Testing Strategy

- Unit tests for each component
- Integration tests with test database
- Load testing for concurrent access
- Decay simulation tests (time travel)

## Open Questions

1. **Embeddings**: Include in MVP or Phase 2+?
2. **Authentication**: Simple API key? JWT?
3. **Multi-tenancy**: Namespace support for multiple agents?
4. **Backup/Restore**: Built-in or external tooling?

---

*This spec is for Claude Code to implement. Lares (the Python agent) prototyped the concept in SQLite; Synaptic is the production Go version.*
