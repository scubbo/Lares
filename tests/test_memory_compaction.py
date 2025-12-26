#!/usr/bin/env python3
"""
Test script for memory compaction recovery mechanism.

This script simulates system alerts from Letta to test the recovery behavior.
Run this with the bot running to verify the changes work correctly.
"""

import asyncio
import json
from unittest.mock import Mock, patch

from lares.memory import MessageResponse, _detect_system_alert


def test_system_alert_detection():
    """Test that various formats of system alerts are detected correctly."""
    test_cases = [
        # Case 1: JSON format in content
        [
            Mock(
                content=json.dumps({
                    "type": "system_alert",
                    "message": "Note: prior messages have been hidden from view due to conversation memory constraints.\nThe following is a summary of the previous messages:\n [summary here]"
                })
            )
        ],
        # Case 2: Plain text pattern
        [
            Mock(
                content="Note: prior messages have been hidden from view due to conversation memory constraints.\nThe following is a summary..."
            )
        ],
        # Case 3: SystemAlertMessage type
        [
            type('SystemAlertMessage', (), {
                'message': 'Memory compaction summary here'
            })()
        ],
        # Case 4: Mixed with other messages (should still detect)
        [
            Mock(role="assistant", content="Normal response"),
            Mock(content='{"type": "system_alert", "message": "Memory compaction occurred"}'),
        ]
    ]

    print("Testing system alert detection...")
    for i, messages in enumerate(test_cases, 1):
        is_alert, summary = _detect_system_alert(messages)
        print(f"  Test case {i}: Alert detected={is_alert}, Summary preview={summary[:50] if summary else None}...")
        assert is_alert, f"Test case {i} should have detected system alert"

    # Negative test case - no alert
    normal_messages = [
        Mock(role="assistant", content="Just a normal response"),
        Mock(role="user", content="A user message"),
    ]
    is_alert, summary = _detect_system_alert(normal_messages)
    print(f"  Negative test: Alert detected={is_alert} (should be False)")
    assert not is_alert, "Should not detect alert in normal messages"

    print("✅ All detection tests passed!\n")


def test_message_response_with_retry():
    """Test the MessageResponse structure with retry flag."""
    # Test response that needs retry
    response = MessageResponse(
        text=None,
        pending_tool_calls=[],
        system_alert="Memory compaction summary",
        needs_retry=True,
    )

    print("Testing MessageResponse with retry flag...")
    print(f"  needs_retry: {response.needs_retry}")
    print(f"  system_alert: {response.system_alert[:50]}...")
    assert response.needs_retry
    assert response.system_alert
    print("✅ MessageResponse test passed!\n")


async def simulate_live_test():
    """
    Simulate a live test by mocking Letta responses.

    This would normally require the bot to be running, but we can test
    the core logic without actually running the bot.
    """
    print("Simulating live memory compaction scenario...")

    from lares.memory import send_message

    # Create a mock Letta client
    mock_client = Mock()
    mock_agent_id = "test-agent-123"

    # First call returns system alert
    mock_client.agents.messages.create.side_effect = [
        Mock(messages=[
            Mock(content=json.dumps({
                "type": "system_alert",
                "message": "Note: prior messages have been hidden from view due to conversation memory constraints."
            }))
        ]),
        # Second call (retry) returns normal response
        Mock(messages=[
            Mock(role="assistant", content="Now I can continue after reorganizing my memory!"),
        ])
    ]

    # Test the flow
    print("  1. Sending initial message...")
    response1 = send_message(mock_client, mock_agent_id, "Test message")

    if response1.needs_retry:
        print(f"  2. Detected memory compaction: {response1.system_alert[:50]}...")
        print("  3. Would show Discord message: '💭 *Reorganizing my thoughts...*'")
        print("  4. Retrying message...")

        # Simulate retry
        response2 = send_message(mock_client, mock_agent_id, "Test message", retry_on_compaction=False)
        print(f"  5. Got response after retry: {response2.text}")

        assert response2.text == "Now I can continue after reorganizing my memory!"
        print("✅ Live simulation test passed!\n")
    else:
        print("❌ Should have detected retry needed")
        assert False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Memory Compaction Recovery Test Suite")
    print("=" * 60 + "\n")

    # Run synchronous tests
    test_system_alert_detection()
    test_message_response_with_retry()

    # Run async test
    asyncio.run(simulate_live_test())

    print("=" * 60)
    print("✅ All tests completed successfully!")
    print("=" * 60)
    print("\nNext steps for testing with live bot:")
    print("1. Start the bot with these changes")
    print("2. Send many messages to trigger natural memory compaction")
    print("3. Or modify code temporarily to always return system_alert for testing")
    print("4. Verify '💭 *Reorganizing my thoughts...*' appears in Discord")
    print("5. Verify the bot completes its intended actions after retry")


if __name__ == "__main__":
    main()