#!/usr/bin/env python3
"""
Test script for MCP approval flow.

Simulates:
1. MCP server submitting an approval request
2. Polling for pending approvals
3. Approving/denying and getting results

Run with: python scripts/test_mcp_approval_flow.py
"""

import json
import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lares.mcp_approval import ApprovalQueue
from lares.mcp_bridge import MCPApprovalBridge, PendingApproval


def test_approval_queue_standalone():
    """Test the approval queue without HTTP server."""
    print("=== Testing ApprovalQueue ===\n")
    
    # Create a test database
    db_path = Path("/tmp/test_approval.db")
    queue = ApprovalQueue(db_path)
    
    # Submit a test approval
    print("1. Submitting approval request...")
    aid = queue.submit("run_shell_command", {"command": "echo hello world"})
    print(f"   Created approval: {aid}")
    
    # Check pending
    print("\n2. Checking pending approvals...")
    pending = queue.get_pending()
    print(f"   Found {len(pending)} pending approvals:")
    for p in pending:
        print(f"   - {p['id']}: {p['tool']} ({p['args']})")
    
    # Approve it
    print(f"\n3. Approving {aid}...")
    queue.approve(aid)
    
    # Simulate execution result
    queue.set_result(aid, "hello world")
    
    # Check final state
    print("\n4. Final state:")
    item = queue.get(aid)
    print(f"   Status: {item['status']}")
    print(f"   Result: {item['result']}")
    
    # Cleanup
    db_path.unlink(missing_ok=True)
    print("\n✅ ApprovalQueue test passed!\n")


def test_bridge_message_formatting():
    """Test the bridge's message formatting."""
    print("=== Testing MCPApprovalBridge ===\n")
    
    bridge = MCPApprovalBridge()
    
    # Test formatting
    pending = PendingApproval(
        approval_id="test123",
        tool="run_shell_command",
        args={"command": "rm -rf /important/files"},
    )
    
    msg = bridge.format_approval_message(pending)
    print("Formatted message:")
    print("-" * 40)
    print(msg)
    print("-" * 40)
    
    # Verify key elements
    assert "test123" in msg
    assert "run_shell_command" in msg
    assert "rm -rf" in msg
    assert "✅" in msg
    assert "❌" in msg
    
    print("\n✅ Bridge formatting test passed!\n")


def test_end_to_end_simulation():
    """Simulate full end-to-end flow (without Discord)."""
    print("=== End-to-End Simulation ===\n")
    
    # Setup
    db_path = Path("/tmp/test_e2e.db")
    queue = ApprovalQueue(db_path)
    bridge = MCPApprovalBridge()
    
    # 1. MCP tool requests approval
    print("1. MCP tool requests approval for: ls -la /home")
    aid = queue.submit("run_shell_command", {"command": "ls -la /home"})
    
    # 2. Bridge polls and finds it
    print("\n2. Bridge polls for pending approvals...")
    pending = queue.get_pending()
    print(f"   Found: {pending[0]['id']}")
    
    # 3. Format for Discord
    parsed_item = PendingApproval(
        approval_id=pending[0]["id"],
        tool=pending[0]["tool"],
        args=json.loads(pending[0]["args"]),
    )
    msg = bridge.format_approval_message(parsed_item)
    print(f"\n3. Would post to Discord:\n{msg[:200]}...")
    
    # 4. Simulate user approval
    print("\n4. User reacts with ✅...")
    queue.approve(aid)
    
    # 5. Tool execution
    print("\n5. MCP tool executes command and stores result")
    queue.set_result(aid, "drwxr-xr-x 3 daniele daniele 4096 Dec 27 00:00 daniele")
    
    # 6. MCP tool retrieves result
    final = queue.get(aid)
    print(f"\n6. Final state:")
    print(f"   Status: {final['status']}")
    print(f"   Result: {final['result']}")
    
    # Cleanup
    db_path.unlink(missing_ok=True)
    print("\n✅ End-to-end simulation passed!\n")


if __name__ == "__main__":
    test_approval_queue_standalone()
    test_bridge_message_formatting()
    test_end_to_end_simulation()
    
    print("=" * 50)
    print("All tests passed! 🎉")
    print("=" * 50)
