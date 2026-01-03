"""BlueSky tools.

Wraps the bluesky_reader module for Letta tool usage.
"""

from lares.bluesky_reader import (
    create_reply,
    follow_user,
    get_notifications,
    get_user_feed,
    search_posts,
    unfollow_user,
)


def read_bluesky_user(handle: str, limit: int = 5) -> str:
    """
    Read recent posts from a BlueSky user.

    Args:
        handle: The user's handle (e.g., "user.bsky.social" or just "username")
        limit: Maximum number of posts to return (default 5)

    Returns:
        Formatted string containing the user's recent posts
    """
    result = get_user_feed(handle, limit=limit)
    return result.format_summary(max_posts=limit)


def search_bluesky(query: str, limit: int = 10) -> str:
    """
    Search BlueSky posts.

    Args:
        query: Search query string
        limit: Maximum number of results (default 10)

    Returns:
        Formatted string containing matching posts
    """
    result = search_posts(query, limit=limit)
    return result.format_summary(max_posts=limit)


def post_to_bluesky(text: str) -> str:
    """
    Post a message to BlueSky. Supports @mentions and #hashtags which are auto-detected.

    Args:
        text: The text to post (max 300 characters). Include @handles to mention users
              and #tags for hashtags.

    Returns:
        Status message indicating success or failure
    """
    from lares.bluesky_reader import create_post

    result = create_post(text)
    return result.format_result()


def follow_bluesky_user(handle: str) -> str:
    """
    Follow a user on BlueSky.

    Args:
        handle: The user's handle (e.g., "user.bsky.social" or just "username")

    Returns:
        Status message indicating success or failure
    """
    result = follow_user(handle)
    return result.format_result()


def unfollow_bluesky_user(handle: str) -> str:
    """
    Unfollow a user on BlueSky.

    Args:
        handle: The user's handle (e.g., "user.bsky.social" or just "username")

    Returns:
        Status message indicating success or failure
    """
    result = unfollow_user(handle)
    return result.format_result()


def reply_to_bluesky_post(text: str, post_uri: str) -> str:
    """
    Reply to an existing BlueSky post. Requires approval.

    Args:
        text: The reply text (max 300 characters). Include @handles to mention users
              and #tags for hashtags.
        post_uri: The AT URI of the post to reply to
                  (e.g., "at://did:plc:xxx/app.bsky.feed.post/yyy")

    Returns:
        Status message indicating success or failure
    """
    result = create_reply(text, post_uri)
    return result.format_result()


def get_bluesky_notifications(limit: int = 20) -> str:
    """
    Get recent BlueSky notifications (mentions, replies, likes, reposts, follows, quotes).

    Args:
        limit: Maximum number of notifications to return (default 20)

    Returns:
        Formatted string containing recent notifications
    """
    result = get_notifications(limit=limit)
    return result.format_summary(max_items=limit)
