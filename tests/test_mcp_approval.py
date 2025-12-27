"""Tests for MCP approval queue."""

import tempfile
from pathlib import Path

import pytest

from lares.mcp_approval import ApprovalQueue


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def queue(temp_db):
    """Create an approval queue with temp database."""
    return ApprovalQueue(temp_db)


class TestApprovalQueue:
    """Test the ApprovalQueue class."""

    def test_submit_creates_pending_approval(self, queue):
        """Test that submit creates a pending approval."""
        aid = queue.submit("test_tool", {"arg": "value"})
        assert aid is not None
        assert len(aid) == 8  # UUID prefix

        item = queue.get(aid)
        assert item is not None
        assert item["tool"] == "test_tool"
        assert item["status"] == "pending"

    def test_get_pending_returns_only_pending(self, queue):
        """Test that get_pending only returns pending items."""
        aid1 = queue.submit("tool1", {})
        aid2 = queue.submit("tool2", {})

        pending = queue.get_pending()
        assert len(pending) == 2

        queue.approve(aid1)
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0]["id"] == aid2

    def test_approve_updates_status(self, queue):
        """Test that approve updates status correctly."""
        aid = queue.submit("test_tool", {})

        result = queue.approve(aid)
        assert result is True

        item = queue.get(aid)
        assert item["status"] == "approved"
        assert item["resolved_at"] is not None

    def test_deny_updates_status(self, queue):
        """Test that deny updates status correctly."""
        aid = queue.submit("test_tool", {})

        result = queue.deny(aid)
        assert result is True

        item = queue.get(aid)
        assert item["status"] == "denied"
        assert item["resolved_at"] is not None

    def test_approve_already_resolved_fails(self, queue):
        """Test that approving already resolved item fails."""
        aid = queue.submit("test_tool", {})
        queue.approve(aid)

        # Try to approve again
        result = queue.approve(aid)
        assert result is False

    def test_set_result_stores_result(self, queue):
        """Test that set_result stores the execution result."""
        aid = queue.submit("test_tool", {})
        queue.approve(aid)
        queue.set_result(aid, "execution output here")

        item = queue.get(aid)
        assert item["result"] == "execution output here"

    def test_get_nonexistent_returns_none(self, queue):
        """Test that getting nonexistent ID returns None."""
        item = queue.get("nonexistent")
        assert item is None

    def test_persistence_across_instances(self, temp_db):
        """Test that data persists across queue instances."""
        queue1 = ApprovalQueue(temp_db)
        aid = queue1.submit("persistent_tool", {"key": "value"})

        # Create new instance with same DB
        queue2 = ApprovalQueue(temp_db)
        item = queue2.get(aid)

        assert item is not None
        assert item["tool"] == "persistent_tool"
