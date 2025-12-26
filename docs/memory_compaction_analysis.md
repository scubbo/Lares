# Memory Compaction Analysis & Solutions

## Current Situation

Lares is experiencing frequent memory compactions ("💭 *Reorganizing my thoughts...*") despite only using ~8k out of 80k available in memory blocks. This indicates the issue is with **conversation history** accumulation, not the memory blocks themselves.

## Investigation Results

### 1. Context Window Configuration Options

Based on Letta API documentation, we can configure:

- **`context_window_limit`**: Artificially limit the agent's context window (e.g., 16k instead of full 200k)
- **`max_tokens`**: Maximum tokens to generate (deprecated, use model_settings)
- **`compaction_settings`**: Configure how conversation compaction works
- **`message_buffer_autoclear`**: Option to not remember previous messages

**Current Configuration in Lares:**
```python
# No explicit context_window_limit set
model = "anthropic/claude-opus-4-5-20251101"  # Supports 200k tokens
# No compaction_settings specified
```

### 2. Message Accumulation Patterns

With current settings:
- **Perch time every 30 minutes** (LARES_PERCH_INTERVAL_MINUTES=30)
- Each perch tick adds: prompt (~500 chars) + response + tool calls
- Each user interaction adds: message + response + tool chain
- Tool results can be verbose (file contents, command outputs)

**Estimated accumulation rate:**
- 48 perch ticks per day = ~48 messages minimum
- User interactions: 10-20 per day = 20-40 messages
- Tool chains: multiply by 3-5x for tool calls/results
- **Total: 200-300+ messages per day**

### 3. Why Compaction Triggers So Often

The default Letta context window appears to be much smaller than Claude's capability:
- Claude Opus supports 200k tokens (~800k chars)
- Letta may default to a much smaller window (possibly 8-16k tokens)
- Without explicit configuration, using conservative defaults

## Recommended Solutions

### Solution 1: Increase Context Window Limit (Immediate Fix)

Modify agent creation in `memory.py`:

```python
async def get_or_create_agent(client: Letta, config: Config) -> str:
    # ... existing code ...

    agent = client.agents.create(
        name="lares",
        model=LARES_MODEL,
        embedding="openai/text-embedding-3-small",
        context_window_limit=100000,  # Use 100k tokens (half of Claude's max)
        memory_blocks=[
            {"label": "persona", "value": blocks.persona},
            {"label": "human", "value": blocks.human},
            {"label": "state", "value": blocks.state},
            {"label": "ideas", "value": blocks.ideas},
        ],
        compaction_settings={
            "model": LARES_MODEL,  # Use same model for compaction
            "mode": "selective",    # More intelligent summarization
            "clip_chars": 2000,     # Keep more context when compacting
        }
    )
```

### Solution 2: Proactive History Management (Medium-term)

Add a function to clear old conversation history during perch time:

```python
async def manage_conversation_history(client: Letta, agent_id: str):
    """Proactively manage conversation history to prevent compaction."""

    # Get current message count
    messages = list(client.agents.messages.list(agent_id=agent_id, limit=100))

    if len(messages) > 50:  # Threshold before natural compaction
        # Save important info to memory blocks first
        important_info = summarize_recent_conversations(messages[-50:])

        # Update state block with summary
        update_memory_block(client, agent_id, "state", important_info)

        # Clear old messages (Letta API may not support this directly)
        # Alternative: trigger intentional compaction
        return True

    return False
```

### Solution 3: Optimize Message Verbosity (Long-term)

Reduce context usage by:

1. **Compress tool results:**
```python
def compress_tool_result(result: str, max_length: int = 500) -> str:
    """Compress verbose tool results."""
    if len(result) > max_length:
        # Keep first/last parts and indicate truncation
        return f"{result[:max_length//2]}...[truncated {len(result)-max_length} chars]...{result[-max_length//2:]}"
    return result
```

2. **Shorter perch prompts:**
```python
# Current: ~30 lines of available tools
# Optimized: Reference tools by category, details on request
```

3. **Selective tool history:**
```python
# Don't send trivial tool results back to Letta
if tool_name in ['discord_react', 'simple_acknowledgment']:
    return MessageResponse(text=None, pending_tool_calls=[])
```

### Solution 4: Configuration via Environment Variables

Add these to `.env`:

```bash
# Context window configuration
LARES_CONTEXT_WINDOW_LIMIT=100000  # 100k tokens
LARES_COMPACTION_MODE=selective     # or 'aggressive'
LARES_COMPACTION_THRESHOLD=80       # Compact at 80% full
LARES_MESSAGE_HISTORY_LIMIT=50      # Keep last N messages

# Verbosity control
LARES_COMPRESS_TOOL_RESULTS=true
LARES_MAX_TOOL_RESULT_LENGTH=500
```

## Implementation Priority

1. **Immediate (5 min)**: Add `context_window_limit=100000` to agent creation
2. **Short-term (30 min)**: Add instrumentation to understand actual limits
3. **Medium-term (2 hours)**: Implement proactive history management
4. **Long-term (ongoing)**: Optimize message verbosity

## Testing the Solutions

1. **With instrumentation active:**
   - Monitor actual context size when compaction triggers
   - Identify patterns (time of day, message types)

2. **After increasing context window:**
   - Track reduction in compaction frequency
   - Monitor performance/cost impacts

3. **Success metrics:**
   - Compaction frequency: Target < 1 per day
   - User experience: No interruptions during active conversation
   - Cost: Monitor API usage with larger context

## Code to Add for Monitoring

In your `.env`:
```bash
LARES_CONTEXT_MONITORING=true
```

In startup code:
```python
if os.getenv("LARES_CONTEXT_MONITORING") == "true":
    from tests.test_context_analysis import instrument_memory_module
    analyzer = instrument_memory_module()
```

This will give you live insights into what's triggering compactions.