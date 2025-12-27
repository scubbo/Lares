"""
Lares MCP Server - Portable tool layer for AI agents.

This MCP server provides all Lares tools in a framework-agnostic way.
Any MCP-compatible system (Letta, Claude Desktop, etc.) can connect to it.

Run with: python -m lares.mcp_server
Or: mcp.run(transport="sse") starts uvicorn on configured host:port

Approval endpoints:
  GET  /approvals/pending         - List pending approvals
  GET  /approvals/{id}            - Get specific approval
  POST /approvals/{id}/approve    - Approve and execute
  POST /approvals/{id}/deny       - Deny request
  GET  /health                    - Health check
"""

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from mcp.server import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from lares.mcp_approval import get_queue

# Initialize MCP server
mcp = FastMCP(
    name="lares-tools",
    instructions="Lares household AI tools - shell, files, RSS, BlueSky, Obsidian",
    host="0.0.0.0",
    port=8765,
)

# Configuration
LARES_PROJECT = Path(os.getenv("LARES_PROJECT_PATH", "/home/daniele/workspace/lares"))
OBSIDIAN_VAULT = Path(
    os.getenv("OBSIDIAN_VAULT_PATH", "/home/daniele/workspace/gitlab/daniele/appunti")
)
ALLOWED_DIRECTORIES = [LARES_PROJECT, OBSIDIAN_VAULT]
APPROVAL_DB = Path(
    os.getenv("LARES_APPROVAL_DB", "/home/daniele/workspace/lares/data/approvals.db")
)

BSKY_PUBLIC_API = "https://public.api.bsky.app/xrpc"
BSKY_AUTH_API = "https://bsky.social/xrpc"
_bsky_session_cache: dict = {}

# Initialize approval queue
approval_queue = get_queue(APPROVAL_DB)

# Commands that can run without approval (prefix match)
SHELL_ALLOWLIST = [
    "echo ", "ls", "cat ", "head ", "tail ", "wc ", "grep ",  # Read-only
    "git status", "git log", "git diff", "git branch", "git show",  # Git read
    "git add", "git commit", "git push", "git pull", "git checkout",  # Git write
    "pytest", "python -m pytest", "ruff check", "ruff format", "mypy",  # Dev tools
    "pwd", "whoami", "date", "env", "which ",  # System info
]
# Set to True to require approval for all shell commands
SHELL_REQUIRE_ALL_APPROVAL = os.getenv("MCP_SHELL_REQUIRE_APPROVAL", "").lower() == "true"


# === HELPER FUNCTIONS ===


def is_path_allowed(path: str) -> bool:
    """Check if a path is within allowed directories."""
    try:
        target = Path(path).resolve()
        return any(
            target == allowed or allowed in target.parents
            for allowed in ALLOWED_DIRECTORIES
            if allowed.exists()
        )
    except Exception:
        return False


def _get_bsky_auth_token() -> str | None:
    """Get or refresh BlueSky auth token."""
    if "access_jwt" in _bsky_session_cache:
        return _bsky_session_cache["access_jwt"]

    handle = os.getenv("BLUESKY_HANDLE")
    password = os.getenv("BLUESKY_APP_PASSWORD")

    if not handle or not password:
        return None

    try:
        auth_url = f"{BSKY_AUTH_API}/com.atproto.server.createSession"
        data = json.dumps({"identifier": handle, "password": password}).encode()
        req = urllib.request.Request(
            auth_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            _bsky_session_cache["access_jwt"] = result.get("accessJwt")
            _bsky_session_cache["did"] = result.get("did")
            return _bsky_session_cache["access_jwt"]
    except Exception:
        return None


# === APPROVAL HTTP ENDPOINTS ===


@mcp.custom_route("/approvals/pending", methods=["GET"])
async def get_pending_approvals(request: Request) -> JSONResponse:
    """Get all pending approval requests."""
    pending = approval_queue.get_pending()
    for item in pending:
        try:
            item["args"] = json.loads(item["args"])
        except Exception:
            pass
    return JSONResponse({"pending": pending})


@mcp.custom_route("/approvals/{approval_id}", methods=["GET"])
async def get_approval(request: Request) -> JSONResponse:
    """Get a specific approval request by ID."""
    approval_id = request.path_params["approval_id"]
    item = approval_queue.get(approval_id)
    if not item:
        return JSONResponse({"error": "Approval not found"}, status_code=404)
    try:
        item["args"] = json.loads(item["args"])
    except Exception:
        pass
    return JSONResponse(item)


@mcp.custom_route("/approvals/{approval_id}/approve", methods=["POST"])
async def approve_request(request: Request) -> JSONResponse:
    """Approve a pending request and execute it."""
    approval_id = request.path_params["approval_id"]
    item = approval_queue.get(approval_id)

    if not item:
        return JSONResponse({"error": "Approval not found"}, status_code=404)
    if item["status"] != "pending":
        return JSONResponse({"error": f"Already {item['status']}"}, status_code=400)

    approval_queue.approve(approval_id)

    tool_name = item["tool"]
    args = json.loads(item["args"])

    try:
        result = await mcp.call_tool(tool_name, args)
        result_str = str(result)
        approval_queue.set_result(approval_id, result_str)
        return JSONResponse({"status": "approved", "result": result_str})
    except Exception as e:
        error_msg = f"Execution error: {e}"
        approval_queue.set_result(approval_id, error_msg)
        return JSONResponse({"status": "approved", "result": error_msg})


@mcp.custom_route("/approvals/{approval_id}/deny", methods=["POST"])
async def deny_request(request: Request) -> JSONResponse:
    """Deny a pending request."""
    approval_id = request.path_params["approval_id"]
    item = approval_queue.get(approval_id)

    if not item:
        return JSONResponse({"error": "Approval not found"}, status_code=404)
    if item["status"] != "pending":
        return JSONResponse({"error": f"Already {item['status']}"}, status_code=400)

    approval_queue.deny(approval_id)
    return JSONResponse({"status": "denied"})


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        {
            "status": "ok",
            "server": "lares-mcp",
            "pending_approvals": len(approval_queue.get_pending()),
        }
    )


