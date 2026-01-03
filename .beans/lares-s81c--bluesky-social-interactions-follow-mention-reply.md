---
# lares-s81c
title: 'BlueSky Social Interactions: Follow, Mention, Reply'
status: completed
type: feature
priority: normal
created_at: 2026-01-03T19:46:16Z
updated_at: 2026-01-03T19:50:30Z
---

Add three new BlueSky tools to Lares:
1. **follow_bluesky_user** - Follow/unfollow users on BlueSky
2. **post_to_bluesky with mentions** - Extend existing post tool to support @mentions
3. **reply_to_bluesky_post** - Reply to existing posts (requires approval)

## Analysis Summary

### Current Architecture
- `bluesky_reader.py` - Core BlueSky API client with auth handling, session caching
- `tools/bluesky.py` - Tool wrappers exposing functions to the agent
- `tools/__init__.py` - Tool exports
- `mcp_server.py` - MCP tool definitions and approval handling

### BlueSky API Requirements

**Follow User:**
- Endpoint: `com.atproto.repo.createRecord`
- Collection: `app.bsky.graph.follow`
- Record: `{"$type": "app.bsky.graph.follow", "createdAt": "...", "subject": "<target_did>"}`

**Mentions in Posts:**
- Add facets array to post record
- Facet structure: `{"index": {"byteStart": N, "byteEnd": M}, "features": [{"": "app.bsky.richtext.facet#mention", "did": "..."}]}`
- Need to resolve handles to DIDs first

**Reply to Post:**
- Add reply field to post record
- Structure: `{"reply": {"root": {"uri": "...", "cid": "..."}, "parent": {"uri": "...", "cid": "..."}}}`
- Need to fetch parent post to get root info

## Checklist

### Phase 1: Core API Functions (bluesky_reader.py)
- [x] Add `resolve_handle_to_did()` helper function
- [x] Add `follow_user(handle)` function with auth
- [x] Add `unfollow_user(handle)` function
- [x] Add `get_post(uri)` function to fetch post details for replies
- [x] Add `create_reply(text, parent_uri)` function with reply structure
- [x] Extend `create_post()` to support optional mentions parameter
- [x] Add `parse_mentions(text)` helper to extract @handles and calculate byte positions

### Phase 2: Tool Wrappers (tools/bluesky.py)
- [x] Add `follow_bluesky_user(handle)` tool
- [x] Add `unfollow_bluesky_user(handle)` tool
- [x] Add `reply_to_bluesky_post(text, post_uri)` tool
- [x] Update `post_to_bluesky()` to accept optional mentions

### Phase 3: Exports and Registration (tools/__init__.py)
- [x] Export new tool functions

### Phase 4: MCP Server Integration (mcp_server.py)
- [x] Add `follow_bluesky_user` MCP tool (no approval needed - reversible)
- [x] Add `reply_to_bluesky_post` MCP tool (requires approval - public action)
- [x] Add `_execute_bluesky_reply()` internal executor
- [x] Update approval endpoint to handle reply tool

### Phase 5: Documentation
- [x] Update README.md with new tools
- [x] Add tools to Available Tools table