"""SQLite Memory Provider with Graph Memory capabilities.

Combines the base SQLite provider with the graph memory mixin
for a complete associative memory system.
"""

from .sqlite import SqliteMemoryProvider
from .sqlite_graph import GraphMemoryMixin


class SqliteGraphMemoryProvider(GraphMemoryMixin, SqliteMemoryProvider):
    """SQLite provider enhanced with graph memory capabilities.

    Inherits all base SQLite functionality (messages, blocks, summaries)
    and adds graph memory (nodes, edges, traversal).

    Usage:
        provider = SqliteGraphMemoryProvider(db_path="data/lares.db")
        await provider.initialize()  # Creates all tables including graph tables

        # Base functionality
        await provider.add_message("user", "Hello")
        await provider.update_block("state", "Active")

        # Graph memory
        node_id = await provider.create_memory_node(
            content="Daniele mentioned interest in mountaineering",
            source="conversation",
            summary="Mountaineering interest",
            tags=["interests", "outdoors"]
        )
    """

    async def initialize(self) -> None:
        """Initialize both base tables and graph tables."""
        # Initialize base SQLite provider
        await super().initialize()

        # Initialize graph memory tables
        await self._create_graph_tables()
