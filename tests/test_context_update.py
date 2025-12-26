#!/usr/bin/env python3
"""Test that context window limit updates work for existing agents."""

import importlib
import os
import sys
from unittest.mock import Mock, MagicMock

# Add src to path
sys.path.insert(0, 'src')


def test_context_window_update():
    """Test that existing agents get their context window updated."""

    # Set test values BEFORE importing/reloading
    os.environ["LARES_CONTEXT_WINDOW_LIMIT"] = "75000"

    # Reload the module to pick up new env var
    import lares.memory
    importlib.reload(lares.memory)
    from lares.memory import get_or_create_agent, LARES_CONTEXT_WINDOW_LIMIT

    # Verify we got the updated value
    assert LARES_CONTEXT_WINDOW_LIMIT == 75000, f"Expected 75000, got {LARES_CONTEXT_WINDOW_LIMIT}"

    print(f"Testing context window update to {LARES_CONTEXT_WINDOW_LIMIT} tokens")
    print("=" * 50)

    # Mock the Letta client
    mock_client = Mock()

    # Mock config with existing agent ID
    mock_config = Mock()
    mock_config.agent_id = "test-agent-123"

    # Test Case 1: Agent with no context_window_limit set
    print("\nTest 1: Agent without context_window_limit")
    mock_agent = Mock()
    mock_agent.id = "test-agent-123"
    mock_agent.name = "lares"
    mock_agent.model = "anthropic/claude-opus-4-5-20251101"
    # No context_window_limit attribute

    mock_client.agents.retrieve.return_value = mock_agent
    mock_client.agents.update = MagicMock()

    # Run the function
    import asyncio
    agent_id = asyncio.run(get_or_create_agent(mock_client, mock_config))

    # Check that update was called with context window
    mock_client.agents.update.assert_called_with(
        "test-agent-123",
        context_window_limit=75000
    )
    print("  ✅ Update called with context_window_limit=75000")

    # Test Case 2: Agent with different context_window_limit
    print("\nTest 2: Agent with different context_window_limit")
    mock_agent2 = Mock()
    mock_agent2.id = "test-agent-123"
    mock_agent2.name = "lares"
    mock_agent2.model = "anthropic/claude-opus-4-5-20251101"
    mock_agent2.context_window_limit = 25000  # Old value

    mock_client.agents.retrieve.return_value = mock_agent2
    mock_client.agents.update.reset_mock()

    agent_id = asyncio.run(get_or_create_agent(mock_client, mock_config))

    mock_client.agents.update.assert_called_with(
        "test-agent-123",
        context_window_limit=75000
    )
    print("  ✅ Update called to change from 25000 to 75000")

    # Test Case 3: Agent with same context_window_limit
    print("\nTest 3: Agent with same context_window_limit")
    mock_agent3 = Mock()
    mock_agent3.id = "test-agent-123"
    mock_agent3.name = "lares"
    mock_agent3.model = "anthropic/claude-opus-4-5-20251101"
    mock_agent3.context_window_limit = 75000  # Same as env var

    mock_client.agents.retrieve.return_value = mock_agent3
    mock_client.agents.update.reset_mock()

    agent_id = asyncio.run(get_or_create_agent(mock_client, mock_config))

    # Should NOT call update since limit is already correct
    mock_client.agents.update.assert_not_called()
    print("  ✅ No update needed (already at 75000)")

    print("\n" + "=" * 50)
    print("✅ All tests passed!")
    print("\nThis means:")
    print("1. Existing agents will automatically get updated context window")
    print("2. No need to recreate the agent (memory preserved!)")
    print("3. Just set LARES_CONTEXT_WINDOW_LIMIT and restart")

    # Cleanup: restore default value
    os.environ["LARES_CONTEXT_WINDOW_LIMIT"] = "50000"
    importlib.reload(lares.memory)


if __name__ == "__main__":
    test_context_window_update()