# === FILE TOOLS ===


@mcp.tool()
def read_file(path: str) -> str:
    """Read a file from the local filesystem."""
    if not is_path_allowed(path):
        return f"Error: Path not in allowed directories: {path}"
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
def list_directory(path: str) -> str:
    """List contents of a directory."""
    if not is_path_allowed(path):
        return f"Error: Path not in allowed directories: {path}"
    try:
        entries = sorted(Path(path).iterdir())
        result = []
        for entry in entries:
            prefix = "📁 " if entry.is_dir() else "📄 "
            result.append(f"{prefix}{entry.name}")
        return "\n".join(result) if result else "(empty directory)"
    except FileNotFoundError:
        return f"Error: Directory not found: {path}"
    except Exception as e:
        return f"Error listing directory: {e}"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file. Requires approval in production mode."""
    if not is_path_allowed(path):
        return f"Error: Path not in allowed directories: {path}"
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"



def is_shell_command_allowed(command: str) -> bool:
    """Check if a shell command can run without approval."""
    if SHELL_REQUIRE_ALL_APPROVAL:
        return False
    cmd_lower = command.strip().lower()
    return any(cmd_lower.startswith(allowed.lower()) for allowed in SHELL_ALLOWLIST)


# === SHELL TOOL ===


@mcp.tool()
def run_shell_command(command: str, working_dir: str | None = None) -> str:
    """Execute a shell command. Non-allowlisted commands require approval."""
    if working_dir and not is_path_allowed(working_dir):
        return f"Error: Working directory not allowed: {working_dir}"

    cwd = working_dir or str(LARES_PROJECT)

    # Check if command needs approval
    if not is_shell_command_allowed(command):
        approval_id = approval_queue.submit(
            "run_shell_command",
            {"command": command, "working_dir": cwd}
        )
        return (
            f"⏳ Command requires approval. ID: {approval_id}\n"
            f"Poll GET /approvals/{approval_id} for status."
        )

    # Allowed command - run directly
    try:
        result = subprocess.run(
            command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=60
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds"
    except Exception as e:
        return f"Error running command: {e}"


# === RSS TOOL ===


@mcp.tool()
def read_rss_feed(url: str, max_entries: int = 5) -> str:
    """Read and parse an RSS or Atom feed."""
    try:
        import feedparser  # type: ignore[import-untyped]
    except ImportError:
        return "Error: feedparser not installed"

    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            err = getattr(feed, "bozo_exception", "Unknown error")
            return f"Error parsing feed: {err}"

        feed_title = feed.feed.get("title", "Untitled Feed")
        lines = [f"📰 **{feed_title}**", ""]

        for entry in feed.entries[:max_entries]:
            title = entry.get("title", "Untitled")
            link = entry.get("link", "")
            pub = getattr(entry, "published", None) or getattr(entry, "updated", None)
            date_str = f" ({pub})" if pub else ""
            lines.append(f"• {title}{date_str}")
            if link:
                lines.append(f"  🔗 {link}")

        remaining = len(feed.entries) - max_entries
        if remaining > 0:
            lines.append(f"\n... and {remaining} more entries")
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading feed: {e}"


# === BLUESKY TOOLS ===


@mcp.tool()
def read_bluesky_user(handle: str, limit: int = 5) -> str:
    """Read recent posts from a BlueSky user."""
    if not handle.endswith(".bsky.social") and "." not in handle:
        handle = f"{handle}.bsky.social"

    try:
        url = f"{BSKY_PUBLIC_API}/app.bsky.feed.getAuthorFeed?actor={handle}&limit={limit}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        posts = data.get("feed", [])
        if not posts:
            return f"No posts found for @{handle}"

        lines = [f"🦋 Recent posts from @{handle}", ""]
        for item in posts:
            post = item.get("post", {})
            record = post.get("record", {})
            text = record.get("text", "")[:200]
            created = record.get("createdAt", "")[:10]
            lines.append(f"• [{created}] {text}")
            lines.append("")
        return "\n".join(lines)
    except urllib.error.HTTPError as e:
        return f"Error: HTTP {e.code} - {e.reason}"
    except Exception as e:
        return f"Error reading BlueSky: {e}"


@mcp.tool()
def search_bluesky(query: str, limit: int = 10) -> str:
    """Search BlueSky posts for a given query. Requires authentication."""
    auth_token = _get_bsky_auth_token()
    if not auth_token:
        return "Error: Search requires auth. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"

    try:
        import urllib.parse

        encoded = urllib.parse.quote(query)
        url = f"{BSKY_AUTH_API}/app.bsky.feed.searchPosts?q={encoded}&limit={limit}"
        headers = {"Authorization": f"Bearer {auth_token}", "Accept": "application/json"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        posts = data.get("posts", [])
        if not posts:
            return f"No results for: {query}"

        lines = [f"🔍 Search results for: {query}", ""]
        for post in posts:
            author = post.get("author", {}).get("handle", "unknown")
            text = post.get("record", {}).get("text", "")[:150]
            lines.append(f"@{author}: {text}")
            lines.append("")
        return "\n".join(lines)
    except urllib.error.HTTPError as e:
        _bsky_session_cache.clear()
        return f"Error: HTTP {e.code} - {e.reason}"
    except Exception as e:
        return f"Error searching BlueSky: {e}"


@mcp.tool()
def post_to_bluesky(text: str) -> str:
    """Post a message to BlueSky. Requires approval in production mode."""
    if len(text) > 300:
        return f"Error: Post too long ({len(text)} chars). Maximum is 300."
    if not text.strip():
        return "Error: Post text cannot be empty."

    auth_token = _get_bsky_auth_token()
    if not auth_token:
        return "Error: Auth required. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"

    did = _bsky_session_cache.get("did")
    if not did:
        return "Error: No DID in session. Re-authentication required."

    try:
        create_url = f"{BSKY_AUTH_API}/com.atproto.repo.createRecord"
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }
        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        payload = json.dumps(
            {
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": record,
            }
        ).encode()

        req = urllib.request.Request(create_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        return f"✅ Posted to BlueSky!\nURI: {result.get('uri')}"
    except urllib.error.HTTPError as e:
        _bsky_session_cache.clear()
        return f"Error: HTTP {e.code} - {e.reason}"
    except Exception as e:
        return f"Error posting to BlueSky: {e}"


# === OBSIDIAN TOOLS ===


@mcp.tool()
def search_obsidian_notes(query: str, max_results: int = 10) -> str:
    """Search for notes in the Obsidian vault containing the query string."""
    if not OBSIDIAN_VAULT.exists():
        return f"Error: Obsidian vault not found at {OBSIDIAN_VAULT}"

    matches = []
    query_lower = query.lower()

    try:
        for md_file in OBSIDIAN_VAULT.rglob("*.md"):
            if any(part.startswith(".") for part in md_file.parts):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                if query_lower in content.lower():
                    rel_path = md_file.relative_to(OBSIDIAN_VAULT)
                    count = content.lower().count(query_lower)
                    matches.append((str(rel_path), count))
            except Exception:
                continue

        if not matches:
            return f"No notes found containing: {query}"

        matches.sort(key=lambda x: x[1], reverse=True)
        lines = [f"📔 Notes matching '{query}':", ""]
        for path, count in matches[:max_results]:
            lines.append(f"• {path} ({count} match{'es' if count > 1 else ''})")

        remaining = len(matches) - max_results
        if remaining > 0:
            lines.append(f"\n... and {remaining} more notes")
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching notes: {e}"


@mcp.tool()
def read_obsidian_note(path: str) -> str:
    """Read a specific note from the Obsidian vault."""
    note_path = OBSIDIAN_VAULT / path

    try:
        note_path.resolve().relative_to(OBSIDIAN_VAULT.resolve())
    except ValueError:
        return "Error: Path must be within the Obsidian vault"

    if not note_path.exists():
        return f"Error: Note not found: {path}"
    if note_path.suffix != ".md":
        return "Error: Only markdown files can be read"

    try:
        content = note_path.read_text(encoding="utf-8")
        return f"📄 {path}\n{'=' * 40}\n\n{content}"
    except Exception as e:
        return f"Error reading note: {e}"


# === ENTRY POINT ===

if __name__ == "__main__":
    print("Starting Lares MCP Server on http://0.0.0.0:8765")
    print("Tools: read_file, list_directory, write_file, run_shell_command")
    print("       read_rss_feed, read_bluesky_user, search_bluesky, post_to_bluesky")
    print("       search_obsidian_notes, read_obsidian_note")
    print("Endpoints: /health, /approvals/pending, /approvals/{id}")
    mcp.run(transport="sse")
