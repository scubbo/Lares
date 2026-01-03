"""BlueSky social network reader tool for Lares.

Provides functionality to read posts from BlueSky using the AT Protocol API.
This is a read-only tool for research and information gathering.

Authentication is optional but required for some features (like search).
Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in .env to enable.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

log = structlog.get_logger()

# BlueSky API endpoints
BSKY_PUBLIC_API = "https://public.api.bsky.app/xrpc"
BSKY_AUTH_API = "https://bsky.social/xrpc"

# Module-level session cache
_session_cache: dict = {}


@dataclass
class BlueskyPost:
    """A single post from BlueSky."""

    author_handle: str
    author_display_name: str
    text: str
    created_at: str
    like_count: int
    repost_count: int
    reply_count: int
    uri: str

    def format_brief(self) -> str:
        """Format as a brief summary."""
        name = self.author_display_name or self.author_handle
        # Truncate long posts
        text = self.text[:150] + "..." if len(self.text) > 150 else self.text
        text = text.replace("\n", " ")
        return f"💬 **{name}**: {text}"

    def format_full(self) -> str:
        """Format with full details."""
        name = self.author_display_name or self.author_handle
        lines = [
            f"💬 **{name}** (@{self.author_handle})",
            f"   {self.text}",
            f"   ❤️ {self.like_count}  🔄 {self.repost_count}  💬 {self.reply_count}",
            f"   🕐 {self.created_at}",
        ]
        return "\n".join(lines)


@dataclass
class BlueskyFeedResult:
    """Result of fetching a BlueSky feed."""

    posts: list[BlueskyPost]
    cursor: str | None = None
    error: str | None = None

    def format_summary(self, max_posts: int = 5) -> str:
        """Format feed as readable summary."""
        if self.error:
            return f"❌ Error reading BlueSky: {self.error}"

        if not self.posts:
            return "📭 No posts found."

        lines = ["🦋 **BlueSky Feed**", ""]
        for post in self.posts[:max_posts]:
            lines.append(post.format_brief())
            lines.append("")

        remaining = len(self.posts) - max_posts
        if remaining > 0:
            lines.append(f"... and {remaining} more posts")

        return "\n".join(lines)


def _make_request(url: str, headers: dict | None = None) -> dict:
    """Make a GET request to the BlueSky API."""
    default_headers = {
        "Accept": "application/json",
        "User-Agent": "Lares/0.1.0 (household guardian AI)",
    }
    if headers:
        default_headers.update(headers)

    req = urllib.request.Request(url, headers=default_headers)

    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _make_post_request(url: str, data: dict, headers: dict | None = None) -> dict:
    """Make a POST request to the BlueSky API."""
    default_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Lares/0.1.0 (household guardian AI)",
    }
    if headers:
        default_headers.update(headers)

    json_data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=json_data, headers=default_headers, method="POST")

    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _clear_session():
    """Clear the authentication session cache."""
    global _session_cache
    _session_cache.clear()
    log.info("bluesky_session_cleared")


def _get_auth_token(force_refresh: bool = False) -> str | None:
    """Get an authentication token, using cached session if available.

    Args:
        force_refresh: If True, ignore cache and re-authenticate
    """
    global _session_cache

    # Check if we have a cached token
    if not force_refresh and "access_jwt" in _session_cache:
        return _session_cache["access_jwt"]

    # Clear any stale cache if forcing refresh
    if force_refresh:
        _session_cache.clear()

    # Try to authenticate
    handle = os.environ.get("BLUESKY_HANDLE")
    if handle:
        handle = handle.lstrip("@")  # Remove @ if present
    app_password = os.environ.get("BLUESKY_APP_PASSWORD")

    if not handle or not app_password:
        log.debug("bluesky_no_credentials", msg="No BlueSky credentials configured")
        return None

    try:
        log.info("bluesky_authenticating", handle=handle)
        auth_url = f"{BSKY_AUTH_API}/com.atproto.server.createSession"
        session_data = _make_post_request(auth_url, {
            "identifier": handle,
            "password": app_password,
        })

        access_jwt = session_data.get("accessJwt")
        if access_jwt:
            _session_cache["access_jwt"] = access_jwt
            _session_cache["did"] = session_data.get("did")
            log.info("bluesky_authenticated", handle=handle)
            return access_jwt
        else:
            log.error("bluesky_auth_no_token", msg="No access token in response")
            return None

    except urllib.error.HTTPError as e:
        log.error("bluesky_auth_failed", error=f"HTTP {e.code}: {e.reason}")
        return None
    except Exception as e:
        log.error("bluesky_auth_error", error=str(e))
        return None


def _is_token_expired_error(error: urllib.error.HTTPError) -> bool:
    """Check if an HTTP error indicates an expired token."""
    if error.code == 401:
        return True
    if error.code == 400:
        try:
            error_body = error.read().decode("utf-8")
            # Reset the file pointer so caller can read it too
            return "ExpiredToken" in error_body
        except Exception:
            pass
    return False


def _parse_post(post_view: dict) -> BlueskyPost:
    """Parse a post from the API response."""
    post = post_view.get("post", post_view)
    author = post.get("author", {})
    record = post.get("record", {})

    return BlueskyPost(
        author_handle=author.get("handle", "unknown"),
        author_display_name=author.get("displayName", ""),
        text=record.get("text", ""),
        created_at=record.get("createdAt", ""),
        like_count=post.get("likeCount", 0),
        repost_count=post.get("repostCount", 0),
        reply_count=post.get("replyCount", 0),
        uri=post.get("uri", ""),
    )


def get_user_feed(handle: str, limit: int = 10) -> BlueskyFeedResult:
    """
    Get recent posts from a BlueSky user.

    Args:
        handle: The user's handle (e.g., "user.bsky.social")
        limit: Maximum number of posts to return

    Returns:
        BlueskyFeedResult containing posts or error
    """
    log.info("fetching_bluesky_user_feed", handle=handle, limit=limit)

    try:
        # First resolve the handle to a DID
        resolve_url = f"{BSKY_PUBLIC_API}/com.atproto.identity.resolveHandle?handle={handle}"
        resolve_data = _make_request(resolve_url)
        did = resolve_data.get("did")

        if not did:
            return BlueskyFeedResult(posts=[], error=f"Could not resolve handle: {handle}")

        # Get the author's feed
        feed_url = f"{BSKY_PUBLIC_API}/app.bsky.feed.getAuthorFeed?actor={did}&limit={limit}"
        feed_data = _make_request(feed_url)

        posts = []
        for item in feed_data.get("feed", []):
            try:
                post = _parse_post(item)
                posts.append(post)
            except Exception as e:
                log.warning("failed_to_parse_post", error=str(e))
                continue

        log.info("bluesky_feed_fetched", handle=handle, post_count=len(posts))
        return BlueskyFeedResult(
            posts=posts,
            cursor=feed_data.get("cursor"),
        )

    except urllib.error.HTTPError as e:
        error_msg = f"HTTP {e.code}: {e.reason}"
        log.error("bluesky_http_error", handle=handle, error=error_msg)
        return BlueskyFeedResult(posts=[], error=error_msg)

    except urllib.error.URLError as e:
        error_msg = f"Network error: {e.reason}"
        log.error("bluesky_network_error", handle=handle, error=error_msg)
        return BlueskyFeedResult(posts=[], error=error_msg)

    except Exception as e:
        log.error("bluesky_error", handle=handle, error=str(e), error_type=type(e).__name__)
        return BlueskyFeedResult(posts=[], error=str(e))


def search_posts(query: str, limit: int = 10) -> BlueskyFeedResult:
    """
    Search for posts on BlueSky.

    Requires authentication - set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in .env.

    Args:
        query: Search query string
        limit: Maximum number of posts to return

    Returns:
        BlueskyFeedResult containing matching posts or error
    """
    log.info("searching_bluesky", query=query, limit=limit)

    # Get auth token (required for search)
    auth_token = _get_auth_token()
    if not auth_token:
        return BlueskyFeedResult(
            posts=[],
            error="Search requires authentication. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"
        )

    def _do_search(token: str) -> BlueskyFeedResult:
        # URL encode the query
        encoded_query = urllib.parse.quote(query)
        search_url = f"{BSKY_AUTH_API}/app.bsky.feed.searchPosts?q={encoded_query}&limit={limit}"

        # Make authenticated request
        headers = {"Authorization": f"Bearer {token}"}
        search_data = _make_request(search_url, headers=headers)

        posts = []
        for item in search_data.get("posts", []):
            try:
                post = _parse_post(item)
                posts.append(post)
            except Exception as e:
                log.warning("failed_to_parse_post", error=str(e))
                continue

        log.info("bluesky_search_complete", query=query, post_count=len(posts))
        return BlueskyFeedResult(
            posts=posts,
            cursor=search_data.get("cursor"),
        )

    try:
        return _do_search(auth_token)

    except urllib.error.HTTPError as e:
        # Check for expired token and retry
        if _is_token_expired_error(e):
            log.info("bluesky_token_expired_retrying", msg="Token expired, refreshing and retrying")
            new_token = _get_auth_token(force_refresh=True)
            if new_token:
                try:
                    return _do_search(new_token)
                except urllib.error.HTTPError as retry_e:
                    error_msg = f"HTTP {retry_e.code}: {retry_e.reason}"
                    log.error("bluesky_search_http_error_after_retry", query=query, error=error_msg)
                    return BlueskyFeedResult(posts=[], error=error_msg)

        error_msg = f"HTTP {e.code}: {e.reason}"
        log.error("bluesky_search_http_error", query=query, error=error_msg)
        return BlueskyFeedResult(posts=[], error=error_msg)

    except urllib.error.URLError as e:
        error_msg = f"Network error: {e.reason}"
        log.error("bluesky_search_network_error", query=query, error=error_msg)
        return BlueskyFeedResult(posts=[], error=error_msg)

    except Exception as e:
        log.error("bluesky_search_error", query=query, error=str(e), error_type=type(e).__name__)
        return BlueskyFeedResult(posts=[], error=str(e))


@dataclass
class BlueskyNotification:
    """A single BlueSky notification."""

    reason: str  # like, repost, follow, mention, reply, quote
    author_handle: str
    author_display_name: str
    created_at: str
    uri: str
    is_read: bool
    text: str | None = None  # For mentions/replies/quotes

    def format_brief(self) -> str:
        """Format as a brief summary."""
        name = self.author_display_name or self.author_handle
        emoji = {
            "like": "❤️",
            "repost": "🔄",
            "follow": "👤",
            "mention": "📣",
            "reply": "💬",
            "quote": "💭",
        }.get(self.reason, "🔔")

        if self.reason == "follow":
            return f"{emoji} **{name}** followed you"
        elif self.reason == "like":
            return f"{emoji} **{name}** liked your post"
        elif self.reason == "repost":
            return f"{emoji} **{name}** reposted your post"
        elif self.text:
            text_preview = self.text[:100] + "..." if len(self.text) > 100 else self.text
            text_preview = text_preview.replace("\n", " ")
            return f"{emoji} **{name}**: {text_preview}"
        else:
            return f"{emoji} **{name}** ({self.reason})"


@dataclass
class BlueskyNotificationsResult:
    """Result of fetching BlueSky notifications."""

    notifications: list[BlueskyNotification]
    cursor: str | None = None
    error: str | None = None

    def format_summary(self, max_items: int = 10) -> str:
        """Format notifications as readable summary."""
        if self.error:
            return f"❌ Error fetching notifications: {self.error}"

        if not self.notifications:
            return "📭 No new notifications."

        lines = ["🔔 **BlueSky Notifications**", ""]
        for notif in self.notifications[:max_items]:
            lines.append(notif.format_brief())
            lines.append("")

        remaining = len(self.notifications) - max_items
        if remaining > 0:
            lines.append(f"... and {remaining} more notifications")

        return "\n".join(lines)


def get_notifications(limit: int = 20) -> BlueskyNotificationsResult:
    """
    Get recent notifications from BlueSky.

    Requires authentication - set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in .env.

    Args:
        limit: Maximum number of notifications to return

    Returns:
        BlueskyNotificationsResult containing notifications or error
    """
    log.info("fetching_bluesky_notifications", limit=limit)

    auth_token = _get_auth_token()
    if not auth_token:
        return BlueskyNotificationsResult(
            notifications=[],
            error="Notifications require auth. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"
        )

    def _do_fetch(token: str) -> BlueskyNotificationsResult:
        url = f"{BSKY_AUTH_API}/app.bsky.notification.listNotifications?limit={limit}"
        headers = {"Authorization": f"Bearer {token}"}
        data = _make_request(url, headers=headers)

        notifications = []
        for item in data.get("notifications", []):
            try:
                author = item.get("author", {})
                record = item.get("record", {})

                notif = BlueskyNotification(
                    reason=item.get("reason", "unknown"),
                    author_handle=author.get("handle", "unknown"),
                    author_display_name=author.get("displayName", ""),
                    created_at=item.get("indexedAt", ""),
                    uri=item.get("uri", ""),
                    is_read=item.get("isRead", False),
                    text=record.get("text") if record else None,
                )
                notifications.append(notif)
            except Exception as e:
                log.warning("failed_to_parse_notification", error=str(e))
                continue

        log.info("bluesky_notifications_fetched", count=len(notifications))
        return BlueskyNotificationsResult(
            notifications=notifications,
            cursor=data.get("cursor"),
        )

    try:
        return _do_fetch(auth_token)

    except urllib.error.HTTPError as e:
        if _is_token_expired_error(e):
            log.info("bluesky_token_expired_retrying")
            new_token = _get_auth_token(force_refresh=True)
            if new_token:
                try:
                    return _do_fetch(new_token)
                except urllib.error.HTTPError as retry_e:
                    error_msg = f"HTTP {retry_e.code}: {retry_e.reason}"
                    return BlueskyNotificationsResult(notifications=[], error=error_msg)

        error_msg = f"HTTP {e.code}: {e.reason}"
        log.error("bluesky_notifications_http_error", error=error_msg)
        return BlueskyNotificationsResult(notifications=[], error=error_msg)

    except urllib.error.URLError as e:
        error_msg = f"Network error: {e.reason}"
        log.error("bluesky_notifications_network_error", error=error_msg)
        return BlueskyNotificationsResult(notifications=[], error=error_msg)

    except Exception as e:
        log.error("bluesky_notifications_error", error=str(e), error_type=type(e).__name__)
        return BlueskyNotificationsResult(notifications=[], error=str(e))


# Convenience test
if __name__ == "__main__":
    # Test with a public account
    print("Testing user feed (no auth required):")
    result = get_user_feed("bsky.app", limit=3)
    print(result.format_summary())

    print("\nTesting search (auth required):")
    result = search_posts("AI agents", limit=3)
    print(result.format_summary())


@dataclass
class BlueskyPostResult:
    """Result of creating a BlueSky post."""

    success: bool
    uri: str | None = None
    cid: str | None = None
    error: str | None = None

    def format_result(self) -> str:
        """Format the result for display."""
        if self.success:
            return f"✅ Posted to BlueSky!\nURI: {self.uri}"
        else:
            return f"❌ Failed to post: {self.error}"


def resolve_handle_to_did(handle: str) -> str | None:
    """
    Resolve a BlueSky handle to its DID.

    Args:
        handle: The user's handle (e.g., "user.bsky.social")

    Returns:
        The user's DID or None if resolution fails
    """
    if not handle.endswith(".bsky.social") and "." not in handle:
        handle = f"{handle}.bsky.social"
    handle = handle.lstrip("@")

    try:
        resolve_url = f"{BSKY_PUBLIC_API}/com.atproto.identity.resolveHandle?handle={handle}"
        data = _make_request(resolve_url)
        return data.get("did")
    except Exception as e:
        log.error("bluesky_resolve_handle_failed", handle=handle, error=str(e))
        return None


def parse_mentions(text: str) -> list[dict]:
    """
    Parse @mentions from text and return facet structures.

    Args:
        text: The post text containing @mentions

    Returns:
        List of facet dicts with byte positions and DIDs
    """
    facets = []
    mention_pattern = re.compile(r"@([a-zA-Z0-9._-]+(?:\.[a-zA-Z0-9._-]+)*)")

    for match in mention_pattern.finditer(text):
        handle = match.group(1)
        did = resolve_handle_to_did(handle)
        if not did:
            log.warning("bluesky_mention_resolve_failed", handle=handle)
            continue

        mention_text = match.group(0)
        start_char = match.start()
        byte_start = len(text[:start_char].encode("utf-8"))
        byte_end = byte_start + len(mention_text.encode("utf-8"))

        facets.append({
            "index": {
                "byteStart": byte_start,
                "byteEnd": byte_end,
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#mention",
                    "did": did,
                }
            ],
        })

    return facets


def parse_tags(text: str) -> list[dict]:
    """
    Parse #hashtags from text and return facet structures.

    Args:
        text: The post text containing #hashtags

    Returns:
        List of facet dicts with byte positions and tag values
    """
    facets = []
    tag_pattern = re.compile(r"#([a-zA-Z0-9_]+)")

    for match in tag_pattern.finditer(text):
        tag = match.group(1)
        tag_text = match.group(0)
        start_char = match.start()
        byte_start = len(text[:start_char].encode("utf-8"))
        byte_end = byte_start + len(tag_text.encode("utf-8"))

        facets.append({
            "index": {
                "byteStart": byte_start,
                "byteEnd": byte_end,
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#tag",
                    "tag": tag,
                }
            ],
        })

    return facets


def parse_facets(text: str) -> list[dict]:
    """
    Parse all facets (mentions and tags) from text.

    Args:
        text: The post text

    Returns:
        List of all facet dicts
    """
    return parse_mentions(text) + parse_tags(text)


@dataclass
class BlueskyFollowResult:
    """Result of a follow/unfollow operation."""

    success: bool
    uri: str | None = None
    error: str | None = None

    def format_result(self) -> str:
        if self.success:
            return f"✅ Follow operation successful!\nURI: {self.uri}"
        else:
            return f"❌ Follow operation failed: {self.error}"


def follow_user(handle: str) -> BlueskyFollowResult:
    """
    Follow a user on BlueSky.

    Args:
        handle: The handle of the user to follow

    Returns:
        BlueskyFollowResult indicating success or failure
    """
    log.info("bluesky_following_user", handle=handle)

    did = resolve_handle_to_did(handle)
    if not did:
        return BlueskyFollowResult(
            success=False,
            error=f"Could not resolve handle: {handle}"
        )

    auth_token = _get_auth_token()
    if not auth_token:
        return BlueskyFollowResult(
            success=False,
            error="Authentication required. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"
        )

    my_did = _session_cache.get("did")
    if not my_did:
        return BlueskyFollowResult(
            success=False,
            error="No DID in session cache. Re-authentication required."
        )

    def _do_follow(token: str) -> BlueskyFollowResult:
        create_url = f"{BSKY_AUTH_API}/com.atproto.repo.createRecord"
        headers = {"Authorization": f"Bearer {token}"}

        record = {
            "$type": "app.bsky.graph.follow",
            "subject": did,
            "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

        payload = {
            "repo": my_did,
            "collection": "app.bsky.graph.follow",
            "record": record,
        }

        response = _make_post_request(create_url, payload, headers)
        log.info("bluesky_follow_created", uri=response.get("uri"), handle=handle)
        return BlueskyFollowResult(
            success=True,
            uri=response.get("uri"),
        )

    try:
        return _do_follow(auth_token)
    except urllib.error.HTTPError as e:
        if _is_token_expired_error(e):
            log.info("bluesky_token_expired_retrying")
            new_token = _get_auth_token(force_refresh=True)
            if new_token:
                try:
                    return _do_follow(new_token)
                except urllib.error.HTTPError as retry_e:
                    error_msg = f"HTTP {retry_e.code}: {retry_e.reason}"
                    return BlueskyFollowResult(success=False, error=error_msg)
        error_msg = f"HTTP {e.code}: {e.reason}"
        return BlueskyFollowResult(success=False, error=error_msg)
    except Exception as e:
        log.error("bluesky_follow_error", error=str(e))
        return BlueskyFollowResult(success=False, error=str(e))


def unfollow_user(handle: str) -> BlueskyFollowResult:
    """
    Unfollow a user on BlueSky.

    Args:
        handle: The handle of the user to unfollow

    Returns:
        BlueskyFollowResult indicating success or failure
    """
    log.info("bluesky_unfollowing_user", handle=handle)

    did = resolve_handle_to_did(handle)
    if not did:
        return BlueskyFollowResult(
            success=False,
            error=f"Could not resolve handle: {handle}"
        )

    auth_token = _get_auth_token()
    if not auth_token:
        return BlueskyFollowResult(
            success=False,
            error="Authentication required. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"
        )

    my_did = _session_cache.get("did")
    if not my_did:
        return BlueskyFollowResult(
            success=False,
            error="No DID in session cache. Re-authentication required."
        )

    try:
        list_url = (
            f"{BSKY_AUTH_API}/com.atproto.repo.listRecords"
            f"?repo={my_did}&collection=app.bsky.graph.follow&limit=100"
        )
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = _make_request(list_url, headers)

        record_key = None
        for record in response.get("records", []):
            if record.get("value", {}).get("subject") == did:
                uri = record.get("uri", "")
                record_key = uri.split("/")[-1]
                break

        if not record_key:
            return BlueskyFollowResult(
                success=False,
                error=f"Not following user: {handle}"
            )

        delete_url = f"{BSKY_AUTH_API}/com.atproto.repo.deleteRecord"
        payload = {
            "repo": my_did,
            "collection": "app.bsky.graph.follow",
            "rkey": record_key,
        }
        _make_post_request(delete_url, payload, headers)

        log.info("bluesky_unfollow_success", handle=handle)
        return BlueskyFollowResult(
            success=True,
            uri=f"Unfollowed {handle}",
        )
    except urllib.error.HTTPError as e:
        error_msg = f"HTTP {e.code}: {e.reason}"
        return BlueskyFollowResult(success=False, error=error_msg)
    except Exception as e:
        log.error("bluesky_unfollow_error", error=str(e))
        return BlueskyFollowResult(success=False, error=str(e))


@dataclass
class BlueskyPostInfo:
    """Information about a BlueSky post needed for replies."""

    uri: str
    cid: str
    author_did: str
    text: str
    root_uri: str | None = None
    root_cid: str | None = None


def get_post(uri: str) -> BlueskyPostInfo | None:
    """
    Fetch a post's details by its AT URI.

    Args:
        uri: The AT URI of the post (at://did:plc:.../app.bsky.feed.post/...)

    Returns:
        BlueskyPostInfo with post details or None if not found
    """
    log.info("bluesky_fetching_post", uri=uri)

    try:
        encoded_uri = urllib.parse.quote(uri, safe="")
        url = f"{BSKY_PUBLIC_API}/app.bsky.feed.getPosts?uris={encoded_uri}"
        data = _make_request(url)

        posts = data.get("posts", [])
        if not posts:
            log.warning("bluesky_post_not_found", uri=uri)
            return None

        post = posts[0]
        record = post.get("record", {})
        reply = record.get("reply", {})

        root_uri = None
        root_cid = None
        if reply:
            root = reply.get("root", {})
            root_uri = root.get("uri")
            root_cid = root.get("cid")

        return BlueskyPostInfo(
            uri=post.get("uri"),
            cid=post.get("cid"),
            author_did=post.get("author", {}).get("did"),
            text=record.get("text", ""),
            root_uri=root_uri,
            root_cid=root_cid,
        )
    except Exception as e:
        log.error("bluesky_get_post_error", uri=uri, error=str(e))
        return None


def create_reply(text: str, parent_uri: str) -> BlueskyPostResult:
    """
    Create a reply to an existing BlueSky post.

    Args:
        text: The reply text (max 300 characters)
        parent_uri: The AT URI of the post to reply to

    Returns:
        BlueskyPostResult indicating success or failure
    """
    log.info("bluesky_creating_reply", text_length=len(text), parent_uri=parent_uri)

    if len(text) > 300:
        return BlueskyPostResult(
            success=False,
            error=f"Reply too long ({len(text)} chars). Maximum is 300 characters."
        )

    if not text.strip():
        return BlueskyPostResult(
            success=False,
            error="Reply text cannot be empty."
        )

    parent_post = get_post(parent_uri)
    if not parent_post:
        return BlueskyPostResult(
            success=False,
            error=f"Could not fetch parent post: {parent_uri}"
        )

    auth_token = _get_auth_token()
    if not auth_token:
        return BlueskyPostResult(
            success=False,
            error="Authentication required. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"
        )

    my_did = _session_cache.get("did")
    if not my_did:
        return BlueskyPostResult(
            success=False,
            error="No DID in session cache. Re-authentication required."
        )

    root_uri = parent_post.root_uri or parent_post.uri
    root_cid = parent_post.root_cid or parent_post.cid

    def _do_reply(token: str) -> BlueskyPostResult:
        create_url = f"{BSKY_AUTH_API}/com.atproto.repo.createRecord"
        headers = {"Authorization": f"Bearer {token}"}

        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "reply": {
                "root": {
                    "uri": root_uri,
                    "cid": root_cid,
                },
                "parent": {
                    "uri": parent_post.uri,
                    "cid": parent_post.cid,
                },
            },
        }

        facets = parse_facets(text)
        if facets:
            record["facets"] = facets

        payload = {
            "repo": my_did,
            "collection": "app.bsky.feed.post",
            "record": record,
        }

        response = _make_post_request(create_url, payload, headers)
        log.info("bluesky_reply_created", uri=response.get("uri"))
        return BlueskyPostResult(
            success=True,
            uri=response.get("uri"),
            cid=response.get("cid"),
        )

    try:
        return _do_reply(auth_token)
    except urllib.error.HTTPError as e:
        if _is_token_expired_error(e):
            new_token = _get_auth_token(force_refresh=True)
            if new_token:
                try:
                    return _do_reply(new_token)
                except urllib.error.HTTPError as retry_e:
                    error_msg = f"HTTP {retry_e.code}: {retry_e.reason}"
                    return BlueskyPostResult(success=False, error=error_msg)
        error_msg = f"HTTP {e.code}: {e.reason}"
        return BlueskyPostResult(success=False, error=error_msg)
    except Exception as e:
        log.error("bluesky_reply_error", error=str(e))
        return BlueskyPostResult(success=False, error=str(e))


def create_post(text: str) -> BlueskyPostResult:
    """
    Create a new post on BlueSky.

    Requires authentication - set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in .env.
    Automatically refreshes expired tokens and retries.

    Args:
        text: The text content of the post (max 300 characters)

    Returns:
        BlueskyPostResult indicating success or failure
    """
    log.info("creating_bluesky_post", text_length=len(text))

    # Validate text length
    if len(text) > 300:
        return BlueskyPostResult(
            success=False,
            error=f"Post too long ({len(text)} chars). Maximum is 300 characters."
        )

    if not text.strip():
        return BlueskyPostResult(
            success=False,
            error="Post text cannot be empty."
        )

    def _do_post(token: str, did: str) -> BlueskyPostResult:
        from datetime import datetime

        # Create the post record
        create_url = f"{BSKY_AUTH_API}/com.atproto.repo.createRecord"
        headers = {"Authorization": f"Bearer {token}"}

        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

        facets = parse_facets(text)
        if facets:
            record["facets"] = facets

        payload = {
            "repo": did,
            "collection": "app.bsky.feed.post",
            "record": record,
        }

        response = _make_post_request(create_url, payload, headers)

        log.info("bluesky_post_created", uri=response.get("uri"))
        return BlueskyPostResult(
            success=True,
            uri=response.get("uri"),
            cid=response.get("cid"),
        )

    # Get auth token
    auth_token = _get_auth_token()
    if not auth_token:
        return BlueskyPostResult(
            success=False,
            error="Authentication required. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"
        )

    # Get DID from cache
    did = _session_cache.get("did")
    if not did:
        return BlueskyPostResult(
            success=False,
            error="No DID in session cache. Re-authentication required."
        )

    try:
        return _do_post(auth_token, did)

    except urllib.error.HTTPError as e:
        # Check for expired token and retry
        if _is_token_expired_error(e):
            log.info("bluesky_token_expired_retrying", msg="Token expired, refreshing and retrying")
            new_token = _get_auth_token(force_refresh=True)
            new_did = _session_cache.get("did")
            if new_token and new_did:
                try:
                    return _do_post(new_token, new_did)
                except urllib.error.HTTPError as retry_e:
                    try:
                        error_body = retry_e.read().decode("utf-8")
                    except Exception:
                        error_body = ""
                    error_msg = f"HTTP {retry_e.code}: {retry_e.reason}"
                    log.error("bluesky_post_http_error_retry", error=error_msg, body=error_body)
                    return BlueskyPostResult(success=False, error=f"{error_msg} - {error_body}")

        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            error_body = ""
        error_msg = f"HTTP {e.code}: {e.reason}"
        log.error("bluesky_post_http_error", error=error_msg, body=error_body)
        return BlueskyPostResult(success=False, error=f"{error_msg} - {error_body}")

    except Exception as e:
        log.error("bluesky_post_error", error=str(e), error_type=type(e).__name__)
        return BlueskyPostResult(success=False, error=str(e))
