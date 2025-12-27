#!/usr/bin/env python3
"""
End-to-end test for MCP approval flow.

This script:
1. Submits a test command to the approval queue (simulating a restricted tool)
2. Waits for Lares to poll and post to Discord
3. You approve/deny via Discord reaction
4. Checks the result

Usage:
  1. Start MCP server: python -m lares.mcp_server
  2. Make sure Lares is running (it polls approvals)
  3. Run this: python scripts/test_mcp_e2e.py
"""

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
import uuid

MCP_BASE_URL = "http://127.0.0.1:8765"
APPROVAL_DB = Path("/home/daniele/workspace/lares/data/approvals.db")


def api_get(endpoint: str) -> dict:
    """GET request to MCP server."""
    url = f"{MCP_BASE_URL}{endpoint}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def api_post(endpoint: str, data: dict | None = None) -> dict:
    """POST request to MCP server."""
    url = f"{MCP_BASE_URL}{endpoint}"
    body = json.dumps(data).encode() if data else b""
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def check_health() -> bool:
    """Check if MCP server is running."""
    try:
        result = api_get("/health")
        return result.get("status") == "ok"
    except urllib.error.URLError:
        return False


def submit_test_approval_directly() -> str:
    """Insert a test approval directly into SQLite.
    
    This simulates what a restricted tool would do.
    """
    approval_id = str(uuid.uuid4())[:8]
    now = datetime.now(UTC).isoformat()
    
    APPROVAL_DB.parent.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(APPROVAL_DB) as conn:
        # Ensure table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                tool TEXT NOT NULL,
                args TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
        """)
        
        # Insert test approval
        conn.execute(
            """INSERT INTO approvals (id, tool, args, status, created_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (
                approval_id, 
                "run_shell_command", 
                json.dumps({"command": "echo 'Hello from MCP test!'", "working_dir": "/home/daniele/workspace/lares"}),
                now
            ),
        )
        conn.commit()
    
    return approval_id


def wait_for_resolution(approval_id: str, timeout: int = 120) -> dict | None:
    """Wait for an approval to be resolved."""
    start = time.time()
    while time.time() - start < timeout:
        result = api_get(f"/approvals/{approval_id}")
        if result.get("status") != "pending":
            return result
        print(".", end="", flush=True)
        time.sleep(2)
    return None


def main():
    print("🧪 MCP End-to-End Test")
    print("=" * 50)
    
    # Check server health
    print("\n1. Checking MCP server health...")
    if not check_health():
        print("❌ MCP server not running!")
        print("   Start it with: python -m lares.mcp_server")
        sys.exit(1)
    
    health = api_get("/health")
    print(f"✅ Server healthy")
    print(f"   Pending approvals: {health.get('pending_approvals', 0)}")
    
    # Submit test approval
    print("\n2. Submitting test approval...")
    approval_id = submit_test_approval_directly()
    print(f"✅ Created approval: {approval_id}")
    print(f"   Tool: run_shell_command")
    print(f"   Command: echo 'Hello from MCP test!'")
    
    # Check it shows in pending
    print("\n3. Verifying in pending list...")
    pending = api_get("/approvals/pending")
    pending_ids = [p["id"] for p in pending.get("pending", [])]
    if approval_id in pending_ids:
        print(f"✅ Found in pending list")
    else:
        print(f"⚠️  Not in pending list yet (may take a moment)")
    
    # Wait for Lares to pick it up
    print("\n4. Waiting for Lares to post to Discord...")
    print("   (Lares polls every 5 seconds)")
    print("   👀 Watch Discord for the approval request!")
    print("   React with ✅ to approve or ❌ to deny")
    print()
    print("   Waiting for resolution", end="", flush=True)
    
    result = wait_for_resolution(approval_id)
    print()  # newline after dots
    
    if result:
        print(f"\n5. Resolution received!")
        print(f"   Status: {result.get('status')}")
        if result.get("result"):
            print(f"   Result: {result.get('result')}")
    else:
        print(f"\n⏰ Timeout waiting for resolution")
        print("   Check if Lares is running and polling approvals")
    
    print("\n" + "=" * 50)
    print("Test complete!")


if __name__ == "__main__":
    main()
